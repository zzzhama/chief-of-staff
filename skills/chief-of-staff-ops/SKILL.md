---
name: chief-of-staff-ops
description: >-
  Protocolo operativo v5.1 del Chief of Staff (Balance Real de Cuotas + Micro-Kernel + Grill Gate + Oleadas)
  para coordinar subagentes ligeros (flash/flash_lite), ejecución agéntica delegada a
  Claude 5.5 y Argon 4 vía consult_council.py (--agent, --exec, --mode, --dir),
  contratos tipados Handoff y auditoría de sesiones con view_tokens.py --sessions.
---

# Protocolo Operativo v5.1: Chief of Staff (Balance Real de Cuotas + Micro-Kernel)

Usa este procedimiento para orquestar tareas maximizando cuotas independientes y evitando el desperdicio del modelo principal:

## 0. Grill Gate (v5.1)
Si la petición es abierta o de diseño, hacer 3-4 preguntas cortas vía `ask_question` (objetivo, alcance, restricciones, criterio de éxito) **antes** de despachar Claude/Argon. Saltar si ya hay `TARGET`/`SCOPE` exactos.

## 1. Memoria Persistente & Context Sharding
Consulta `~/.gemini/config/plugins/chief-of-staff/MEMORY.md` y fichas atómicas en `memory/` antes de explorar a ciegas o pedir datos ya registrados.

## 2. Matriz de Ruteo v5.0 (Subagentes Flash + Ejecución vía Consejo)
> **Regla Anti-Desperdicio:** PROHIBIDO usar `invoke_subagent` con `Model=inherit` o `Model=pro` cuando el orquestador corre en Hydrogen/Neon/Pro.

### A. Vía `invoke_subagent` (SOLO `flash` / `flash_lite`)
1. `recon-scout` (*Vega*, `flash` / `flash_lite`): Exploración rápida, logs, diagnóstico y coordenadas AST (`ast_outline.py`). Solo lectura.
2. `memory-archivist` (*Clío*, `flash_lite` / `flash`): Fichas selladas (<80 líneas) en `memory/` y actualización de `MEMORY.md` (`shard_doc.py`).
3. Tareas menores/rutina (`worker-builder`, `frontend-crafter`, `qa-auditor`, `cyber-auditor`): Solo si son cambios triviales explícitamente despachados en `flash`.

### B. Vía `consult_council.py` (Cuotas Independientes con Rol Agéntico `--agent`)
- **Coding / Refactor / Debug / Tests / QA Crítico (Cuota Claude Sonnet/Opus 5.5)**:
  ```bash
  # Implementación backend/scripts con worker-builder en Claude Sonnet 5.5
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m claude --agent worker-builder --exec --dir /ruta/workspace \
    "TARGET: app.py | SCOPE: L20-L90 | OUTPUT: HANDOFF_PACKET | BUDGET: 4 | FORBID: fuera de scope"

  # Auditoría QA independiente o Pre-Mortem de seguridad con qa-auditor / cyber-auditor
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m claude --agent qa-auditor --mode plan --sandbox --yolo --dir /ruta/workspace \
    "TARGET: tests/test_app.py | SCOPE: validación casos borde | OUTPUT: PASS/FAIL"
  ```
- **Arquitectura / Frontend / UX / Diseño 3D (Cuota Argon 4)**:
  ```bash
  # Ejecución UI/Frontend con frontend-crafter en Argon 4
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m argon --agent frontend-crafter --exec --dir /ruta/workspace \
    "TARGET: src/ui/Dashboard.tsx | SCOPE: layout responsivo | OUTPUT: HANDOFF_PACKET"

  # Diseño arquitectónico o UX en modo solo planificación (--mode plan)
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m argon --agent frontend-crafter --mode plan --dir /ruta/workspace \
    "Diseña la arquitectura de componentes y flujo UX"
  ```
- **Segunda Opinión / Desempate Técnico (Cuota GPT-OSS)**:
  ```bash
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m gpt "Evalúa trade-offs entre opción A y opción B"
  ```

## 3. Flujos Deterministas & Telemetría (`scripts/`)
- `consult_council.py`: Invoca modelos independientes con perfiles de `agents/*.md` (`--agent`), controla permisos (`--exec` para `accept-edits`, `--mode plan|accept-edits|auto`, `--sandbox --yolo` o `--allow-cmd`), fija directorio (`--dir`) y registra tokens reales en `metrics.jsonl`.
- `view_tokens.py`: Audita consumo acumulado de `consult_council.py` y sesiones reales de AGY (`transcript.jsonl`):
  ```bash
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/view_tokens.py --sessions
  ```
- `verify_handoff.py`: Valida compilación limpia (Python, Bash, JSON) y cero violaciones de scope git antes de aceptar cualquier `HANDOFF_PACKET`.
- `ast_outline.py` y `shard_doc.py`: Coordenadas quirúrgicas AST y partición de fichas en `memory/`.

## 4. Orquestación por Oleadas + Telemetría final (v5.1)
Detalle completo en `~/.gemini/config/plugins/chief-of-staff/playbooks/teamwork_waves.md`. Preferir Oleadas propias sobre `/teamwork-preview` nativo (protege la cuota principal e impone `verify_handoff.py`).
1. **Oleada 1 Recon** (paralelo): `recon-scout` (`flash`) + `memory-archivist` (`flash_lite`), solo lectura.
2. **Oleada 2 Plan**: Argon `--mode plan`; desempate con `-m gpt`.
3. **Oleada 3 Ejecución** (paralela, archivos disjuntos): `frontend-crafter` (Argon) + `worker-builder` (Claude); `qa-auditor` solo lectura con `--mode plan --sandbox`.
4. **Oleada 4 Cierre**: `verify_handoff.py` + telemetría y reporte de ahorro de cuota:
   ```bash
   python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/view_tokens.py --last 10 --sessions 5
   ```
   Luego `memory-archivist` sella la ficha en `memory/`.
