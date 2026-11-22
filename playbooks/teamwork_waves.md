# Playbook: Teamwork Propio por Oleadas v5.1

Orquestación multi-agente con cuotas separadas, Grill Gate previo y telemetría de cierre.
Notación: `S=~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts` (usado como `$S` abajo).

## 0. Grill Gate (antes de despachar Claude/Argon)
- **Cuándo**: la petición es abierta, ambigua o de diseño ("hazme un dashboard", "mejora X").
- **Qué**: 3-4 preguntas cortas vía `ask_question` (objetivo, alcance/archivos, restricciones, criterio de éxito).
- **Saltar** si el usuario ya entregó `TARGET` y `SCOPE` exactos: despachar directo.
- Las respuestas se convierten en el briefing tipado `TARGET | SCOPE | OUTPUT | BUDGET | FORBID`.

## 1. Oleada 1 — Recon paralelo (solo lectura, cuota flash)
Despacho simultáneo con `invoke_subagent`:
- `recon-scout` (`Model: flash`): estructura, logs, coordenadas AST (`ast_outline.py`).
- `memory-archivist` (`Model: flash_lite`): fichas relevantes en `memory/` y `MEMORY.md`.

Salida: contexto mínimo + lista de archivos candidatos, sin escrituras.

## 2. Oleada 2 — Plan
```bash
python3 $S/consult_council.py -m argon --agent frontend-crafter --mode plan --dir <ws> "Plan: <contexto Oleada 1>"
# Desempate técnico si hay opciones en conflicto (cuota GPT-OSS):
python3 $S/consult_council.py -m gpt "Evalúa trade-offs entre A y B"
```
Salida: plan con archivos **disjuntos** asignados por agente (sin solapes de escritura).

## 3. Oleada 3 — Ejecución paralela en archivos disjuntos
```bash
# UI/Frontend (cuota Argon 4)
python3 $S/consult_council.py -m argon --agent frontend-crafter --exec --dir <ws> "TARGET: <ui> | SCOPE: ... | OUTPUT: HANDOFF_PACKET"
# Backend/scripts/tests (cuota Claude 5.5)
python3 $S/consult_council.py -m claude --agent worker-builder --exec --dir <ws> "TARGET: <backend> | SCOPE: ... | OUTPUT: HANDOFF_PACKET"
# QA: SOLO lectura/verificación, sin herramientas de escritura
python3 $S/consult_council.py -m claude --agent qa-auditor --mode plan --sandbox --yolo --dir <ws> "TARGET: ... | OUTPUT: PASS/FAIL"
```
Reglas:
- Un archivo = un único escritor. Si dos tareas tocan el mismo archivo, serializarlas.
- `qa-auditor` nunca usa `--exec`; corre en `--mode plan --sandbox`, tras (o junto a) los builders, solo leyendo.
- Cada builder cierra con `verify_handoff.py` y `HANDOFF_PACKET`.

## 4. Oleada 4 — Cierre y telemetría
```bash
python3 $S/verify_handoff.py
python3 $S/view_tokens.py --last 10 --sessions 5
```
- Aceptar la entrega solo si `verify_handoff.py` pasa (compilación limpia + cero violaciones de scope).
- Reportar al usuario el **ahorro de cuota**: tokens gastados en Claude/Argon/GPT/flash (`consult_council`) frente a la sesión principal (`--sessions`).
- Despachar `memory-archivist` (`flash_lite`) para sellar la ficha de aprendizajes (<80 líneas) y actualizar `MEMORY.md`.

## Por qué Oleadas propias y no `/teamwork-preview` nativo
- **Protección de cuota principal**: el teamwork nativo hereda el modelo del orquestador (Hydrogen/Neon/Pro) y quema su cuota; las Oleadas propias reparten el trabajo en cuotas independientes (flash, Claude, Argon, GPT-OSS).
- **verify_handoff obligatorio**: el nativo no valida compilación ni scope git; las Oleadas lo imponen en el cierre y en cada builder.
- **Trazabilidad**: cada llamada queda en `metrics.jsonl` y es auditable con `view_tokens.py`.
- **Control de escrituras**: archivos disjuntos y QA de solo lectura evitan colisiones que el nativo no previene.
