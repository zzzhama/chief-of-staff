#!/usr/bin/env python3
"""
consult_council.py - Convocatoria al Consejo Multi-Modelo de Antigravity (v4.5 Agéntico + JSON & Tokens)
Características:
1. Timeout extendido a 240s (pasado también a agy como --print-timeout).
2. Protección ARG_MAX: prompts > 100000 caracteres se referencian vía archivo temporal.
3. Telegrama Inteligente (Head + Tail) con línea de tokens.
4. Telemetría JSONL best-effort en metrics.jsonl (mode, agent, sandbox, denied_count, conversation_id, usage).
5. Soporte agéntico: --agent, --mode, --exec, --dir/--add-dir, --sandbox, --effort, --isolated, --yolo, --allow-cmd.
6. Detección de acciones denegadas (status DENIED, exit code 3).
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

DEFAULT_METRICS_PATH = os.path.expanduser("~/.gemini/config/plugins/chief-of-staff/metrics.jsonl")
COUNCIL_DIR = "/tmp/agy_council"
ARG_MAX_CHARS = 100000

MODEL_ALIASES = {
    "neon": "gemini-4-neon-high",
    "neon-xhigh": "gemini-4-neon-xhigh",
    "neon-med": "gemini-4-neon-medium",
    "neon-low": "gemini-4-neon-low",
    "orch-neon": "gemini-pro-orchestrator-neon",
    "hydrogen": "gemini-4-hydrogen-high",
    "hydrogen-xhigh": "gemini-4-hydrogen-xhigh",
    "hydrogen-med": "gemini-4-hydrogen-medium",
    "hydrogen-low": "gemini-4-hydrogen-low",
    "argon": "gemini-4-argon-high",
    "argon-med": "gemini-4-argon-medium",
    "argon-low": "gemini-4-argon-low",
    "orch-argon": "gemini-pro-orchestrator-g1-pro",
    "flash": "gemini-3.8-flash-high",
    "flash-med": "gemini-3.8-flash-medium",
    "flash-low": "gemini-3.8-flash-low",
    "claude": "claude-sonnet-5-5-high",
    "claude-sonnet": "claude-sonnet-5-5-high",
    "claude-sonnet-med": "claude-sonnet-5-5-medium",
    "claude-sonnet-low": "claude-sonnet-5-5-low",
    "claude-opus": "claude-opus-5-5-high",
    "claude-opus-med": "claude-opus-5-5-medium",
    "claude-opus-low": "claude-opus-5-5-low",
    "gpt": "gpt-oss-120b-medium",
}

TASK_CHOICES = ["code", "plan", "ui", "qa", "sec", "recon", "opinion"]

AGENT_TASK_MAP: dict[str, str] = {
    "worker-builder": "code",
    "mentor-architect": "plan",
    "frontend-crafter": "ui",
    "qa-auditor": "qa",
    "cyber-auditor": "sec",
    "recon-scout": "recon",
}

TASK_PRIORITY_CHAINS: dict[str, list[str]] = {
    "code": ["claude", "argon", "hydrogen", "neon", "flash"],
    "plan": ["argon", "hydrogen", "neon", "gpt", "flash"],
    "ui": ["argon", "hydrogen", "flash"],
    "qa": ["claude", "argon", "hydrogen", "flash"],
    "sec": ["claude", "argon", "hydrogen", "flash"],
    "recon": ["flash", "hydrogen", "argon"],
    "opinion": ["gpt", "argon", "hydrogen", "claude"],
}

QUOTA_ERROR_PATTERNS = (
    "429",
    "rate limit",
    "rate_limit",
    "ratelimit",
    "quota",
    "exhausted",
    "resource_exhausted",
    "capacity",
    "overloaded",
    "limit reached",
)


def infer_task(task: str | None, agent: str | None) -> str:
    """Infiere el tipo de tarea desde --task o --agent (default: 'code')."""
    if task and task.strip().lower() in TASK_PRIORITY_CHAINS:
        return task.strip().lower()
    if agent:
        norm_agent = agent.strip().lower()
        if norm_agent in AGENT_TASK_MAP:
            return AGENT_TASK_MAP[norm_agent]
    return "code"


def is_quota_or_rate_limit_error(text: str) -> bool:
    """Detecta si un mensaje de error de agy corresponde a cuota o rate-limit."""
    low = (text or "").lower()
    return any(pat in low for pat in QUOTA_ERROR_PATTERNS)


def _load_view_tokens_module():
    """Importa view_tokens.py desde el mismo directorio de scripts."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import view_tokens  # type: ignore

    return view_tokens


HEALTH_WINDOW_HOURS = 2
UNHEALTHY_CONSECUTIVE_FAILS = 3
FAILURE_STATUSES = {"ERROR", "TIMEOUT", "DENIED"}


def count_recent_consecutive_failures(
    records_recent: list[dict],
    alias: str,
    model_name: str,
) -> int:
    """Cuenta fallos consecutivos recientes (ERROR/TIMEOUT/DENIED) para un candidato desde su último registro."""
    norm_alias = alias.strip().lower()
    norm_model = model_name.strip().lower()
    consecutive = 0
    for rec in reversed(records_recent):
        rec_model = str(rec.get("model") or "").strip().lower()
        rec_alias = str(rec.get("alias") or "").strip().lower()
        if rec_model != norm_model and rec_alias != norm_alias:
            continue
        status = str(rec.get("status") or "").strip().upper()
        if status in FAILURE_STATUSES:
            consecutive += 1
        else:
            break
    return consecutive


def resolve_auto_route(
    task: str,
    metrics_path: str | None = None,
    quota_file: str | None = None,
) -> dict:
    """Calcula el candidato óptimo para `task` consultando cuota (1d/7d) y health-score reciente (2h)."""
    norm_task = task if task in TASK_PRIORITY_CHAINS else "code"
    candidates = list(TASK_PRIORITY_CHAINS[norm_task])
    vt = _load_view_tokens_module()

    resolved_metrics = os.path.abspath(
        metrics_path or os.environ.get("COS_METRICS_PATH") or vt.DEFAULT_METRICS_PATH
    )
    resolved_quota = quota_file or os.environ.get("COS_QUOTA_FILE") or vt.DEFAULT_QUOTA_PATH

    now_utc = datetime.now(timezone.utc)
    rec_2h = vt.load_council_records(resolved_metrics, since_dt=now_utc - timedelta(hours=HEALTH_WINDOW_HOURS))
    rec_1d = vt.load_council_records(resolved_metrics, since_dt=now_utc - timedelta(days=1))
    rec_7d = vt.load_council_records(resolved_metrics, since_dt=now_utc - timedelta(days=7))
    q_1d = vt.compute_quota_report(vt.aggregate_records(rec_1d), None, 1, resolved_quota)
    q_7d = vt.compute_quota_report(vt.aggregate_records(rec_7d), None, 7, resolved_quota)

    pct_1d = {r["family"]: float(r["used_pct"]) for r in q_1d.get("families", [])}
    pct_7d = {r["family"]: float(r["used_pct"]) for r in q_7d.get("families", [])}

    evaluated: list[dict] = []
    for idx, alias in enumerate(candidates):
        model_name = MODEL_ALIASES.get(alias, alias)
        family = vt.get_family(model_name)
        u1 = pct_1d.get(family, 0.0)
        u7 = pct_7d.get(family, 0.0)
        consec_fails = count_recent_consecutive_failures(rec_2h, alias, model_name)
        is_healthy = consec_fails < UNHEALTHY_CONSECUTIVE_FAILS
        evaluated.append({
            "idx": idx,
            "alias": alias,
            "model": model_name,
            "family": family,
            "pct_1d": u1,
            "pct_7d": u7,
            "max_pct": max(u1, u7),
            "under_threshold": (u1 < 85.0 and u7 < 85.0),
            "consecutive_failures": consec_fails,
            "healthy": is_healthy,
        })

    def _describe_skip(s: dict) -> str:
        if not s["healthy"]:
            return (
                f"{s['alias']} (unhealthy: {s['consecutive_failures']} consecutive failures "
                f"in {HEALTH_WINDOW_HOURS}h)"
            )
        return f"{s['alias']} ({s['family']} 1d={s['pct_1d']:.1f}%/7d={s['pct_7d']:.1f}% >=85%)"

    healthy_under = [e for e in evaluated if e["healthy"] and e["under_threshold"]]
    healthy_over = sorted(
        [e for e in evaluated if e["healthy"] and not e["under_threshold"]],
        key=lambda e: (e["max_pct"], e["idx"]),
    )
    unhealthy_under = [e for e in evaluated if not e["healthy"] and e["under_threshold"]]
    unhealthy_over = sorted(
        [e for e in evaluated if not e["healthy"] and not e["under_threshold"]],
        key=lambda e: (e["max_pct"], e["idx"]),
    )

    ordered_entries = healthy_under + healthy_over + unhealthy_under + unhealthy_over
    ordered_aliases = [e["alias"] for e in ordered_entries]

    if healthy_under:
        chosen = healthy_under[0]
        skipped = [e for e in evaluated[:chosen["idx"]] if not (e["healthy"] and e["under_threshold"])]
        if not skipped:
            reason = (
                f"primary '{chosen['alias']}' ({chosen['family']}) <85% quota "
                f"(1d={chosen['pct_1d']:.1f}%, 7d={chosen['pct_7d']:.1f}%)"
            )
        else:
            skipped_desc = ", ".join(_describe_skip(s) for s in skipped)
            reason = (
                f"rotated from {skipped_desc} to '{chosen['alias']}' "
                f"({chosen['family']} 1d={chosen['pct_1d']:.1f}%/7d={chosen['pct_7d']:.1f}% <85%)"
            )
    elif healthy_over:
        chosen = healthy_over[0]
        unhealthy_skipped = [e for e in evaluated if not e["healthy"]]
        prefix = (
            f"penalized {', '.join(_describe_skip(s) for s in unhealthy_skipped)}; "
            if unhealthy_skipped
            else ""
        )
        reason = (
            f"{prefix}all candidates >=85% quota; selected lowest usage '{chosen['alias']}' "
            f"({chosen['family']} 1d={chosen['pct_1d']:.1f}%/7d={chosen['pct_7d']:.1f}%)"
        )
    else:
        chosen = ordered_entries[0]
        reason = (
            f"all candidates unhealthy (>={UNHEALTHY_CONSECUTIVE_FAILS} consecutive failures "
            f"in {HEALTH_WINDOW_HOURS}h); fallback to '{chosen['alias']}'"
        )

    return {
        "task": norm_task,
        "selected_alias": chosen["alias"],
        "selected_model": chosen["model"],
        "candidates": candidates,
        "ordered_candidates": ordered_aliases,
        "reason": reason,
    }


def ensure_council_dir() -> None:
    """Crea /tmp/agy_council con permisos 0o700 (best-effort, también corrige permisos existentes)."""
    try:
        os.makedirs(COUNCIL_DIR, mode=0o700, exist_ok=True)
        os.chmod(COUNCIL_DIR, 0o700)
    except Exception:
        pass


def log_telemetry(
    ts: str,
    alias: str,
    model: str,
    duration_s: float,
    status: str,
    exit_code: int,
    usage: dict | None = None,
    mode: str | None = None,
    agent: str | None = None,
    sandbox: bool | None = None,
    denied_count: int | None = None,
    conversation_id: str | None = None,
    fallback_from: str | None = None,
) -> None:
    """Registra telemetría de ejecución en metrics.jsonl de forma best-effort (fail-safe)."""
    try:
        metrics_file = os.path.abspath(os.environ.get("COS_METRICS_PATH", DEFAULT_METRICS_PATH))
        os.makedirs(os.path.dirname(metrics_file), exist_ok=True)
        payload: dict = {
            "ts": ts,
            "script": "consult_council.py",
            "alias": alias,
            "model": model,
            "duration_s": duration_s,
            "status": status,
            "exit_code": exit_code,
        }
        if mode:
            payload["mode"] = mode
        if agent:
            payload["agent"] = agent
        if sandbox:
            payload["sandbox"] = True
        if denied_count:
            payload["denied_count"] = denied_count
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if fallback_from:
            payload["fallback_from"] = fallback_from
        if usage is not None:
            payload["usage"] = usage
        with open(metrics_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def parse_agy_output(raw_stdout: str, elapsed_s: float) -> dict:
    """Parsea la salida JSON de `agy --output-format json` con fallback seguro a texto plano.

    Devuelve dict con: response, duration_s, usage, conversation_id, agy_status, denied_actions, is_json.
    """
    result: dict = {
        "response": raw_stdout,
        "duration_s": elapsed_s,
        "usage": None,
        "conversation_id": None,
        "agy_status": None,
        "denied_actions": [],
        "is_json": False,
    }
    try:
        data = json.loads(raw_stdout)
        if not isinstance(data, dict) or ("response" not in data and "usage" not in data and "status" not in data):
            return result

        result["is_json"] = True
        result["response"] = str(data.get("response") or "").strip()
        raw_dur = data.get("duration_seconds")
        if isinstance(raw_dur, (int, float)):
            result["duration_s"] = round(float(raw_dur), 3)

        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            result["usage"] = {
                "input_tokens": int(raw_usage.get("input_tokens", 0) or 0),
                "output_tokens": int(raw_usage.get("output_tokens", 0) or 0),
                "thinking_tokens": int(raw_usage.get("thinking_tokens", 0) or 0),
                "cache_read_tokens": int(raw_usage.get("cache_read_tokens", 0) or 0),
                "total_tokens": int(raw_usage.get("total_tokens", 0) or 0),
            }

        conv = data.get("conversation_id") or data.get("conversationId")
        result["conversation_id"] = str(conv) if conv else None
        status = data.get("status") or data.get("agy_status")
        result["agy_status"] = str(status) if status else None

        denied = data.get("denied_actions")
        if not denied:
            denied = data.get("permission_denials")
        if isinstance(denied, list):
            result["denied_actions"] = denied
        elif denied:
            result["denied_actions"] = [denied]
        return result
    except (json.JSONDecodeError, TypeError, ValueError):
        return result


def format_denied_action(action) -> str:
    """Convierte una acción denegada (dict/str) en una línea corta legible."""
    if isinstance(action, dict):
        tool = action.get("tool") or action.get("tool_name") or action.get("name") or action.get("action") or "?"
        detail = (
            action.get("command")
            or action.get("path")
            or action.get("input")
            or action.get("reason")
            or action.get("args")
            or ""
        )
        if not isinstance(detail, str):
            detail = json.dumps(detail, ensure_ascii=False)
        return f"{tool}: {detail}".strip().replace("\n", " ")[:200]
    return str(action).replace("\n", " ")[:200]


def format_token_line(usage: dict | None) -> str | None:
    """Formatea la línea resumen de tokens si hay datos de uso."""
    if not usage:
        return None
    return (
        f"📊 Tokens: in={usage['input_tokens']} | out={usage['output_tokens']} | "
        f"think={usage['thinking_tokens']} | cache={usage['cache_read_tokens']} | "
        f"total={usage['total_tokens']}"
    )


def smart_telegram(
    lines: list[str],
    max_lines: int,
    out_path: str,
    model_name: str,
    token_line: str | None = None,
) -> str:
    """Extrae cabecera + veredicto final respetando max_lines e incluyendo tokens."""
    reserved = 1 if token_line else 0
    body_budget = max(4, max_lines - 1 - reserved)

    if len(lines) <= body_budget:
        res = [f"[{model_name}]:", *lines]
        if token_line:
            res.append(token_line)
        return "\n".join(res)

    head_count = min(3, max(1, body_budget // 3))
    tail_count = max(1, body_budget - head_count - 2)
    head_lines = lines[:head_count]
    tail_lines = lines[-tail_count:]
    omitted = len(lines) - (head_count + tail_count)

    res = [f"[{model_name}] (Telegrama Inteligente - {len(lines)} líneas totales):"]
    res.extend(head_lines)
    res.append(f"... [{omitted} líneas intermedias omitidas. Conclusión/Veredicto:] ...")
    res.extend(tail_lines)
    res.append(f"⚡ Traza completa guardada en: {out_path}")
    if token_line:
        res.append(token_line)
    return "\n".join(res)


def list_models() -> None:
    """Imprime la tabla de alias -> modelo disponible."""
    width = max(len(k) for k in MODEL_ALIASES) + 2
    for alias, model in MODEL_ALIASES.items():
        print(f"{alias:<{width}} -> {model}")


def main():
    start_time = time.time()
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    parser = argparse.ArgumentParser(description="Consulta al Consejo Multi-Modelo de Antigravity")
    parser.add_argument("-m", "--model", default="claude", help="Alias o nombre del modelo ('auto' para auto-ruteo; --list-models para ver todos)")
    parser.add_argument("--task", choices=TASK_CHOICES, default=None,
                        help="Tipo de tarea para auto-ruteo (-m auto) o cadena de fallback")
    parser.add_argument("--auto-fallback", action="store_true",
                        help="Reintentar automáticamente con el siguiente modelo de la cadena ante errores de cuota/rate-limit")
    parser.add_argument("--dry-run-route", action="store_true",
                        help="Imprimir ruta de modelo calculada por cuota en JSON 1-línea y salir 0")
    parser.add_argument("--list-models", action="store_true", help="Listar todos los alias -> modelo disponibles y salir")
    parser.add_argument("--check-env", action="store_true", help="Verificar disponibilidad de agy y COS_PROFILE (JSON 1-línea)")
    parser.add_argument("-p", "--prompt", help="Texto del prompt")
    parser.add_argument("-f", "--file", help="Ruta de archivo con el prompt")
    parser.add_argument("-o", "--out", help="Ruta de salida para respuesta completa")
    parser.add_argument("-l", "--max-lines", type=int, default=12, help="Límite de líneas en stdout (Telegrama)")
    parser.add_argument("-t", "--timeout", type=int, default=240, help="Timeout en segundos (default 240s)")
    # Soporte agéntico
    parser.add_argument("--agent", default=None, help="Nombre de agente agy (pasado como --agent <name>)")
    parser.add_argument("--mode", choices=["plan", "accept-edits", "auto"], default="plan",
                        help="Modo de permisos de agy (default: plan)")
    parser.add_argument("--exec", action="store_true", dest="exec_mode",
                        help="Atajo: si --mode es plan, lo cambia a accept-edits")
    parser.add_argument("--dir", "--add-dir", dest="add_dirs", action="append", default=[],
                        help="Directorio extra accesible para agy (repetible; --add-dir <dir>)")
    parser.add_argument("--sandbox", action="store_true", help="Ejecutar agy con --sandbox")
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], default=None,
                        help="Nivel de esfuerzo de razonamiento (--effort)")
    parser.add_argument("--isolated", action="store_true",
                        help="Ejecuta en cwd=/tmp/agy_council con --disable-slash-commands")
    parser.add_argument("--yolo", action="store_true",
                        help="Pasa --dangerously-skip-permissions (solo si se pide explícitamente; útil con --sandbox)")
    parser.add_argument("--allow-cmd", dest="allow_cmds", action="append", default=[],
                        help="Comando permitido (repetible); arma --settings con permissions.allow command(<cmd>)")
    args = parser.parse_args()

    if args.list_models:
        list_models()
        sys.exit(0)

    resolved_task = infer_task(args.task, args.agent)
    if args.dry_run_route:
        route = resolve_auto_route(resolved_task)
        dry_out = {
            "task": route["task"],
            "selected_alias": route["selected_alias"],
            "selected_model": route["selected_model"],
            "candidates": route["candidates"],
            "reason": route["reason"],
        }
        print(json.dumps(dry_out, ensure_ascii=False))
        sys.exit(0)

    profile = os.environ.get("COS_PROFILE", "council").strip().lower()
    agy_path = shutil.which("agy")
    if args.check_env:
        mode = "student-lite" if (profile == "lite" or not agy_path) else "council"
        info = {"mode": mode, "cos_profile": profile, "agy_available": bool(agy_path), "agy_path": agy_path,
                "aliases": list(MODEL_ALIASES.keys()) if agy_path else []}
        print(json.dumps(info, ensure_ascii=False))
        sys.exit(0)

    if profile == "lite" or not agy_path:
        reason = "COS_PROFILE=lite" if profile == "lite" else "binario 'agy' no disponible"
        print(f"ℹ️ Modo Student Lite ({reason}): usa invoke_subagent con Model='flash' o 'flash_lite' en lugar de consult_council.py.")
        sys.exit(2)

    if args.exec_mode and args.mode == "plan":
        args.mode = "accept-edits"

    is_auto_model = args.model.strip().lower() == "auto"
    if is_auto_model:
        route = resolve_auto_route(resolved_task)
        attempt_aliases = list(route["ordered_candidates"])
    elif args.auto_fallback:
        base_alias = args.model.strip().lower()
        chain = TASK_PRIORITY_CHAINS.get(resolved_task, TASK_PRIORITY_CHAINS["code"])
        attempt_aliases = [args.model] + [c for c in chain if c != base_alias]
    else:
        attempt_aliases = [args.model]

    alias = attempt_aliases[0]
    model_name = MODEL_ALIASES.get(alias.lower(), alias)
    fallback_from: str | None = None

    def tlog(duration_s, status, exit_code, usage=None, denied_count=None, conversation_id=None):
        log_telemetry(
            ts, alias, model_name, duration_s, status, exit_code,
            usage=usage,
            mode=args.mode,
            agent=args.agent,
            sandbox=args.sandbox,
            denied_count=denied_count,
            conversation_id=conversation_id,
            fallback_from=fallback_from,
        )

    prompt_text = ""
    if args.file and os.path.exists(args.file):
        with open(args.file, "r", encoding="utf-8") as f:
            prompt_text = f.read().strip()
    elif args.prompt:
        prompt_text = args.prompt.strip()
    elif not sys.stdin.isatty():
        prompt_text = sys.stdin.read().strip()

    if not prompt_text:
        print("Error: Se requiere un prompt (-p, -f o stdin)", file=sys.stderr)
        tlog(round(time.time() - start_time, 3), "ERROR", 1)
        sys.exit(1)

    # Protección ARG_MAX para prompts gigantes
    prompt_tmp = None
    if len(prompt_text) > ARG_MAX_CHARS:
        fd, prompt_tmp = tempfile.mkstemp(prefix="council_prompt_", suffix=".md")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(prompt_text)
        cli_prompt = f"Por favor lee atentamente y responde según las instrucciones contenidas en el archivo: {prompt_tmp}"
    else:
        cli_prompt = prompt_text

    def build_cmd(target_model: str) -> tuple[list[str], str | None]:
        c = [
            "agy", "--model", target_model,
            "--output-format", "json",
            "--print-timeout", f"{args.timeout}s",
            "--mode", args.mode,
        ]
        if args.agent:
            c += ["--agent", args.agent]
        for d in args.add_dirs:
            c += ["--add-dir", d]
        if prompt_tmp:
            c += ["--add-dir", os.path.dirname(prompt_tmp)]
        if args.sandbox:
            c.append("--sandbox")
        if args.effort:
            c += ["--effort", args.effort]
        if args.yolo:
            c.append("--dangerously-skip-permissions")
        if args.allow_cmds:
            settings = {"permissions": {"allow": [f"command({cmd_item})" for cmd_item in args.allow_cmds]}}
            c += ["--settings", json.dumps(settings, ensure_ascii=False)]

        cwd_val = None
        if args.isolated:
            ensure_council_dir()
            cwd_val = COUNCIL_DIR
            c.append("--disable-slash-commands")

        c += ["-p", cli_prompt]
        return c, cwd_val

    res = None
    try:
        for idx, cand_alias in enumerate(attempt_aliases):
            alias = cand_alias
            model_name = MODEL_ALIASES.get(cand_alias.lower(), cand_alias)
            cmd, run_cwd = build_cmd(model_name)
            try:
                res = subprocess.run(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    timeout=args.timeout, cwd=run_cwd,
                )
            except subprocess.TimeoutExpired:
                print(f"Error: Timeout esperando respuesta de {model_name} ({args.timeout}s)", file=sys.stderr)
                tlog(round(time.time() - start_time, 3), "TIMEOUT", 2)
                sys.exit(2)

            if res.returncode == 0:
                break

            combined_err = f"{res.stderr or ''}\n{res.stdout or ''}".strip()
            has_next = (idx + 1) < len(attempt_aliases)
            if has_next and (is_auto_model or args.auto_fallback) and is_quota_or_rate_limit_error(combined_err):
                if fallback_from is None:
                    fallback_from = cand_alias
                next_alias = attempt_aliases[idx + 1]
                print(
                    f"⚠️ Cuota/rate-limit en {model_name} ({cand_alias}); reintentando con {next_alias}...",
                    file=sys.stderr,
                )
                continue
            break
    finally:
        if prompt_tmp and os.path.exists(prompt_tmp):
            try:
                os.remove(prompt_tmp)
            except Exception:
                pass

    elapsed_s = round(time.time() - start_time, 3)
    raw_output = res.stdout.strip()

    if res.returncode != 0:
        err = res.stderr.strip() or raw_output
        print(f"Error ejecutando {model_name} (exit {res.returncode}): {err[:200]}", file=sys.stderr)
        err_parsed = parse_agy_output(raw_output, elapsed_s) if raw_output else {}
        tlog(
            elapsed_s, "ERROR", res.returncode,
            usage=err_parsed.get("usage"),
            denied_count=len(err_parsed.get("denied_actions") or []),
            conversation_id=err_parsed.get("conversation_id"),
        )
        sys.exit(res.returncode)

    parsed = parse_agy_output(raw_output, elapsed_s)
    response_text = parsed["response"]
    duration_s = parsed["duration_s"]
    usage = parsed["usage"]
    conversation_id = parsed["conversation_id"]
    agy_status = parsed["agy_status"]
    denied_actions = parsed["denied_actions"]

    is_denied = bool(denied_actions) or (
        parsed["is_json"] and not response_text and (agy_status or "").upper() == "SUCCESS"
    )

    # Guardar traza a disco
    out_path = args.out
    if not out_path:
        ensure_council_dir()
        out_path = f"{COUNCIL_DIR}/{alias}_{int(time.time())}_{os.getpid()}.md"

    token_line = format_token_line(usage)

    if is_denied:
        denied_lines = [format_denied_action(a) for a in denied_actions]
        header = f"🚫 DENIED: {len(denied_actions)} acción(es) denegada(s) por permisos"
        if not denied_actions:
            header = "🚫 DENIED: respuesta vacía con status SUCCESS (posible acción bloqueada por permisos)"
        trace = [header, *[f"  - {d}" for d in denied_lines]]
        if response_text:
            trace += ["", response_text]
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(trace) + "\n")

        shown = denied_lines[:max(1, args.max_lines - 4)]
        tele = [f"[{model_name}] {header}"]
        tele += [f"  - {d}" for d in shown]
        if len(denied_lines) > len(shown):
            tele.append(f"  ... (+{len(denied_lines) - len(shown)} más)")
        tele.append(f"💡 Reintenta con --exec/--mode auto, --allow-cmd <cmd> o --yolo (con --sandbox). Traza: {out_path}")
        if token_line:
            tele.append(token_line)
        print("\n".join(tele))
        tlog(duration_s, "DENIED", 3, usage=usage, denied_count=len(denied_actions), conversation_id=conversation_id)
        sys.exit(3)

    lines = response_text.splitlines() if response_text else []
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(response_text + "\n")

    print(smart_telegram(lines, args.max_lines, out_path, model_name, token_line))
    tlog(duration_s, "OK", 0, usage=usage, conversation_id=conversation_id)


if __name__ == "__main__":
    main()
