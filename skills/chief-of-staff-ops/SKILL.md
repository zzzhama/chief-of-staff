---
name: chief-of-staff-ops
description: >-
  Protocolo operativo v5.1 del Chief of Staff (Modo Dual Student Lite / Council Pro +
  Balance Real de Cuotas + Micro-Kernel + Grill Gate + Oleadas + Zero-Syntax UX)
  para coordinar subagentes ligeros (flash/flash_lite), ejecución agéntica delegada a
  Claude 5.5 y Argon 4 vía consult_council.py, contratos Handoff y Semáforo de Cuotas
  con view_tokens.py --weekly --quota.
---

# Protocolo Operativo v5.1: Chief of Staff (Modo Dual + Balance de Cuotas + Micro-Kernel)

Usa este procedimiento para orquestar tareas maximizando cuotas independientes y evitando el desperdicio del modelo principal:

## 0. Grill Gate & Autonomía Amable (v5.1)
Si la petición es abierta o de diseño, hacer 3-4 preguntas cortas vía `ask_question` (objetivo, alcance, restricciones, criterio de éxito) **antes** de despachar builders. Saltar si ya hay `TARGET`/`SCOPE` exactos.
- **Autonomía con cortesía**: el Chief of Staff decide solo el modelo y balance de cuotas en cada tarea, pero **pregunta amablemente** antes de fijar una automatización o preferencia permanente (*"para siempre"*).

## 1. Memoria Persistente & Context Sharding
Consulta `~/.gemini/config/plugins/chief-of-staff/MEMORY.md` y busca en fichas atómicas de `memory/` con `memory_search.py "<consulta>"` (búsqueda local SQLite FTS5) antes de explorar a ciegas o pedir datos ya registrados.

## 2. Modo Dual & Matriz de Ruteo (Council Pro vs Student Lite)
> **Regla Anti-Desperdicio:** PROHIBIDO usar `invoke_subagent` con `Model=inherit` o `Model=pro` cuando el orquestador corre en Hydrogen/Neon/Pro.

- **Modo Council Pro** (por defecto con CLI `agy` instalado y `COS_PROFILE!=lite`): combina subagentes nativos `flash`/`flash_lite` (exploración y memoria) con ejecución multi-modelo vía `consult_council.py` (Claude 5.5, Argon 4, GPT-OSS).
- **Modo Student Lite** (cuando `COS_PROFILE=lite`, sin CLI `agy`, o cuando el semáforo de cuota exige ahorro): los 7 agentes (`recon-scout`, `memory-archivist`, `mentor-architect`, `worker-builder`, `frontend-crafter`, `qa-auditor`, `cyber-auditor`) se ejecutan vía `invoke_subagent` usando **exclusivamente** `Model: "flash"` o `"flash_lite"`, conservando Grill Gate, Oleadas y `verify_handoff.py`.

### A. Vía `invoke_subagent` (SOLO `flash` / `flash_lite`)
1. `recon-scout` (*Vega*, `flash` / `flash_lite`): Exploración rápida, logs, diagnóstico y coordenadas AST (`ast_outline.py`). Solo lectura.
2. `memory-archivist` (*Clío*, `flash_lite` / `flash`): Fichas selladas (<80 líneas) en `memory/`, curaduría de **Instincts** vía `learn_instinct.py` (cabecera `Confidence: X.XX`, dry-run primero + preguntar al usuario antes de `--apply`) y actualización de `MEMORY.md` (`shard_doc.py` + `memory_search.py`).
3. Ejecución completa en **Modo Student Lite** o cambios menores (`mentor-architect`, `worker-builder`, `frontend-crafter`, `qa-auditor`, `cyber-auditor`): siempre con `Model: "flash"` o `"flash_lite"`.

### B. Vía `consult_council.py` (Modo Council Pro — Cuotas Independientes con `--agent`)
- **Auto-Ruteo con Fallback de Cuotas (Recomendado: `-m auto`, `--task`, `--auto-fallback`, `--dry-run-route`)**:
  ```bash
  # Selección automática de modelo según agente/tarea con fallback si la cuota está en CRITICAL
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m auto --agent worker-builder --task coding --auto-fallback --exec --dir /ruta/workspace \
    "TARGET: app.py | SCOPE: L20-L90 | OUTPUT: HANDOFF_PACKET | BUDGET: 4 | FORBID: fuera de scope"

  # Previsualizar ruta y fallback de cuota sin ejecutar llamada (--dry-run-route)
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m auto --agent mentor-architect --auto-fallback --dry-run-route "Plan de arquitectura"
  ```
- **Coding / Refactor / Debug / Tests / QA Crítico (Cuota Claude Sonnet/Opus 5.5)**:
  ```bash
  # Implementación backend/scripts con worker-builder en Claude Sonnet 5.5
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m claude --agent worker-builder --exec --dir /ruta/workspace \
    "TARGET: app.py | SCOPE: L20-L90 | OUTPUT: HANDOFF_PACKET | BUDGET: 4 | FORBID: fuera de scope"

  # Auditoría QA independiente o Pre-Mortem de seguridad con qa-auditor / cyber-auditor
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m claude --agent qa-auditor --mode plan --sandbox --dir /ruta/workspace \
    "TARGET: tests/test_app.py | SCOPE: validación casos borde | OUTPUT: PASS/FAIL"
  ```
- **Arquitectura / Mentoría (Oleada 2) / Frontend / UX / Diseño 3D (Cuota Argon 4)**:
  ```bash
  # Arquitectura de sistemas, Oleada 2 (Plan) y mentoría socrática con mentor-architect (Marco)
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m argon --agent mentor-architect --mode plan --dir /ruta/workspace \
    "TARGET: arquitectura | SCOPE: diseño modular y trade-offs | OUTPUT: plan de oleadas"

  # Ejecución UI/Frontend con frontend-crafter (Elena) en Argon 4
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m argon --agent frontend-crafter --exec --dir /ruta/workspace \
    "TARGET: src/ui/Dashboard.tsx | SCOPE: layout responsivo | OUTPUT: HANDOFF_PACKET"

  # Diseño UX/Frontend en modo solo planificación (--mode plan)
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m argon --agent frontend-crafter --mode plan --dir /ruta/workspace \
    "Diseña la arquitectura de componentes y flujo UX"
  ```
- **Segunda Opinión / Desempate Técnico (Cuota GPT-OSS)**:
  ```bash
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py \
    -m gpt "Evalúa trade-offs entre opción A y opción B"
  ```

## 3. Flujos Deterministas, Semáforo de Cuotas & Telemetría (`scripts/`)
- `consult_council.py`: Invoca modelos independientes con perfiles de `agents/*.md` (`--agent`), controla permisos (`--exec`, `--mode plan|accept-edits|auto`, `--sandbox`, `--allow-cmd`), fija directorio (`--dir`) y registra tokens reales en `metrics.jsonl`.
- `view_tokens.py`: Audita consumo acumulado (`metrics.jsonl` + `transcript.jsonl`), atribuye automáticamente los turnos del chat IDE a su familia detectando etiquetas `<USER_SETTINGS_CHANGE>` en los transcripts y evalúa el **Semáforo de Cuotas** (`quota_budget.json`):
  ```bash
  python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/view_tokens.py --weekly --quota
  ```
  *(Soporta `--daily`, `--weekly`, `--quota` y `--sessions`; si una familia entra en estado crítico, rota de familia o pasa a Student Lite).*
- `verify_handoff.py`: Valida compilación limpia (Python, Bash, JSON), cero violaciones de scope git y escaneo anti-secretos/API keys antes de aceptar cualquier `HANDOFF_PACKET`.
- `memory_search.py`: Búsqueda rápida full-text (SQLite FTS5) sobre `MEMORY.md` y fichas en `memory/` (incluyendo Instincts graduados por `Confidence: X.XX`).
- `learn_instinct.py`: Ciclo de auto-aprendizaje amable (estilo ECC Instincts). Por defecto ejecuta **dry-run** (vista previa sin escribir disco) respetando la *Autonomía Amable*; tras confirmar con el usuario, `--apply` escribe la ficha atómica (<80 líneas) en `memory/<slug>.md` con cabecera `Confidence: X.XX` compatible con `memory_search.py` y añade la entrada a `MEMORY.md`.
- `ast_outline.py` y `shard_doc.py`: Coordenadas quirúrgicas AST y partición de fichas en `memory/`.

## 4. Orquestación por Oleadas + Telemetría final (v5.1)
Detalle completo en `~/.gemini/config/plugins/chief-of-staff/playbooks/teamwork_waves.md`. Preferir Oleadas propias sobre `/teamwork-preview` nativo (protege la cuota principal e impone `verify_handoff.py`).
1. **Oleada 1 Recon** (paralelo): `recon-scout` (`flash`) + `memory-archivist` (`flash_lite`) / `memory_search.py`, solo lectura.
2. **Oleada 2 Plan**: `mentor-architect` (*Marco*) con Argon (`-m argon --agent mentor-architect --mode plan`) / `-m gpt` (o `flash` en Student Lite).
3. **Oleada 3 Ejecución** (paralela, archivos disjuntos): `frontend-crafter` + `worker-builder`; `qa-auditor` solo lectura (`--mode plan --sandbox`).
4. **Oleada 4 Cierre**: `verify_handoff.py` + chequeo de cuota y reporte de ahorro:
   ```bash
   python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/view_tokens.py --weekly --quota
   ```
   Luego `memory-archivist` sella la ficha e Instincts (`learn_instinct.py`: dry-run primero → confirmar con el usuario → `--apply`) en `memory/` y `MEMORY.md`.

## 5. Zero-Syntax UX (Frases Naturales → Acción Interna)
El usuario nunca necesita memorizar rutas ni flags; traduce sus peticiones en lenguaje natural:

| Petición natural del usuario | Acción interna ejecutada |
|---|---|
| *"¿Cómo voy de cuota esta semana?"* | `view_tokens.py --weekly --quota` (o `--daily --quota`) |
| *"Revisa mi proyecto y dime por dónde empezar"* | `invoke_subagent` → `recon-scout` (`flash`) + `ast_outline.py` |
| *"Haz un plan antes de programar / explícame la arquitectura"* | Grill Gate (`ask_question`) + Oleada 2 con `mentor-architect` (`-m argon --agent mentor-architect --mode plan` o `flash`) |
| *"Hazlo en modo estudiante / ahorro"* | Modo Student Lite (`COS_PROFILE=lite`, subagentes `flash`/`flash_lite`) |
| *"Consulta al consejo / segunda opinión"* | `consult_council.py -m claude` / `-m argon` / `-m gpt` |
| *"Verifica si todo compila limpio"* | `verify_handoff.py --scope <archivos>` (sintaxis + scope git + secret-scan) |
| *"Busca o guarda esto en memoria / aprende esta regla"* | `memory_search.py "<query>"` (FTS5) / `learn_instinct.py` (dry-run → preguntar → `--apply`) / `memory-archivist` (`flash_lite`) |
