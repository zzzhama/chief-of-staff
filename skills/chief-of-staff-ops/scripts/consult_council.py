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
import json
import os
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
    parser.add_argument("-m", "--model", default="claude", help="Alias o nombre del modelo (use --list-models para ver todos)")
    parser.add_argument("--list-models", action="store_true", help="Listar todos los alias -> modelo disponibles y salir")
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

    if args.exec_mode and args.mode == "plan":
        args.mode = "accept-edits"

    alias = args.model
    model_name = MODEL_ALIASES.get(args.model.lower(), args.model)

    def tlog(duration_s, status, exit_code, usage=None, denied_count=None, conversation_id=None):
        log_telemetry(
            ts, alias, model_name, duration_s, status, exit_code,
            usage=usage,
            mode=args.mode,
            agent=args.agent,
            sandbox=args.sandbox,
            denied_count=denied_count,
            conversation_id=conversation_id,
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
    temp_prompt_file = None
    if len(prompt_text) > ARG_MAX_CHARS:
        fd, temp_prompt_file = tempfile.mkstemp(prefix="council_prompt_", suffix=".md")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(prompt_text)
        cli_prompt = f"Por favor lee atentamente y responde según las instrucciones contenidas en el archivo: {temp_prompt_file}"
    else:
        cli_prompt = prompt_text

    cmd = [
        "agy", "--model", model_name,
        "--output-format", "json",
        "--print-timeout", f"{args.timeout}s",
        "--mode", args.mode,
    ]
    if args.agent:
        cmd += ["--agent", args.agent]
    for d in args.add_dirs:
        cmd += ["--add-dir", d]
    if args.sandbox:
        cmd.append("--sandbox")
    if args.effort:
        cmd += ["--effort", args.effort]
    if args.yolo:
        cmd.append("--dangerously-skip-permissions")
    if args.allow_cmds:
        settings = {"permissions": {"allow": [f"command({c})" for c in args.allow_cmds]}}
        cmd += ["--settings", json.dumps(settings, ensure_ascii=False)]

    run_cwd = None
    if args.isolated:
        ensure_council_dir()
        run_cwd = COUNCIL_DIR
        cmd.append("--disable-slash-commands")

    cmd += ["-p", cli_prompt]

    try:
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=args.timeout, cwd=run_cwd,
        )
    except subprocess.TimeoutExpired:
        print(f"Error: Timeout esperando respuesta de {model_name} ({args.timeout}s)", file=sys.stderr)
        tlog(round(time.time() - start_time, 3), "TIMEOUT", 2)
        sys.exit(2)
    finally:
        if temp_prompt_file and os.path.exists(temp_prompt_file):
            try:
                os.remove(temp_prompt_file)
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
        out_path = f"{COUNCIL_DIR}/{args.model}_{int(time.time())}.md"

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
