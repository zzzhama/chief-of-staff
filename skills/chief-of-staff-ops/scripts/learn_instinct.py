#!/usr/bin/env python3
"""
learn_instinct.py - Ciclo de auto-aprendizaje amable (estilo ECC Instincts, stdlib puro).
Previsualiza (dry-run por defecto, respetando Autonomía Amable) o persiste (--apply)
una ficha atómica (<80 líneas) en memory/<slug>.md con cabecera 'Confidence: X.XX'
compatible con memory_search.py, e indexa la entrada en MEMORY.md si no existe.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import re
import sys
import unicodedata

DEFAULT_PLUGIN_DIR = os.path.expanduser("~/.gemini/config/plugins/chief-of-staff")
MAX_CARD_LINES = 79


def slugify(text: str) -> str:
    """Convierte un título o nombre en un slug ASCII seguro para nombres de archivo."""
    norm = unicodedata.normalize("NFKD", text or "")
    ascii_text = norm.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return slug[:64] or "instinct"


def normalize_filename(title: str, file_arg: str | None) -> tuple[str, str]:
    """Determina (slug, filename.md) a partir de --file o --title."""
    if file_arg and file_arg.strip():
        base = os.path.basename(file_arg.strip())
        if base.lower().endswith(".md"):
            base = base[:-3]
        slug = slugify(base)
    else:
        slug = slugify(title)
    return slug, f"{slug}.md"


def validate_confidence(value: float) -> float:
    """Valida que confidence esté en el rango [0.1, 1.0]."""
    try:
        conf = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence debe ser un número flotante entre 0.1 y 1.0") from exc
    if conf < 0.1 or conf > 1.0:
        raise ValueError("confidence debe estar entre 0.1 y 1.0")
    return round(conf, 2)


def _clean_block(text: str, max_lines: int) -> list[str]:
    """Limpia un bloque de texto y limita su número de líneas para garantizar <80 líneas."""
    raw = (text or "").strip()
    if not raw:
        return ["- _(sin especificar)_"]
    lines = [line.rstrip() for line in raw.splitlines() if line.strip()]
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + ["..."]
    return lines


def build_instinct_card(
    title: str,
    category: str = "workflow",
    confidence: float = 0.75,
    trigger: str = "",
    rule: str = "",
    evidence: str = "",
    date_str: str | None = None,
) -> str:
    """Construye el contenido Markdown (<80 líneas) con cabecera 'Confidence: X.XX'."""
    conf = validate_confidence(confidence)
    clean_title = (title or "").strip() or "Instinct sin título"
    clean_category = (category or "workflow").strip() or "workflow"
    today = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines: list[str] = [
        f"# {clean_title}",
        f"Confidence: {conf:.2f}",
        f"Category: {clean_category}",
        f"Updated: {today}",
        "",
        "## Trigger",
        *_clean_block(trigger, max_lines=15),
        "",
        "## Rule",
        *_clean_block(rule, max_lines=25),
    ]

    if evidence and evidence.strip():
        lines.extend([
            "",
            "## Evidence",
            *_clean_block(evidence, max_lines=15),
        ])

    if len(lines) > MAX_CARD_LINES:
        lines = lines[:MAX_CARD_LINES]

    return "\n".join(lines) + "\n"


def update_memory_index(
    base_dir: str,
    rel_card_path: str,
    title: str,
    category: str,
    confidence: float,
    rule: str,
) -> tuple[str, bool]:
    """Añade la referencia de la ficha a MEMORY.md si aún no está registrada."""
    index_path = os.path.join(base_dir, "MEMORY.md")
    conf_str = f"{confidence:.2f}"
    summary = re.sub(r"\s+", " ", (rule or title).strip())
    if len(summary) > 100:
        summary = summary[:97] + "..."
    entry_line = (
        f"- **[{title.strip()}]({rel_card_path})** "
        f"(`{category.strip()}`, `Confidence: {conf_str}`): {summary}"
    )

    if os.path.isfile(index_path):
        with open(index_path, "r", encoding="utf-8", errors="replace") as f:
            existing = f.read()
        if rel_card_path in existing or os.path.basename(rel_card_path) in existing:
            return index_path, False
        content = existing.rstrip()
        if "## Instincts" not in content and "## Lecciones Aprendidas" not in content:
            content += "\n\n## Instincts & Lecciones Aprendidas\n"
        content += f"\n{entry_line}\n"
    else:
        content = (
            "# MEMORY.md — Índice de Memoria Persistente\n\n"
            "## Instincts & Lecciones Aprendidas\n"
            f"{entry_line}\n"
        )

    os.makedirs(base_dir, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(content)
    return index_path, True


def learn_instinct(
    base_dir: str,
    title: str,
    category: str = "workflow",
    confidence: float = 0.75,
    trigger: str = "",
    rule: str = "",
    evidence: str = "",
    file_name: str | None = None,
    apply: bool = False,
) -> dict:
    """Genera (dry-run) o escribe (--apply) una ficha Instinct e indexa en MEMORY.md."""
    if not title or not title.strip():
        raise ValueError("Se requiere --title no vacío")
    if not trigger or not trigger.strip():
        raise ValueError("Se requiere --trigger no vacío")
    if not rule or not rule.strip():
        raise ValueError("Se requiere --rule no vacío")

    conf = validate_confidence(confidence)
    resolved_dir = os.path.abspath(os.path.expanduser(base_dir or DEFAULT_PLUGIN_DIR))
    slug, fname = normalize_filename(title, file_name)
    rel_path = f"memory/{fname}"
    card_path = os.path.join(resolved_dir, "memory", fname)
    index_path = os.path.join(resolved_dir, "MEMORY.md")

    card_content = build_instinct_card(
        title=title,
        category=category,
        confidence=conf,
        trigger=trigger,
        rule=rule,
        evidence=evidence,
    )
    line_count = len(card_content.splitlines())
    index_updated = False

    if apply:
        os.makedirs(os.path.dirname(card_path), exist_ok=True)
        with open(card_path, "w", encoding="utf-8") as f:
            f.write(card_content)
        index_path, index_updated = update_memory_index(
            base_dir=resolved_dir,
            rel_card_path=rel_path,
            title=title,
            category=category,
            confidence=conf,
            rule=rule,
        )

    return {
        "status": "applied" if apply else "dry_run",
        "applied": bool(apply),
        "dry_run": not bool(apply),
        "title": title.strip(),
        "slug": slug,
        "category": (category or "workflow").strip(),
        "confidence": conf,
        "confidence_str": f"{conf:.2f}",
        "trigger": trigger.strip(),
        "rule": rule.strip(),
        "evidence": (evidence or "").strip(),
        "dir": resolved_dir,
        "card_path": card_path,
        "rel_path": rel_path,
        "memory_index_path": index_path,
        "memory_index_updated": index_updated,
        "line_count": line_count,
        "content": card_content,
        "courtesy_note": (
            "Autonomía Amable: confirma con el usuario antes de ejecutar con --apply "
            "para fijar este Instinct en memory/ y MEMORY.md."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ciclo de auto-aprendizaje amable (ECC Instincts) para memory/ y MEMORY.md"
    )
    parser.add_argument(
        "--dir",
        "-d",
        default=DEFAULT_PLUGIN_DIR,
        help="Directorio base que contiene MEMORY.md y memory/ (default: ~/.gemini/config/plugins/chief-of-staff)",
    )
    parser.add_argument("--title", "-t", required=True, help="Título descriptivo del Instinct")
    parser.add_argument("--category", "-c", default="workflow", help="Categoría del Instinct (default: workflow)")
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.75,
        help="Nivel de confianza entre 0.1 y 1.0 (default: 0.75)",
    )
    parser.add_argument("--trigger", required=True, help="Condición o contexto que dispara este Instinct")
    parser.add_argument("--rule", required=True, help="Acción, patrón o regla aprendida a aplicar")
    parser.add_argument("--evidence", default="", help="Evidencia o sesión que respalda el aprendizaje (opcional)")
    parser.add_argument("--file", dest="file_name", default=None, help="Nombre de archivo opcional en memory/")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persistir ficha en memory/<slug>.md y actualizar MEMORY.md (sin --apply ejecuta dry-run)",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emitir resultado en formato JSON")
    args = parser.parse_args()

    try:
        report = learn_instinct(
            base_dir=args.dir,
            title=args.title,
            category=args.category,
            confidence=args.confidence,
            trigger=args.trigger,
            rule=args.rule,
            evidence=args.evidence,
            file_name=args.file_name,
            apply=args.apply,
        )
    except ValueError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    if report["dry_run"]:
        print(
            f"[learn_instinct] DRY-RUN (vista previa) -> {report['rel_path']} "
            f"({report['line_count']} líneas | Category: {report['category']} | "
            f"Confidence: {report['confidence_str']})"
        )
        print("-" * 60)
        print(report["content"].rstrip())
        print("-" * 60)
        print(report["courtesy_note"])
    else:
        idx_state = "actualizado" if report["memory_index_updated"] else "sin cambios (ya indexado)"
        print(
            f"[learn_instinct] APPLIED -> {report['card_path']} "
            f"({report['line_count']} líneas | Confidence: {report['confidence_str']}) | "
            f"MEMORY.md: {idx_state}"
        )


if __name__ == "__main__":
    main()
