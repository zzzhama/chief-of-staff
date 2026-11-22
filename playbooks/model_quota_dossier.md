# Expediente Táctico: Modelos y Durabilidad de Cuotas en Antigravity (v5.1)

Referencia operativa de modelos configurados en `MODEL_ALIASES` (`consult_council.py`) e `invoke_subagent`, su durabilidad relativa de cuota y reglas de rotación para el Chief of Staff.

## 1. Jerarquía de Durabilidad Relativa de Cuota
```text
Gemini 3.8 Flash > Gemini 4 Hydrogen / Neon ≈ Argon 4 >> Claude 5.5 Sonnet > Claude 5.5 Opus
```
*(GPT-OSS 120B opera como bolsa auxiliar ligera para segundas opiniones y desempates rápidos).*

## 2. Catálogo de Modelos (`MODEL_ALIASES`) y Rol Óptimo

| Familia / Modelo | Aliases en `consult_council.py` (`-m`) | ID Real en `agy` | Durabilidad | Rol Óptimo en Chief of Staff |
|---|---|---|---|---|
| **Gemini 3.8 Flash** | `flash`, `flash-med`, `flash-low` (+ `flash` / `flash_lite` en `invoke_subagent`) | `gemini-3.8-flash-{high,medium,low}` | **Muy Alta** (caballo de batalla) | Exploración (`recon-scout`), memoria (`memory-archivist`), diagnóstico rápido y ejecución completa en **Modo Student Lite**. |
| **Gemini 4 Hydrogen** | `hydrogen`, `hydrogen-xhigh`, `hydrogen-med`, `hydrogen-low` | `gemini-4-hydrogen-{xhigh,high,medium,low}` | **Alta** (pool principal G4) | Orquestador principal alternativo, razonamiento profundo generalista y respaldo cuando Claude entra en fatiga de cuota. |
| **Gemini 4 Neon** | `neon`, `neon-xhigh`, `neon-med`, `neon-low`, `orch-neon` | `gemini-4-neon-*`, `gemini-pro-orchestrator-neon` | **Alta** (pool principal G4) | Orquestación táctica de sesión principal, síntesis ejecutiva y coordinación de oleadas (sin picar código largo directo). |
| **Gemini 4 Argon** | `argon`, `argon-med`, `argon-low`, `orch-argon` | `gemini-4-argon-{high,medium,low}`, `gemini-pro-orchestrator-g1-pro` | **Alta** (`≈ Hydrogen/Neon`) | Arquitectura (`--mode plan`), Frontend, UI/UX, CSS/3D (`frontend-crafter`) y relevo directo de ejecución si Claude supera el 85%. |
| **Claude 5.5 Sonnet** | `claude`, `claude-sonnet`, `claude-sonnet-med`, `claude-sonnet-low` | `claude-sonnet-5-5-{high,medium,low}` | **Media-Baja** (recurso escaso) | Ingeniería quirúrgica de backend, refactoring, scripts complejos (`worker-builder`) y auditoría QA/Tests (`qa-auditor`). |
| **Claude 5.5 Opus** | `claude-opus`, `claude-opus-med`, `claude-opus-low` | `claude-opus-5-5-{high,medium,low}` | **Muy Baja** (élite crítica) | Exclusivo para decisiones de arquitectura críticas, auditorías de seguridad complejas (`cyber-auditor`) o bugs bloqueantes. |
| **GPT-OSS 120B** | `gpt` | `gpt-oss-120b-medium` | **Alta** (uso puntual) | Árbitro de segunda opinión, contraste de trade-offs arquitectónicos y desempate técnico en Oleada 2 (`--mode plan`). |

## 3. Señales de Rotación y Semáforo de Cuotas
Auditar con `view_tokens.py --weekly --quota` (o `--daily --quota`):

- **`🟢 OK` (< 60%)**: Operación normal en **Modo Council Pro** según la Matriz de Ruteo.
- **`🟡 WARN` (≥ 60%) — Moderar**:
  - Reducir esfuerzo (`-m claude-sonnet-med` en vez de `claude`, evitar `claude-opus`).
  - Exigir coordenadas exactas vía `recon-scout` (`flash`) + `ast_outline.py` antes de despachar a un builder para minimizar turnos de lectura en modelos caros.
- **`🔴 CRITICAL` (≥ 85%) — Rotar de inmediato**:
  - Si **Claude 5.5** marca `≥ 85%`: rotar tareas de código/arquitectura a **Argon 4** (`-m argon`), **Hydrogen** (`-m hydrogen`) o **Flash** (`-m flash`).
  - Si múltiples familias Pro están en `🔴 CRITICAL`: activar **Modo Student Lite** (`COS_PROFILE=lite`, 100% `invoke_subagent` con `flash` / `flash_lite`).

## 4. Nota Técnica sobre Telemetría y Presupuesto Local
> **Transparencia operativa**: El binario `agy` CLI no expone un endpoint con el porcentaje exacto de cuota restante en los servidores remotos. Por ello, `view_tokens.py --quota` usa `metrics.jsonl` como fuente de verdad para `Claude 5.5`, `Argon 4` y `GPT-OSS` (evitando doble conteo con `antigravity-cli`) y reporta aparte el chat IDE sin etiqueta de modelo (`Other`), comparando contra `~/.gemini/config/plugins/chief-of-staff/quota_budget.json`. Si notas throttling antes o después del umbral, ajusta `daily_tokens` y `weekly_tokens` en `quota_budget.json`.
