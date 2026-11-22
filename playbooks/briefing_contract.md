# 🎯 Sniper Briefing Contract (Protocolo de Despacho Táctico v5.0)

El Chief of Staff DEBE incluir exactamente estas 5 líneas al convocar a cualquier subagente (`invoke_subagent` o `consult_council.py --agent`). Prohibido enviar volcados de contexto difusos.

## Formato Estricto de 5 Líneas (Entrada)
```yaml
1. TARGET: [Ruta absoluta de archivo, IP, host SSH o URL exacta]
2. SCOPE:  [Rango exacto de líneas (ej. L30-L75), función, endpoint ISAPI o dominio exclusivo]
3. OUTPUT: [Formato exacto esperado: diff unificado, JSON validado, tabla o booleano]
4. BUDGET: [Límite máximo de pasos de herramientas: ej. 3 llamadas / 2 comandos]
5. FORBID: [Acciones prohibidas: NO pisar archivos de otros, NO broad scan, NO herramientas fuera de rol, CERO cortesía]
```

## Formato Estricto de Cierre: Typed Handoff Packet (Salida)
Todo subagente que realice modificaciones (`worker-builder`, `frontend-crafter`) debe adjuntar al final de su reporte en `scratch/*.md` un bloque YAML tipado de cierre:

```yaml
```yaml
HANDOFF_PACKET:
  STATUS: DONE # o FAILED
  TOUCHED_FILES:
    - /ruta/exacta/archivo1.py
  SCOPE_VIOLATION: false
  PREFLIGHT_CMD: "python3 ~/.gemini/config/plugins/chief-of-staff/skills/chief-of-staff-ops/scripts/verify_handoff.py --scope /ruta/exacta/archivo1.py"
  VERIFY_CMD: "pytest tests/test_especifico.py" # o comando de test relevante
```
```

## Reglas Anti-Colisión & Mínimo Privilegio (v5.0)
1. **Aislamiento de Escritura (No Pisarse)**:
   - Solo **un** agente de escritura (`worker-builder` o `frontend-crafter`) puede editar un archivo a la vez. Si hay trabajo paralelo, debe usarse `Workspace: "branch"` o ejecutarse en estricta secuencia.
   - Todo subagente debe respetar estrictamente su `SCOPE`. Tocar archivos fuera del `SCOPE` es aborto inmediato detectado por `verify_handoff.py`.
2. **Mínimo Privilegio de Herramientas (Cero Bloat)**:
   - `recon-scout` y `cyber-auditor`: Nunca reciben herramientas de edición o creación de archivos.
   - `qa-auditor`: Solo herramientas de test y diff (`view_file`, `run_command`, `send_message`, `manage_task`); tiene prohibido editar el código bajo prueba.
   - `memory-archivist`: Solo opera sobre `/memory/` y `MEMORY.md`.
3. **Embudo Quirúrgico "Agentless" (SWE-bench)**:
   - `recon-scout` localiza coordenadas exactas con `ast_outline.py`.
   - `worker-builder` entra directo al rango de líneas sin hacer búsquedas globales a ciegas.
4. **Ciego Cruzado (Blind Twin Dispatch - BMAD)**:
   - Para tareas críticas, `worker-builder` programa la solución y `qa-auditor` programa los tests de fallo en paralelo a partir de la misma especificación, sin que QA vea el código de Builder.
5. **Escudo de Cuotas v5.0 (Balance Real Multi-Modelo)**:
   - **Orquestador**: Jamás escribe o edita >25 líneas de código o HTML.
   - **Prohibido `inherit`/`pro` en `invoke_subagent`**: Si el orquestador corre en Hydrogen/Neon/Pro, está PROHIBIDO invocar subagentes con `Model=inherit` o `Model=pro`.
   - **Matriz de Ruteo v5.0**:
     - Exploración / Lectura / Memoria -> `invoke_subagent` (`recon-scout`, `memory-archivist`) SOLO con `flash` / `flash_lite`.
     - Coding / Refactor / Debug / Tests / QA Crítico -> `consult_council.py -m claude --agent worker-builder --exec --dir <workspace>` (o `--agent qa-auditor`, gastando cuota Claude 5.5).
     - Arquitectura / Frontend / UX / Diseño -> `consult_council.py -m argon --agent frontend-crafter --exec --dir <workspace>` (o `--mode plan`, gastando cuota Argon 4).
     - Segunda opinión / Desempate -> `consult_council.py -m gpt`.
6. **Protocolo Telegrama (≤12 líneas)**:
   - Subagentes NUNCA retornan más de 12 líneas al turno principal. Cualquier reporte extenso va a disco (`scratch/*.md`) y la respuesta contiene solo un resumen ejecutivo de ≤10 líneas + ruta del archivo.
