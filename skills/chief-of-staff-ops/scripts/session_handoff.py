#!/usr/bin/env python3
"""
session_handoff.py - Compresor Estratégico de Contexto y Generador de HANDOFF_CONTEXT (ECC strategic-compact).
Analiza transcript.jsonl (stdlib puro), cuenta turnos PLANNER_RESPONSE, mide input_tokens/output_tokens
del último turno frente a --threshold, extrae el último <USER_REQUEST> o USER_INPUT limpio y recopila
archivos tocados en tool_calls (write_file, edit_file).
"""
import argparse
import glob
import json
import os
import re
import sys

DEFAULT_BRAIN_GLOB = os.path.expanduser(
    "~/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl"
)
DEFAULT_CLI_BRAIN_GLOB = os.path.expanduser(
    "~/.gemini/antigravity-cli/brain/*/.system_generated/logs/transcript.jsonl"
)
DEFAULT_THRESHOLD = 120_000

USER_REQUEST_RE = re.compile(
    r"<USER_REQUEST>(.*?)(?:</USER_REQUEST>|$)",
    re.DOTALL | re.IGNORECASE,
)
STRIP_BLOCKS_RE = re.compile(
    r"<(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE)>.*?(?:</(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE)>|$)",
    re.DOTALL | re.IGNORECASE,
)


def find_latest_transcript(brain_glob: str = DEFAULT_BRAIN_GLOB) -> str | None:
    """Encuentra el último transcript.jsonl por mtime usando el glob por defecto."""
    candidates = [p for p in glob.glob(brain_glob) if os.path.isfile(p)]
    if not candidates and brain_glob == DEFAULT_BRAIN_GLOB:
        candidates = [p for p in glob.glob(DEFAULT_CLI_BRAIN_GLOB) if os.path.isfile(p)]
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def _iter_tool_calls(entry: dict):
    """Itera tool_calls de un paso del transcript de forma tolerante a variaciones de formato."""
    calls = entry.get("tool_calls")
    if not isinstance(calls, list):
        return
    for call in calls:
        if not isinstance(call, dict):
            continue
        fn = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = call.get("name") or call.get("tool_name") or call.get("tool") or fn.get("name") or ""
        raw_args = call.get("args")
        if raw_args is None:
            raw_args = call.get("arguments")
        if raw_args is None:
            raw_args = call.get("input")
        if raw_args is None:
            raw_args = fn.get("arguments")
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except (json.JSONDecodeError, ValueError):
                raw_args = {"_raw": raw_args}
        if not isinstance(raw_args, dict):
            raw_args = {}
        yield str(name), raw_args


def extract_clean_user_request(content: object) -> str:
    """Extrae el texto limpio de <USER_REQUEST> o de un USER_INPUT sin bloques de sistema."""
    if not isinstance(content, str) or not content.strip():
        return ""
    m = USER_REQUEST_RE.search(content)
    if m:
        cleaned = m.group(1).strip()
        if cleaned:
            return cleaned
    cleaned = STRIP_BLOCKS_RE.sub("", content)
    cleaned = re.sub(r"</?USER_REQUEST>", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def classify_status(tokens: int, threshold: int) -> tuple[str, str, float]:
    """Clasifica el estado de contexto frente al threshold (<70% OK, 70-99% COMPACTAR, >=100% NUEVO)."""
    eff_threshold = max(1, int(threshold))
    pct = round((tokens / eff_threshold) * 100.0, 1)
    if tokens >= eff_threshold:
        return "🔴 ABRIR CHAT NUEVO", "critical", pct
    if tokens >= (eff_threshold * 0.70):
        return "🟡 COMPACTAR PRONTO", "warn", pct
    return "🟢 OK", "ok", pct


def build_handoff_context(report: dict) -> str:
    """Construye un bloque HANDOFF_CONTEXT compacto (<35 líneas) listo para copiar a una sesión limpia."""
    lines: list[str] = [
        "# HANDOFF_CONTEXT",
        f"Estado: {report['status']} ({report['usage_pct']:.1f}% de {report['threshold']:,} tokens)",
        f"Tokens último turno: input={report['input_tokens']:,} | output={report['output_tokens']:,} | total={report['total_tokens']:,}",
        f"Turnos PLANNER_RESPONSE: {report['planner_turns']}",
        f"Transcript: {report['transcript_path'] or 'N/A'}",
        "",
        "## Objetivo Activo",
    ]
    objective = (report.get("last_user_request") or "").strip()
    if objective:
        obj_lines = [ln.strip() for ln in objective.splitlines() if ln.strip()]
        for ln in obj_lines[:8]:
            lines.append(ln[:160])
        if len(obj_lines) > 8:
            lines.append(f"... (+{len(obj_lines) - 8} líneas adicionales)")
    else:
        lines.append("(Sin USER_REQUEST detectado)")

    lines.append("")
    lines.append("## Archivos Tocados (write_file / edit_file)")
    touched = report.get("touched_files") or []
    if touched:
        for path in touched[:10]:
            lines.append(f"- {path}")
        if len(touched) > 10:
            lines.append(f"- ... (+{len(touched) - 10} archivo(s) más)")
    else:
        lines.append("- (Ninguno)")

    return "\n".join(lines[:34])


def analyze_transcript(transcript_path: str | None, threshold: int = DEFAULT_THRESHOLD) -> dict:
    """Analiza un archivo transcript.jsonl y devuelve métricas, estado y HANDOFF_CONTEXT."""
    planner_turns = 0
    last_input_tokens = 0
    last_output_tokens = 0
    last_user_request = ""
    touched_files: list[str] = []

    if transcript_path and os.path.isfile(transcript_path):
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue

                entry_type = str(entry.get("type") or "").strip().upper()
                entry_source = str(entry.get("source") or "").strip().upper()
                if entry_type == "PLANNER_RESPONSE":
                    planner_turns += 1

                usage = entry.get("usage") if isinstance(entry.get("usage"), dict) else {}
                raw_in = entry.get("input_tokens") if entry.get("input_tokens") is not None else usage.get("input_tokens")
                raw_cache = entry.get("cache_read_tokens") if entry.get("cache_read_tokens") is not None else usage.get("cache_read_tokens")
                raw_out = entry.get("output_tokens") if entry.get("output_tokens") is not None else usage.get("output_tokens")
                if raw_in is not None or raw_cache is not None or raw_out is not None:
                    in_tok = int(raw_in or 0) + int(raw_cache or 0)
                    out_tok = int(raw_out or 0)
                    if in_tok > 0 or out_tok > 0 or entry_type in ("PLANNER_RESPONSE", "MODEL"):
                        last_input_tokens = in_tok
                        last_output_tokens = out_tok

                content = entry.get("content")
                if entry_type == "USER_INPUT" or entry_source == "USER_EXPLICIT":
                    cleaned_req = extract_clean_user_request(content)
                    if cleaned_req:
                        last_user_request = cleaned_req

                for tool_name, tool_args in _iter_tool_calls(entry):
                    base_tool = tool_name.split(":")[-1].strip().lower()
                    if base_tool in ("write_file", "edit_file"):
                        raw_path = (
                            tool_args.get("Path")
                            or tool_args.get("path")
                            or tool_args.get("file_path")
                            or tool_args.get("filepath")
                            or tool_args.get("target_file")
                        )
                        if raw_path:
                            clean_path = str(raw_path).strip().strip('"').strip("'")
                            if clean_path and clean_path not in touched_files:
                                touched_files.append(clean_path)

    total_tokens = last_input_tokens + last_output_tokens
    eval_tokens = last_input_tokens if last_input_tokens >= threshold else total_tokens
    status_label, status_level, usage_pct = classify_status(eval_tokens, threshold)

    report: dict = {
        "transcript_path": transcript_path,
        "planner_turns": planner_turns,
        "input_tokens": last_input_tokens,
        "output_tokens": last_output_tokens,
        "total_tokens": total_tokens,
        "threshold": int(threshold),
        "usage_pct": usage_pct,
        "status": status_label,
        "status_level": status_level,
        "last_user_request": last_user_request,
        "touched_files": touched_files,
    }
    handoff_context = build_handoff_context(report)
    report["handoff_context"] = handoff_context
    report["line_count"] = len(handoff_context.splitlines())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analizador de presión de contexto y generador de HANDOFF_CONTEXT (ECC strategic-compact)"
    )
    parser.add_argument(
        "--transcript",
        default=None,
        help="Ruta a transcript.jsonl (default: último de ~/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help=f"Umbral de tokens para recomendar chat nuevo (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument("--out", default=None, help="Guardar HANDOFF_CONTEXT en archivo destino")
    parser.add_argument("--json", action="store_true", help="Emitir resultado en formato JSON")
    args = parser.parse_args()

    transcript_path = os.path.expanduser(args.transcript) if args.transcript else find_latest_transcript()
    report = analyze_transcript(transcript_path, threshold=args.threshold)

    if args.out:
        out_path = os.path.abspath(os.path.expanduser(args.out))
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report["handoff_context"] + "\n")

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(report["handoff_context"])


if __name__ == "__main__":
    main()
