# Micro-Kernel Operativo v5.0 — Matriz de Ruteo & Balance Real de Cuotas

Complementa `GEMINI.md` sin repetir reglas base.

## 1. Matriz de Ruteo v5.0 (Cuotas Separadas)
- **Exploración / Lectura / Memoria**:
  - `invoke_subagent` (`recon-scout`, `memory-archivist`, `cyber-auditor`) **SOLO** con `Model: "flash"` o `"flash_lite"`.
- **Coding / Refactor / Debug / Tests / QA Crítico** (gasta cuota Claude Sonnet/Opus 5.5):
  - `python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py -m claude --agent worker-builder --exec --dir <workspace> "Briefing"`
  - Para QA/Tests/Seguridad: `--agent qa-auditor` o `--agent cyber-auditor` (usa `-m claude-opus` en decisiones críticas).
- **Arquitectura / Frontend / UX / Diseño** (gasta cuota Argon 4):
  - `python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py -m argon --agent frontend-crafter --exec --dir <workspace> "Briefing"` (o `--mode plan`).
- **Segunda Opinión / Desempate**:
  - `python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/consult_council.py -m gpt "Consulta"`

## 2. Regla Anti-Desperdicio & Verificación
- **PROHIBIDO `invoke_subagent` con `Model="inherit"` o `Model="pro"`** si el orquestador corre en Hydrogen/Neon/Pro; usar siempre Claude 5.5 o Argon 4 vía `consult_council.py` (o `flash` en ajustes menores).
- **Exclusión Mutua & Handoff**: Lecturas en paralelo; escrituras secuenciales por archivo. Todo builder ejecuta `verify_handoff.py` y cierra con `HANDOFF_PACKET`.

## 2b. Grill Gate & Teamwork por Oleadas (v5.1)
- **Grill Gate**: petición abierta/de diseño → 3-4 preguntas cortas vía `ask_question` antes de despachar Claude/Argon; saltar si ya hay `TARGET`/`SCOPE` exactos.
- **Teamwork por Oleadas** (preferir sobre `/teamwork-preview` nativo): 1 Recon paralelo (flash) → 2 Plan (Argon `--mode plan`/GPT) → 3 Ejecución en archivos disjuntos (QA solo lectura) → 4 Cierre (`verify_handoff.py` + `view_tokens.py --last 10 --sessions 5` + `memory-archivist`). Ver `playbooks/teamwork_waves.md`.
