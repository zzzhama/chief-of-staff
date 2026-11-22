# Micro-Kernel Operativo v5.1 — Modo Dual, Matriz de Ruteo & Balance de Cuotas

Complementa `GEMINI.md` sin repetir reglas base.

## 1. Modo Dual & Matriz de Ruteo (Council Pro vs Student Lite)
- **Modo Council Pro** (por defecto cuando `agy` está disponible y `COS_PROFILE!=lite`):
  - **Auto-Ruteo Inteligente (Recomendado)**: `consult_council.py -m auto --agent <rol> [--task <tipo>] --auto-fallback` elige el modelo óptimo según agente/tarea y rota de familia automáticamente si el Semáforo de Cuotas marca `🔴 CRITICAL` o por health-score de fallos recientes (`--dry-run-route` para previsualizar).
  - **Exploración / Lectura / Memoria**: `invoke_subagent` (`recon-scout`, `memory-archivist`, `cyber-auditor`) **SOLO** con `Model: "flash"` o `"flash_lite"`, más búsqueda local FTS5 en `memory/` con `memory_search.py "<query>"`.
  - **Arquitectura / Mentoría (Oleada 2) & Frontend / UX / Diseño** (cuota Argon 4):
    - Arquitectura y plan (`mentor-architect`, *Marco*): `python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py -m argon --agent mentor-architect --mode plan --dir <workspace> "Briefing"`
    - Frontend, UI y 3D (`frontend-crafter`, *Elena*): `python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py -m argon --agent frontend-crafter --exec --dir <workspace> "Briefing"` (o `--mode plan`).
  - **Coding / Refactor / Debug / Tests / QA Crítico** (cuota Claude 5.5):
    - `python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py -m claude --agent worker-builder --exec --dir <workspace> "Briefing"`
    - Para QA/Tests/Seguridad: `--agent qa-auditor` o `--agent cyber-auditor` (`--mode plan --sandbox`; usa `-m claude-opus` en decisiones críticas).
  - **Segunda Opinión / Desempate**:
    - `python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py -m gpt "Consulta"`
- **Modo Student Lite** (cuando `COS_PROFILE=lite`, el usuario pide modo ahorro/estudiante, o no hay CLI `agy`):
  - Los 7 roles (`recon-scout`, `memory-archivist`, `mentor-architect`, `worker-builder`, `frontend-crafter`, `qa-auditor`, `cyber-auditor`) se despachan vía `invoke_subagent` usando **EXCLUSIVAMENTE** `Model: "flash"` o `"flash_lite"`. Mantiene Grill Gate, Oleadas y `verify_handoff.py` con gasto cero de cuota Pro.

## 2. Regla Anti-Desperdicio, Semáforo de Cuotas & Verificación
- **PROHIBIDO `invoke_subagent` con `Model="inherit"` o `Model="pro"`** si el orquestador corre en Hydrogen/Neon/Pro.
- **Chequeo de Cuota & Autonomía Amable**: El Chief of Staff **decide solo por defecto** el ruteo de modelos auditando antes de oleadas intensivas con:
  `python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/view_tokens.py --weekly --quota`
  (`view_tokens.py` atribuye automáticamente los tokens del chat IDE a su familia rastreando cambios `<USER_SETTINGS_CHANGE>` en `transcript.jsonl`). Si una familia marca `🔴 CRITICAL`, rota a otra familia (`Argon`/`Hydrogen`/`Flash`) o degrada a Student Lite. **Regla de cortesía**: antes de fijar una preferencia, regla o Instinct permanente (*"para siempre"* en `MEMORY.md`, `memory/` vía `learn_instinct.py`, `quota_budget.json` o reglas globales), **ejecuta primero `learn_instinct.py` en dry-run (sin `--apply`) y pregunta con amabilidad** al usuario antes de aplicar `--apply`.
- **Expediente de Modelos y Durabilidad**: Ver `~/.gemini/config/plugins/chief-of-staff/playbooks/model_quota_dossier.md`.
- **Exclusión Mutua & Handoff**: Lecturas en paralelo; escrituras secuenciales por archivo. Todo builder ejecuta `verify_handoff.py` (sintaxis, scope git, escaneo anti-secretos/API keys y verification-loop con `--test-cmd`/`--auto-test`) y cierra con `HANDOFF_PACKET`.

## 2b. Grill Gate & Teamwork por Oleadas (v5.1)
- **Grill Gate**: petición abierta/de diseño → 3-4 preguntas cortas vía `ask_question` antes de despachar builders; saltar si ya hay `TARGET`/`SCOPE` exactos.
- **Teamwork por Oleadas** (preferir sobre `/teamwork-preview` nativo): 1 Recon paralelo (`flash` + `memory_search.py`) → 2 Plan con `mentor-architect` (*Marco*: `-m argon --agent mentor-architect --mode plan` / GPT o `flash` en Student Lite) → 3 Ejecución en archivos disjuntos (QA solo lectura) → 4 Cierre (`verify_handoff.py --auto-test` + `view_tokens.py --weekly --quota` + `session_handoff.py` + `memory-archivist`). Ver `playbooks/teamwork_waves.md`.

## 3. Zero-Syntax UX (Lenguaje Natural → Acción Interna)
El usuario nunca necesita escribir rutas ni flags; traduce su intención directamente:

| Frase natural del usuario | Acción interna del Chief of Staff |
|---|---|
| *"¿Cómo voy de cuota?"* / *"Semáforo de tokens"* | `view_tokens.py --weekly --quota` (o `--daily --quota`) |
| *"Revisa / explora mi proyecto"* | `invoke_subagent` → `recon-scout` (`flash`) + `ast_outline.py` |
| *"Haz un plan paso a paso / explícame la arquitectura"* | Grill Gate (`ask_question`) + Oleada 2 con `mentor-architect` (`-m argon --agent mentor-architect --mode plan` o `flash` Lite) |
| *"Resuélvelo en modo estudiante / ahorro"* | Modo Student Lite (`invoke_subagent` con `flash` / `flash_lite`) |
| *"Pide segunda opinión al consejo"* | `consult_council.py -m claude` / `-m argon` / `-m gpt` |
| *"Verifica si todo compila limpio y pasa los tests"* | `verify_handoff.py --scope <archivos> --auto-test` (sintaxis + scope git + secret-scan + `--test-cmd`/`--auto-test`) |
| *"Busca o guarda esto en memoria / aprende esta regla"* | `memory_search.py "<query>"` (FTS5) / `learn_instinct.py` (dry-run → preguntar → `--apply`) / `memory-archivist` (`flash_lite`) |
| *"Prepara relevo de sesión / ¿toca compactar?"* | `session_handoff.py --threshold 120000` (chequeo de compactación `/compact` y snapshot de relevo) |
