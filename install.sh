#!/usr/bin/env bash
# install.sh — Instala el plugin Chief of Staff en ~/.gemini/config/plugins/chief-of-staff
#
# Uso: bash install.sh [--copy | --link] [--init-config] [--student] [--doctor] [-h|--help]
#   --copy         (por defecto) copia los componentes al directorio destino.
#   --link         enlaza simbólicamente los componentes al repo (ideal para desarrollo).
#   --init-config  crea ~/.gemini/GEMINI.md, mcp_config.json y quota_budget.json desde templates/ SOLO si no existen.
#   --student      onboarding completo: copia + --init-config + quota_budget.json + --doctor.
#   --doctor       valida python3>=3.10, git, agy (opcional con aviso Student Lite), GEMINI.md y quota_budget.json.
#
# Garantías: nunca sobrescribe MEMORY.md, memory/, metrics.jsonl, mcp_config.json ni quota_budget.json existentes.
# Variables opcionales: GEMINI_HOME (default ~/.gemini), COS_TARGET (destino del plugin).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GEMINI_HOME="${GEMINI_HOME:-$HOME/.gemini}"
TARGET="${COS_TARGET:-$GEMINI_HOME/config/plugins/chief-of-staff}"
COMPONENTS=(agents rules skills playbooks templates assets)
MODE="copy"
INIT_CONFIG=0
STUDENT_MODE=0
RUN_DOCTOR=0
EXPLICIT_ACTION=0

info() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✘\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

run_doctor() {
  local issues=0
  echo "Chief of Staff — Diagnóstico (--doctor)"
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    info "python3 >= 3.10 detectado ($(python3 -V 2>&1))"
  else
    warn "python3 >= 3.10 no disponible (requerido por los scripts en skills/chief-of-staff-ops/scripts)"
    issues=$((issues + 1))
  fi

  if command -v git >/dev/null 2>&1; then
    info "git detectado ($(git --version))"
  else
    warn "git no encontrado en PATH (requerido por verify_handoff.py para auditar scope)"
    issues=$((issues + 1))
  fi

  if command -v agy >/dev/null 2>&1; then
    info "CLI 'agy' detectado: Modo Council Pro activo (Claude 5.5 / Argon 4 / GPT-OSS)"
  else
    info "Sin CLI 'agy': operando en Modo Student Lite (subagentes flash/flash_lite, 0% gasto Council)"
  fi

  if [ -e "$GEMINI_HOME/GEMINI.md" ]; then
    info "GEMINI.md encontrado en $GEMINI_HOME/GEMINI.md"
  else
    warn "GEMINI.md no encontrado en $GEMINI_HOME/GEMINI.md (ejecuta: bash install.sh --student)"
    issues=$((issues + 1))
  fi

  if [ -e "$TARGET/quota_budget.json" ]; then
    info "quota_budget.json encontrado en $TARGET/quota_budget.json"
  else
    warn "quota_budget.json no encontrado en $TARGET/quota_budget.json (ejecuta: bash install.sh --student)"
    issues=$((issues + 1))
  fi

  if [ "$issues" -eq 0 ]; then
    info "Diagnóstico completado sin errores bloqueantes."
  else
    warn "Diagnóstico completado con $issues aviso(s) de configuración."
  fi
  return 0
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --copy)        MODE="copy"; EXPLICIT_ACTION=1 ;;
    --link)        MODE="link"; EXPLICIT_ACTION=1 ;;
    --init-config) INIT_CONFIG=1; EXPLICIT_ACTION=1 ;;
    --student)     MODE="copy"; INIT_CONFIG=1; STUDENT_MODE=1; RUN_DOCTOR=1; EXPLICIT_ACTION=1 ;;
    --doctor)      RUN_DOCTOR=1 ;;
    -h|--help)     usage; exit 0 ;;
    *)             usage >&2; die "Opción desconocida: $1" ;;
  esac
  shift
done

if [ "$RUN_DOCTOR" -eq 1 ] && [ "$EXPLICIT_ACTION" -eq 0 ]; then
  run_doctor
  exit 0
fi

command -v python3 >/dev/null 2>&1 || warn "python3 no encontrado: los scripts de skills/chief-of-staff-ops/scripts lo requieren."
if ! command -v agy >/dev/null 2>&1; then
  if [ "$STUDENT_MODE" -eq 1 ]; then
    info "Modo Student Lite activo (no requiere CLI 'agy'; usa subagentes flash/flash_lite)."
  else
    warn "CLI 'agy' no encontrado en PATH: operará en Modo Student Lite (instala 'agy' para Modo Council Pro)."
  fi
fi

echo "Chief of Staff — instalación (modo: $MODE)"
echo "  Origen : $REPO_DIR"
echo "  Destino: $TARGET"

mkdir -p "$TARGET"
SAME_DIR=0
if [ "$(readlink -f "$TARGET")" = "$REPO_DIR" ]; then
  SAME_DIR=1
  warn "El destino es este mismo repositorio; se omite el despliegue de componentes."
fi

deploy_component() {
  local name="$1" src dst
  src="$REPO_DIR/$name"
  dst="$TARGET/$name"
  [ -d "$src" ] || { warn "Componente ausente en el repo, se omite: $name"; return 0; }

  if [ -L "$dst" ]; then
    rm "$dst"
  elif [ "$MODE" = "link" ] && [ -e "$dst" ]; then
    local backup="$dst.bak.$(date +%Y%m%d%H%M%S)"
    mv "$dst" "$backup"
    warn "Respaldo previo: $backup"
  fi

  if [ "$MODE" = "link" ]; then
    ln -s "$src" "$dst"
    info "enlazado  $name/"
  else
    mkdir -p "$dst"
    cp -a "$src/." "$dst/"
    info "copiado   $name/"
  fi
}

if [ "$SAME_DIR" -eq 0 ]; then
  for component in "${COMPONENTS[@]}"; do
    deploy_component "$component"
  done
  if [ -f "$REPO_DIR/plugin.json" ]; then
    if [ "$MODE" = "link" ]; then
      ln -sf "$REPO_DIR/plugin.json" "$TARGET/plugin.json"
      info "enlazado  plugin.json"
    else
      rm -f "$TARGET/plugin.json"
      cp -a "$REPO_DIR/plugin.json" "$TARGET/plugin.json"
      info "copiado   plugin.json"
    fi
  fi
fi

# Scripts ejecutables (best-effort, incluido memory_search.py)
for scripts_dir in "$TARGET/skills/chief-of-staff-ops/scripts" "$REPO_DIR/skills/chief-of-staff-ops/scripts" "$TARGET/scripts" "$REPO_DIR/scripts"; do
  if [ -d "$scripts_dir" ]; then
    chmod +x "$scripts_dir"/*.py 2>/dev/null || true
  fi
done

# Memoria: se crea solo si falta; jamás se pisa
mkdir -p "$TARGET/memory"
if [ -e "$TARGET/MEMORY.md" ]; then
  info "MEMORY.md existente conservado"
else
  cp "$REPO_DIR/templates/MEMORY.md.example" "$TARGET/MEMORY.md"
  info "MEMORY.md creado desde plantilla"
fi

# Configuración opcional
if [ "$INIT_CONFIG" -eq 1 ]; then
  mkdir -p "$GEMINI_HOME"
  if [ -e "$GEMINI_HOME/GEMINI.md" ]; then
    info "GEMINI.md existente conservado"
  else
    cp "$REPO_DIR/templates/GEMINI.md.example" "$GEMINI_HOME/GEMINI.md"
    info "GEMINI.md creado en $GEMINI_HOME"
  fi
  if [ -e "$TARGET/mcp_config.json" ]; then
    info "mcp_config.json existente conservado"
  else
    cp "$REPO_DIR/templates/mcp_config.example.json" "$TARGET/mcp_config.json"
    info "mcp_config.json creado (edítalo con tus servidores MCP)"
  fi
  if [ -e "$TARGET/quota_budget.json" ]; then
    info "quota_budget.json existente conservado"
  elif [ -e "$REPO_DIR/templates/quota_budget.example.json" ]; then
    cp "$REPO_DIR/templates/quota_budget.example.json" "$TARGET/quota_budget.json"
    info "quota_budget.json creado desde plantilla"
  else
    warn "templates/quota_budget.example.json aún no disponible; se omite copia inicial"
  fi
else
  warn "Sin --init-config: revisa templates/GEMINI.md.example, mcp_config.example.json y quota_budget.example.json."
fi

if [ "$RUN_DOCTOR" -eq 1 ]; then
  echo ""
  run_doctor
fi

echo "Listo. Verifica con:"
echo "  python3 \"$TARGET/skills/chief-of-staff-ops/scripts/view_tokens.py\" --weekly --quota"
