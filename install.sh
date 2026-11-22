#!/usr/bin/env bash
# install.sh — Instala el plugin Chief of Staff en ~/.gemini/config/plugins/chief-of-staff
#
# Uso: bash install.sh [--copy | --link] [--init-config] [-h|--help]
#   --copy         (por defecto) copia los componentes al directorio destino.
#   --link         enlaza simbólicamente los componentes al repo (ideal para desarrollo).
#   --init-config  crea ~/.gemini/GEMINI.md y mcp_config.json desde templates/ SOLO si no existen.
#
# Garantías: nunca sobrescribe MEMORY.md, memory/, metrics.jsonl ni mcp_config.json existentes.
# Variables opcionales: GEMINI_HOME (default ~/.gemini), COS_TARGET (destino del plugin).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GEMINI_HOME="${GEMINI_HOME:-$HOME/.gemini}"
TARGET="${COS_TARGET:-$GEMINI_HOME/config/plugins/chief-of-staff}"
COMPONENTS=(agents rules skills playbooks templates)
MODE="copy"
INIT_CONFIG=0

info() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✘\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --copy)        MODE="copy" ;;
    --link)        MODE="link" ;;
    --init-config) INIT_CONFIG=1 ;;
    -h|--help)     usage; exit 0 ;;
    *)             usage >&2; die "Opción desconocida: $1" ;;
  esac
  shift
done

command -v python3 >/dev/null 2>&1 || warn "python3 no encontrado: los scripts de skills/chief-of-staff-ops/scripts lo requieren."
command -v agy >/dev/null 2>&1 || warn "CLI 'agy' no encontrado en PATH: consult_council.py lo necesita para invocar modelos."

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
fi

# Scripts ejecutables (best-effort)
if [ -d "$TARGET/skills/chief-of-staff-ops/scripts" ]; then
  chmod +x "$TARGET"/skills/chief-of-staff-ops/scripts/*.py 2>/dev/null || true
fi

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
else
  warn "Sin --init-config: revisa templates/GEMINI.md.example y templates/mcp_config.example.json."
fi

echo "Listo. Verifica con:"
echo "  python3 \"$TARGET/skills/chief-of-staff-ops/scripts/view_tokens.py\" --sessions 0"
