#!/usr/bin/env python3
"""
view_tokens.py - Resumen tabular y JSON de consumo de tokens, duración y costo USD
para llamadas registradas en metrics.jsonl por consult_council.py.
"""
import argparse
import glob
import json
import os
import re
import sys

DEFAULT_METRICS_PATH = os.path.expanduser("~/.gemini/config/plugins/chief-of-staff/metrics.jsonl")
DEFAULT_BRAIN_GLOB = os.path.expanduser("~/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl")

# Tarifas aproximadas (estimadas) por 1M de tokens: (input_usd, output_and_thinking_usd, cache_read_usd)
MODEL_PRICING_PER_1M = {
    "gemini-4-neon-": (3.00, 15.00, 0.15),
    "gemini-4-hydrogen-": (1.50, 7.50, 0.075),
    "gemini-4-argon-": (2.00, 12.00, 0.20),
    "gemini-3.8-flash-": (0.30, 2.50, 0.03),
    "claude-sonnet-5-5-": (3.00, 15.00, 0.30),
    "claude-opus-5-5-": (15.00, 75.00, 1.50),
}

# Familias para % Share (orden de presentación)
FAMILY_PREFIXES = [
    ("Gemini Heavy", ("gemini-4-neon-", "gemini-4-hydrogen-", "gemini-pro-orchestrator-neon")),
    ("Gemini Flash", ("gemini-3.8-flash-",)),
    ("Argon 4", ("gemini-4-argon-", "gemini-pro-orchestrator-g1-pro")),
    ("Claude 5.5", ("claude-",)),
    ("GPT-OSS", ("gpt-oss-",)),
]


def get_family(model_name: str) -> str:
    """Clasifica un modelo en su familia para el reporte de % Share."""
    for family, prefixes in FAMILY_PREFIXES:
        if any(model_name.startswith(p) for p in prefixes):
            return family
    return "Other"


def get_pricing(model_name: str) -> tuple[float, float, float] | None:
    """Devuelve la tupla de tarifas (in, out, cache) por 1M tokens si existe tarifa local."""
    for prefix, rates in MODEL_PRICING_PER_1M.items():
        if model_name.startswith(prefix):
            return rates
    return None


def compute_cost_usd(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int,
    cache_read_tokens: int,
) -> float | None:
    """Calcula costo estimado en USD para modelos con tarifa local configurada."""
    rates = get_pricing(model_name)
    if rates is None:
        return None
    in_rate, out_rate, cache_rate = rates
    cost = (
        (input_tokens * in_rate)
        + ((output_tokens + thinking_tokens) * out_rate)
        + (cache_read_tokens * cache_rate)
    ) / 1_000_000.0
    return round(cost, 6)


def load_council_records(metrics_path: str, last_n: int | None = None) -> list[dict]:
    """Carga registros de consult_council.py desde metrics.jsonl de forma tolerante."""
    if not os.path.exists(metrics_path):
        return []

    records: list[dict] = []
    with open(metrics_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            if entry.get("script") == "consult_council.py" or "model" in entry:
                records.append(entry)

    if last_n is not None and last_n > 0:
        records = records[-last_n:]
    return records


def aggregate_records(records: list[dict]) -> dict:
    """Agrupa métricas por (model, alias) y calcula totales generales."""
    groups: dict[tuple[str, str], dict] = {}
    totals = {
        "calls": 0,
        "ok": 0,
        "err": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "cache_read_tokens": 0,
        "total_tokens": 0,
        "duration_s": 0.0,
        "cost_usd": 0.0,
        "_has_priced": False,
    }

    for rec in records:
        model = str(rec.get("model") or "unknown")
        alias = str(rec.get("alias") or model)
        key = (model, alias)

        if key not in groups:
            groups[key] = {
                "model": model,
                "alias": alias,
                "calls": 0,
                "ok": 0,
                "err": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "thinking_tokens": 0,
                "cache_read_tokens": 0,
                "total_tokens": 0,
                "duration_s": 0.0,
            }

        g = groups[key]
        is_ok = str(rec.get("status", "")).upper() == "OK"
        dur = float(rec.get("duration_s") or 0.0)
        usage = rec.get("usage") if isinstance(rec.get("usage"), dict) else {}

        in_tok = int(usage.get("input_tokens", 0) or 0)
        out_tok = int(usage.get("output_tokens", 0) or 0)
        think_tok = int(usage.get("thinking_tokens", 0) or 0)
        cache_tok = int(usage.get("cache_read_tokens", 0) or 0)
        tot_tok = int(usage.get("total_tokens", 0) or 0)

        g["calls"] += 1
        g["ok"] += 1 if is_ok else 0
        g["err"] += 0 if is_ok else 1
        g["input_tokens"] += in_tok
        g["output_tokens"] += out_tok
        g["thinking_tokens"] += think_tok
        g["cache_read_tokens"] += cache_tok
        g["total_tokens"] += tot_tok
        g["duration_s"] += dur

        totals["calls"] += 1
        totals["ok"] += 1 if is_ok else 0
        totals["err"] += 0 if is_ok else 1
        totals["input_tokens"] += in_tok
        totals["output_tokens"] += out_tok
        totals["thinking_tokens"] += think_tok
        totals["cache_read_tokens"] += cache_tok
        totals["total_tokens"] += tot_tok
        totals["duration_s"] += dur

    models_summary = []
    for g in sorted(groups.values(), key=lambda x: (-x["total_tokens"], -x["calls"], x["model"])):
        g["duration_s"] = round(g["duration_s"], 3)
        cost = compute_cost_usd(
            g["model"],
            g["input_tokens"],
            g["output_tokens"],
            g["thinking_tokens"],
            g["cache_read_tokens"],
        )
        g["cost_usd"] = cost
        if cost is not None:
            totals["cost_usd"] += cost
            totals["_has_priced"] = True
        models_summary.append(g)

    totals["duration_s"] = round(totals["duration_s"], 3)
    totals["cost_usd"] = round(totals["cost_usd"], 6) if totals.pop("_has_priced") else None

    # % Share por familia (llamadas, tokens y costo estimado)
    fam: dict[str, dict] = {}
    for g in models_summary:
        name = get_family(g["model"])
        f = fam.setdefault(name, {"family": name, "calls": 0, "total_tokens": 0, "cost_usd": 0.0})
        f["calls"] += g["calls"]
        f["total_tokens"] += g["total_tokens"]
        f["cost_usd"] += g["cost_usd"] or 0.0
    order = [n for n, _ in FAMILY_PREFIXES] + ["Other"]
    families = []
    for name in order:
        if name not in fam:
            continue
        f = fam[name]
        f["cost_usd"] = round(f["cost_usd"], 6)
        f["calls_pct"] = round(100.0 * f["calls"] / totals["calls"], 1) if totals["calls"] else 0.0
        f["tokens_pct"] = round(100.0 * f["total_tokens"] / totals["total_tokens"], 1) if totals["total_tokens"] else 0.0
        f["cost_pct"] = round(100.0 * f["cost_usd"] / totals["cost_usd"], 1) if totals["cost_usd"] else 0.0
        families.append(f)

    return {"models": models_summary, "totals": totals, "families": families}


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


def audit_sessions(n_sessions: int, brain_glob: str = DEFAULT_BRAIN_GLOB) -> dict:
    """Escanea los últimos N transcripts y cuenta invoke_subagent por (TypeName, Model) vs consult_council.py."""
    files = []
    for p in glob.glob(brain_glob):
        try:
            files.append((os.path.getmtime(p), p))
        except OSError:
            continue
    files.sort(reverse=True)
    files = files[:n_sessions]

    subagents: dict[tuple[str, str], int] = {}
    council_calls = 0
    council_models: dict[str, int] = {}
    model_re = re.compile(r"(?:-m|--model)[ =]+([\w.\-]+)")

    for _, path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "invoke_subagent" not in line and "consult_council" not in line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(entry, dict):
                        continue
                    for name, a in _iter_tool_calls(entry):
                        if name.endswith("invoke_subagent"):
                            tname = str(a.get("TypeName") or "unknown").strip('"')
                            mname = str(a.get("Model") or "inherit").strip('"')
                            key = (tname, mname)
                            subagents[key] = subagents.get(key, 0) + 1
                        else:
                            cmdline = str(a.get("CommandLine") or a.get("command") or a.get("_raw") or "")
                            if "consult_council.py" in cmdline:
                                council_calls += 1
                                m = model_re.search(cmdline)
                                alias = m.group(1) if m else "claude"
                                council_models[alias] = council_models.get(alias, 0) + 1
        except OSError:
            continue

    rows = [
        {"type_name": t, "model": m, "invocations": c}
        for (t, m), c in sorted(subagents.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "sessions_scanned": len(files),
        "subagent_invocations": sum(subagents.values()),
        "subagents": rows,
        "council_calls": council_calls,
        "council_by_model": dict(sorted(council_models.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def print_subagent_audit(audit: dict) -> None:
    """Imprime la tabla Subagent & Council Balance."""
    print()
    print(f"Subagent & Council Balance (Last {audit['sessions_scanned']} sessions)")
    rows = [["TypeName", "Model", "Invocations"]]
    for r in audit["subagents"]:
        rows.append([r["type_name"], r["model"], str(r["invocations"])])
    rows.append(["consult_council.py", "(all)", str(audit["council_calls"])])
    for alias, c in audit["council_by_model"].items():
        rows.append(["  council -m", alias, str(c)])
    widths = [max(len(r[i]) for r in rows) for i in range(3)]

    def fmt(r: list[str]) -> str:
        return f"{r[0]:<{widths[0]}} | {r[1]:<{widths[1]}} | {r[2]:>{widths[2]}}"

    print(fmt(rows[0]))
    print("-+-".join("-" * w for w in widths))
    for r in rows[1:]:
        print(fmt(r))
    total = audit["subagent_invocations"]
    print(f"Total subagents: {total} | Council calls: {audit['council_calls']}")


def format_cost(cost_usd: float | None) -> str:
    """Formatea costo USD o N/A si no aplica tarifa local."""
    if cost_usd is None:
        return "N/A"
    return f"${cost_usd:.4f}"


def print_table(summary: dict, metrics_path: str, last_n: int | None) -> None:
    """Imprime tabla legible en stdout."""
    rows = summary["models"]
    totals = summary["totals"]

    if not rows:
        scope = f" (últimas {last_n})" if last_n else ""
        print(f"Sin registros de consult_council.py{scope} en {metrics_path}")
        return

    headers = ["Model (Alias)", "Calls", "OK/ERR", "Input", "Output", "Think", "Cache", "Total", "Dur(s)", "Est.USD"]
    table_rows = []
    for r in rows:
        label = r["model"] if r["alias"] == r["model"] else f"{r['model']} ({r['alias']})"
        table_rows.append([
            label,
            str(r["calls"]),
            f"{r['ok']}/{r['err']}",
            f"{r['input_tokens']:,}",
            f"{r['output_tokens']:,}",
            f"{r['thinking_tokens']:,}",
            f"{r['cache_read_tokens']:,}",
            f"{r['total_tokens']:,}",
            f"{r['duration_s']:.2f}",
            format_cost(r["cost_usd"]),
        ])

    total_row = [
        "TOTAL",
        str(totals["calls"]),
        f"{totals['ok']}/{totals['err']}",
        f"{totals['input_tokens']:,}",
        f"{totals['output_tokens']:,}",
        f"{totals['thinking_tokens']:,}",
        f"{totals['cache_read_tokens']:,}",
        f"{totals['total_tokens']:,}",
        f"{totals['duration_s']:.2f}",
        format_cost(totals["cost_usd"]),
    ]

    all_rows = [headers, *table_rows, total_row]
    widths = [max(len(row[i]) for row in all_rows) for i in range(len(headers))]

    def fmt_row(row: list[str]) -> str:
        parts = [f"{row[0]:<{widths[0]}}"]
        for i in range(1, len(row)):
            parts.append(f"{row[i]:>{widths[i]}}")
        return " | ".join(parts)

    sep = "-+-".join("-" * w for w in widths)
    print(fmt_row(headers))
    print(sep)
    for row in table_rows:
        print(fmt_row(row))
    print(sep)
    print(fmt_row(total_row))

    families = summary.get("families") or []
    if families:
        print()
        print("% Share por familia (estimado)")
        fh = ["Family", "Calls", "Calls%", "Tokens", "Tokens%", "Est.USD", "Cost%"]
        frows = [fh]
        for f in families:
            frows.append([
                f["family"], str(f["calls"]), f"{f['calls_pct']:.1f}%",
                f"{f['total_tokens']:,}", f"{f['tokens_pct']:.1f}%",
                f"${f['cost_usd']:.4f}", f"{f['cost_pct']:.1f}%",
            ])
        fw = [max(len(r[i]) for r in frows) for i in range(len(fh))]
        def ffmt(r: list[str]) -> str:
            return " | ".join([f"{r[0]:<{fw[0]}}"] + [f"{r[i]:>{fw[i]}}" for i in range(1, len(r))])
        print(ffmt(fh))
        print("-+-".join("-" * w for w in fw))
        for r in frows[1:]:
            print(ffmt(r))


def main() -> None:
    parser = argparse.ArgumentParser(description="Visor de telemetría y consumo de tokens (metrics.jsonl)")
    parser.add_argument("--last", type=int, default=None, help="Analizar solo las últimas N llamadas")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emitir resumen en formato JSON")
    parser.add_argument("--sessions", type=int, default=20,
                        help="Escanear los últimos N transcripts para auditar subagentes vs consejo (default 20; 0 desactiva)")
    args = parser.parse_args()

    if args.last is not None and args.last <= 0:
        print("Error: --last debe ser un entero positivo", file=sys.stderr)
        sys.exit(1)
    if args.sessions < 0:
        print("Error: --sessions debe ser >= 0", file=sys.stderr)
        sys.exit(1)

    metrics_path = os.environ.get("COS_METRICS_PATH", DEFAULT_METRICS_PATH)
    records = load_council_records(metrics_path, args.last)
    summary = aggregate_records(records)
    audit = audit_sessions(args.sessions) if args.sessions > 0 else None

    if args.as_json:
        out = {"metrics_path": metrics_path, "last": args.last, **summary}
        if audit is not None:
            out["subagent_audit"] = audit
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_table(summary, metrics_path, args.last)
        if audit is not None:
            print_subagent_audit(audit)


if __name__ == "__main__":
    main()
