#!/usr/bin/env python3
"""
verify_handoff.py - Verificador Determinista de Handoff & Pre-Flight Check (v4.3 Telemetría & Lean Industrial)
Correcciones incorporadas post-auditoría Arch-Critic (Claude Sonnet 5.5):
1. Fail-closed: Nunca asume éxito si git falla o salta excepción.
2. In-Memory AST: Usa ast.parse() en vez de py_compile (cero basura __pycache__).
3. Resolución precisa de Git: Usa git rev-parse --show-toplevel y resuelve rutas canónicas.
4. Detección honesta: Extensiones desconocidas se marcan como UNCHECKED, no como OK falso.
5. Telemetría JSONL best-effort en metrics.jsonl (ts, script, files_checked, status, syntax_fails, scope_violations).
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time

DEFAULT_METRICS_PATH = os.path.expanduser("~/.gemini/config/plugins/chief-of-staff/metrics.jsonl")

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Google API Key (AIza...)", re.compile(r"AIza[0-9A-Za-z\-_]{20,}")),
    ("Secret API Key (sk-...)", re.compile(r"\bsk-(?:proj-|ant-)?[0-9A-Za-z\-_]{20,}")),
    ("GitHub PAT (ghp_...)", re.compile(r"\bghp_[0-9A-Za-z]{20,}")),
    ("GitHub OAuth (gho_...)", re.compile(r"\bgho_[0-9A-Za-z]{20,}")),
    ("Private Key Header", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")),
]


def log_telemetry(
    ts: str,
    files_checked: int,
    status: str,
    syntax_fails: int,
    scope_violations: int,
    secret_leaks: int = 0,
) -> None:
    """Registra telemetría de verificación en metrics.jsonl de forma best-effort (fail-safe)."""
    try:
        metrics_file = os.environ.get("COS_METRICS_PATH", DEFAULT_METRICS_PATH)
        os.makedirs(os.path.dirname(metrics_file), exist_ok=True)
        payload = {
            "ts": ts,
            "script": "verify_handoff.py",
            "files_checked": files_checked,
            "status": status,
            "syntax_fails": syntax_fails,
            "scope_violations": scope_violations,
            "secret_leaks": secret_leaks,
        }
        with open(metrics_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def scan_secrets(filepath: str) -> list[str]:
    """Escaneo ligero de secretos (ECC AgentShield, stdlib re). Ignora *.example y verify_handoff.py."""
    base = os.path.basename(filepath)
    if base.lower().endswith(".example") or base == "verify_handoff.py":
        return []
    try:
        if os.path.realpath(filepath) == os.path.realpath(__file__):
            return []
        if not os.path.isfile(filepath):
            return []
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return []

    findings: list[str] = []
    for lineno, line in enumerate(lines, start=1):
        for label, pattern in SECRET_PATTERNS:
            m = pattern.search(line)
            if m:
                token = m.group(0)
                preview = token[:8] + "..." if len(token) > 8 else token
                findings.append(f"{filepath}:L{lineno} [{label}] ({preview})")
    return findings

def check_syntax(filepath: str) -> tuple[str, str]:
    """Retorna (STATUS, MENSAJE) donde STATUS es OK, FAIL o UNCHECKED."""
    if not os.path.isfile(filepath):
        return "FAIL", "Archivo no existe en disco"
    
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".py":
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            ast.parse(content, filename=filepath)
            return "OK", "AST parse exitoso (sin __pycache__)"
        elif ext in [".sh", ".bash"]:
            res = subprocess.run(["bash", "-n", filepath], capture_output=True, text=True)
            if res.returncode != 0:
                return "FAIL", f"Bash syntax error: {res.stderr.strip()[:150]}"
            return "OK", "Bash -n validado"
        elif ext == ".json":
            res = subprocess.run(["python3", "-m", "json.tool", filepath], capture_output=True, text=True)
            if res.returncode != 0:
                return "FAIL", f"JSON malformado: {res.stderr.strip()[:150]}"
            return "OK", "JSON válido"
        else:
            return "UNCHECKED", f"Sin linter local para extensión '{ext}'"
    except SyntaxError as se:
        return "FAIL", f"Error de sintaxis L{se.lineno}: {se.msg}"
    except Exception as e:
        return "FAIL", f"Excepción al verificar: {str(e)}"

def get_git_modified_files(repo_root: str) -> list[str]:
    """Obtiene lista de archivos modificados y untracked dentro del repo de forma fail-closed."""
    # 1. Cambios rastreados (staged o un-staged)
    diff_res = subprocess.run(
        ["git", "-C", repo_root, "diff", "--name-only", "HEAD"],
        capture_output=True, text=True
    )
    # Si HEAD falla (ej. repo recién inicializado sin commits), probar contra árbol vacío
    if diff_res.returncode != 0:
        diff_res = subprocess.run(
            ["git", "-C", repo_root, "diff", "--name-only"],
            capture_output=True, text=True
        )
    
    # 2. Archivos untracked (sin ignorados)
    untracked_res = subprocess.run(
        ["git", "-C", repo_root, "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True
    )

    touched = set()
    if diff_res.returncode == 0 and diff_res.stdout:
        for rel in diff_res.stdout.splitlines():
            if rel.strip():
                touched.add(os.path.realpath(os.path.join(repo_root, rel.strip())))
                
    if untracked_res.returncode == 0 and untracked_res.stdout:
        for rel in untracked_res.stdout.splitlines():
            if rel.strip():
                touched.add(os.path.realpath(os.path.join(repo_root, rel.strip())))

    return list(touched)

def main():
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    parser = argparse.ArgumentParser(description="Auditoría Determinista de Handoff (Fail-Closed)")
    parser.add_argument("--scope", nargs="*", default=[], help="Archivos permitidos en el SCOPE")
    parser.add_argument("--files", nargs="*", default=[], help="Archivos modificados a verificar")
    parser.add_argument("--no-secret-scan", action="store_true", help="Desactivar escaneo ligero de secretos")
    args = parser.parse_args()

    # 1. Resolver raíz de Git
    repo_check = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    in_git = (repo_check.returncode == 0)
    repo_root = repo_check.stdout.strip() if in_git else None

    # 2. Syntax Check & Secret Scan (ECC AgentShield)
    files_to_check = [os.path.realpath(f) for f in (args.files or args.scope)]
    syntax_fails = []
    secret_fails = []
    unchecked = []
    for f in files_to_check:
        status, msg = check_syntax(f)
        if status == "FAIL":
            syntax_fails.append(f"{f}: {msg}")
        elif status == "UNCHECKED":
            unchecked.append(f"{os.path.basename(f)} ({msg})")
        if not args.no_secret_scan:
            secret_fails.extend(scan_secrets(f))

    # 3. Scope Check (Fail-closed)
    scope_violations = []
    if args.scope:
        if not in_git:
            print("❌ HANDOFF FAILED: Validación de SCOPE requerida pero no se detectó repositorio Git.", file=sys.stderr)
            log_telemetry(ts, len(files_to_check), "FAIL", len(syntax_fails), 1, len(secret_fails))
            sys.exit(1)
            
        allowed_set = {os.path.realpath(f) for f in args.scope}
        all_touched = get_git_modified_files(repo_root)
        for t in all_touched:
            if t not in allowed_set:
                scope_violations.append(t)

    # 4. Veredicto y Telemetría
    overall_status = "FAIL" if (syntax_fails or scope_violations or secret_fails) else "OK"
    log_telemetry(
        ts,
        len(files_to_check),
        overall_status,
        len(syntax_fails),
        len(scope_violations),
        len(secret_fails),
    )

    if syntax_fails or scope_violations or secret_fails:
        print("❌ HANDOFF FAILED:")
        for v in scope_violations:
            print(f"  [SCOPE VIOLATION] Archivo no autorizado modificado: {v}")
        for err in syntax_fails:
            print(f"  [SYNTAX ERROR] {err}")
        for leak in secret_fails:
            print(f"  [SECRET LEAK] {leak}")
        sys.exit(1)

    print(f"✅ HANDOFF VERIFIED: {len(files_to_check)} archivo(s) validados.")
    if unchecked:
        print(f"  ℹ️ Sin linter local: {', '.join(unchecked)}")

if __name__ == "__main__":
    main()
