#!/usr/bin/env python3
"""
memory_search.py - Buscador ligero FTS5 en :memory: (estilo Ruflo AgentDB, stdlib puro).
Indexa MEMORY.md y memory/*.md, extrae ruta, línea, confidence (si existe) y snippet.
Usa sqlite3 FTS5 en :memory: con fallback léxico en memoria si FTS5 no está disponible.
"""
import argparse
import glob
import json
import os
import re
import sqlite3
import sys

DEFAULT_PLUGIN_DIR = os.path.expanduser("~/.gemini/config/plugins/chief-of-staff")
REPO_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

CONFIDENCE_RE = re.compile(
    r"(?:^|[\s\[\(|,;])\*{0,2}confidence\*{0,2}\s*[:=]\s*([0-9]+(?:\.[0-9]+)?%?|\b(?:high|medium|low|alta|media|baja)\b)",
    re.IGNORECASE | re.MULTILINE,
)
HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def resolve_base_dir(user_dir: str | None) -> str:
    """Resuelve el directorio raíz donde buscar MEMORY.md y memory/*.md."""
    if user_dir:
        return os.path.abspath(os.path.expanduser(user_dir))
    if os.path.exists(os.path.join(REPO_ROOT_DIR, "MEMORY.md")) or os.path.isdir(os.path.join(REPO_ROOT_DIR, "memory")):
        return REPO_ROOT_DIR
    return DEFAULT_PLUGIN_DIR


def discover_memory_files(base_dir: str) -> list[str]:
    """Descubre MEMORY.md y memory/*.md dentro de base_dir."""
    candidates: list[str] = []
    mem_index = os.path.join(base_dir, "MEMORY.md")
    if os.path.isfile(mem_index):
        candidates.append(mem_index)

    mem_dir = os.path.join(base_dir, "memory")
    if os.path.isdir(mem_dir):
        for p in sorted(glob.glob(os.path.join(mem_dir, "**", "*.md"), recursive=True)):
            if os.path.isfile(p):
                candidates.append(p)
    elif not candidates and os.path.isdir(base_dir):
        for p in sorted(glob.glob(os.path.join(base_dir, "*.md"))):
            if os.path.isfile(p):
                candidates.append(p)

    seen: set[str] = set()
    unique: list[str] = []
    for p in candidates:
        rp = os.path.realpath(p)
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def extract_confidence(text: str) -> str | None:
    """Extrae el valor de confidence de un bloque o cabecera si existe."""
    m = CONFIDENCE_RE.search(text)
    return m.group(1).strip() if m else None


def parse_file_chunks(filepath: str, base_dir: str) -> list[dict]:
    """Divide un archivo Markdown en bloques indexables preservando línea inicial y confidence."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            raw_lines = f.read().splitlines()
    except OSError:
        return []

    if not raw_lines:
        return []

    try:
        rel_path = os.path.relpath(filepath, base_dir)
        if rel_path.startswith(".."):
            rel_path = filepath
    except ValueError:
        rel_path = filepath

    header_sample = "\n".join(raw_lines[:30])
    file_confidence = extract_confidence(header_sample)

    chunks: list[dict] = []
    current_heading = ""
    buf: list[tuple[int, str]] = []

    def flush_buf() -> None:
        if not buf:
            return
        start_line = buf[0][0]
        text = "\n".join(line for _, line in buf).strip()
        if not text:
            buf.clear()
            return
        conf = extract_confidence(text) or file_confidence
        chunks.append({
            "path": rel_path,
            "abs_path": os.path.abspath(filepath),
            "start_line": start_line,
            "heading": current_heading,
            "confidence": conf,
            "lines": list(buf),
            "content": text,
        })
        buf.clear()

    for lineno, line in enumerate(raw_lines, start=1):
        hm = HEADING_RE.match(line)
        if hm:
            flush_buf()
            current_heading = hm.group(1).strip()
            buf.append((lineno, line))
            continue
        if not line.strip():
            flush_buf()
            continue
        buf.append((lineno, line))

    flush_buf()
    return chunks


def refine_match_line_and_snippet(chunk: dict, tokens: list[str], raw_query: str) -> tuple[int, str]:
    """Determina la línea exacta de mayor coincidencia dentro del bloque y construye un snippet compacto."""
    lower_tokens = [t.lower() for t in tokens if t]
    raw_q_lower = raw_query.strip().lower()
    best_line = int(chunk["start_line"])
    best_score = -1
    best_idx = 0
    lines: list[tuple[int, str]] = chunk.get("lines") or [(best_line, chunk.get("content", ""))]

    for idx, (lineno, text) in enumerate(lines):
        low = text.lower()
        score = 0
        if raw_q_lower and raw_q_lower in low:
            score += 10
        for tok in lower_tokens:
            if tok in low:
                score += 2
        if score > best_score:
            best_score = score
            best_line = lineno
            best_idx = idx

    window = [text.strip() for _, text in lines[best_idx:best_idx + 2] if text.strip()]
    snippet = " ".join(window)
    heading = chunk.get("heading") or ""
    if heading and heading.lower() not in snippet.lower():
        snippet = f"[{heading}] {snippet}"
    snippet = re.sub(r"\s+", " ", snippet).strip()
    if len(snippet) > 160:
        snippet = snippet[:157] + "..."
    return best_line, snippet


def search_fts5(chunks: list[dict], query: str, top_k: int) -> tuple[list[dict], bool]:
    """Ejecuta búsqueda con sqlite3 FTS5 en :memory:. Retorna (resultados, fts5_disponible)."""
    tokens = TOKEN_RE.findall(query)
    if not tokens:
        return [], True

    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE memory_fts USING fts5("
            "chunk_idx UNINDEXED, path, heading, content, tokenize='unicode61'"
            ")"
        )
    except sqlite3.OperationalError:
        conn.close()
        return [], False

    try:
        conn.executemany(
            "INSERT INTO memory_fts (chunk_idx, path, heading, content) VALUES (?, ?, ?, ?)",
            [
                (idx, c["path"], c["heading"], c["content"])
                for idx, c in enumerate(chunks)
            ],
        )

        fts_queries = [
            " AND ".join(f'"{t}"*' for t in tokens),
        ]
        if len(tokens) > 1:
            fts_queries.append(" OR ".join(f'"{t}"*' for t in tokens))

        rows = []
        for fq in fts_queries:
            cur = conn.execute(
                "SELECT chunk_idx, bm25(memory_fts) AS rank "
                "FROM memory_fts WHERE memory_fts MATCH ? "
                "ORDER BY rank ASC LIMIT ?",
                (fq, top_k),
            )
            rows = cur.fetchall()
            if rows:
                break

        results: list[dict] = []
        for chunk_idx, rank in rows:
            c = chunks[int(chunk_idx)]
            line_no, snippet = refine_match_line_and_snippet(c, tokens, query)
            results.append({
                "path": c["path"],
                "line": line_no,
                "confidence": c["confidence"],
                "snippet": snippet,
                "score": round(-float(rank), 4),
            })
        return results, True
    except sqlite3.OperationalError:
        return [], False
    finally:
        conn.close()


def search_fallback(chunks: list[dict], query: str, top_k: int) -> list[dict]:
    """Fallback léxico en memoria si FTS5 no está disponible o para consultas por subcadena."""
    tokens = [t.lower() for t in TOKEN_RE.findall(query)]
    raw_q = query.strip().lower()
    if not raw_q:
        return []

    scored: list[tuple[float, int, dict]] = []
    for idx, c in enumerate(chunks):
        haystack = f"{c['path']} {c['heading']} {c['content']}".lower()
        score = 0.0
        if raw_q in haystack:
            score += 5.0
        for tok in tokens:
            count = haystack.count(tok)
            if count > 0:
                score += 1.0 + min(count, 5) * 0.25
        if score > 0:
            scored.append((score, -idx, c))

    scored.sort(reverse=True)
    results: list[dict] = []
    for score, _, c in scored[:top_k]:
        line_no, snippet = refine_match_line_and_snippet(c, tokens, query)
        results.append({
            "path": c["path"],
            "line": line_no,
            "confidence": c["confidence"],
            "snippet": snippet,
            "score": round(score, 4),
        })
    return results


def search_memory(base_dir: str, query: str, top_k: int = 5) -> dict:
    """Indexa MEMORY.md y memory/*.md en base_dir y retorna los top_k resultados."""
    files = discover_memory_files(base_dir)
    chunks: list[dict] = []
    for fpath in files:
        chunks.extend(parse_file_chunks(fpath, base_dir))

    if not chunks or not query.strip():
        return {
            "dir": base_dir,
            "query": query,
            "engine": "fts5",
            "files_indexed": len(files),
            "chunks_indexed": len(chunks),
            "results": [],
        }

    results, fts_ok = search_fts5(chunks, query, top_k)
    engine = "fts5" if fts_ok else "fallback"
    if not results:
        fb_results = search_fallback(chunks, query, top_k)
        if fb_results:
            results = fb_results
            if not fts_ok:
                engine = "fallback"
            else:
                engine = "fts5+fallback"

    return {
        "dir": base_dir,
        "query": query,
        "engine": engine,
        "files_indexed": len(files),
        "chunks_indexed": len(chunks),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Buscador FTS5 en :memory: para MEMORY.md y memory/*.md")
    parser.add_argument("--dir", "-d", default=None, help="Directorio base que contiene MEMORY.md y memory/")
    parser.add_argument("--query", "-q", default=None, help="Consulta de búsqueda")
    parser.add_argument("query_pos", nargs="?", default=None, help="Consulta de búsqueda (posicional opcional)")
    parser.add_argument("--top", "-k", type=int, default=5, help="Máximo de resultados a retornar (default: 5)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emitir salida en formato JSON")
    args = parser.parse_args()

    query = (args.query if args.query is not None else args.query_pos) or ""
    if not query.strip():
        print("Error: Se requiere --query <texto>", file=sys.stderr)
        sys.exit(1)
    if args.top <= 0:
        print("Error: --top debe ser un entero positivo", file=sys.stderr)
        sys.exit(1)

    base_dir = resolve_base_dir(args.dir)
    report = search_memory(base_dir, query, top_k=args.top)

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    results = report["results"]
    print(
        f"[memory_search] query={query!r} | engine={report['engine']} | "
        f"files={report['files_indexed']} | hits={len(results)}"
    )
    if not results:
        print(f"Sin coincidencias en {base_dir}")
        return

    for idx, r in enumerate(results, start=1):
        conf_str = f" [confidence={r['confidence']}]" if r.get("confidence") else ""
        print(f"{idx}. {r['path']}:{r['line']}{conf_str} — {r['snippet']}")


if __name__ == "__main__":
    main()
