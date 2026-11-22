# Python Daemon Guardrails (micro-playbook)

> Destilado de la auditoría ECC v2.2.3 vs Chief of Staff v5.1. Aplica a daemons/bots Python 3.10+ (`requests` + stdlib, SQLite, SSH/ISAPI). Ej. de referencia: `don_mario` (`daemon.py`, `telegram_bot.py`).
> Roles: **WB** = worker-builder · **QA** = qa-auditor · **CY** = cyber-auditor.

## 1. Redacción de secretos (WB, CY)
- Todo texto que salga a log, Telegram o excepción pasa por `redact(texto, (token, password, ...))`.
- Al envolver errores de red/HTTP que puedan contener la URL con el token: `raise CustomError(redact(str(e), secrets)) from None` (suprime traceback con credenciales).
- Prohibido `logger.exception`/`traceback.print_exc()` sobre errores que incluyan URLs de API con token.
- Secretos solo desde entorno/config; nunca hardcodeados ni en defaults. Token vacío => cliente `enabled = False` (falla segura, sin crash).
- Whitelist estricta de `allowed_users` antes de ejecutar cualquier comando del bot; ignorar el resto en silencio.

## 2. SQLite parametrizado (WB, CY)
- 100% placeholders `?`; prohibido f-string/`%`/`+` en SQL. Los nombres de tabla/columna dinámicos solo desde una constante whitelisted.
- Transacciones con context manager: `with conn:` (commit/rollback) y cierre explícito de conexiones/archivos con `with`.
- Acceso concurrente: una conexión por hilo o lock explícito (`threading.Lock`); nunca compartir cursor entre hilos.

## 3. Timeouts y backoff (WB, QA)
- Toda llamada de red lleva timeout explícito: `requests.*(..., timeout=(connect, read))`, `SshClient`, ISAPI/NVR, Gemini Vision, Telegram long-poll (timeout > poll).
- Reintentos con backoff exponencial + jitter y tope (`delay = min(cap, base * 2**n) + random`), máx. N intentos; solo para errores transitorios (timeout, 5xx, 429). Nunca reintentar 4xx de autenticación.
- El loop del daemon captura excepciones por iteración, loguea redactado y continúa; nunca `except:` desnudo. Usar `raise ... from e` para encadenar o `from None` si hay secretos.
- Argumentos de comandos (`/snap`, `/analiza`) validados contra alias válidos (`CAMERAS`, `_CAMERA_ALIASES`); rechazar lo desconocido.

## 4. Invariantes físicos y privacidad (QA, CY)
- `MOTOR_AUTHORIZED is False` por defecto; ningún camino de código lo cambia en runtime ni acciona motores/PTZ sin autorización explícita del humano.
- Privacidad: si `indoor_paused` (`INDOOR_PRIVACY_KEY`) está activo, cero captura/análisis/envío de cámaras interiores. Verificar en cada ruta (poll, comandos, alertas).
- Cooldowns deterministas (sin aleatoriedad) para alertas; no spamear.
- Cada invariante tiene un test unitario que falla si se rompe (`assert MOTOR_AUTHORIZED is False`, test de privacidad pausada).

## 5. Checklist pre-mortem (QA, CY — marcar antes de cerrar)
1. [ ] Cero tokens/passwords en logs, tracebacks o mensajes de bot (`redact`).
2. [ ] `allowed_users` validado en todos los handlers.
3. [ ] SQL parametrizado en `Store` y cualquier otro acceso.
4. [ ] Argumentos de comandos validados contra alias/whitelist.
5. [ ] Timeouts en todo `requests` y `SshClient`.
6. [ ] Backoff acotado; sin bucles de reintento infinitos ni busy-loops.
7. [ ] `MOTOR_AUTHORIZED is False` y privacidad `indoor_paused` cubiertos por tests.
8. [ ] Sin `except:` desnudo ni errores tragados sin log redactado.
9. [ ] Recursos (conexiones, sockets, archivos, hilos) cerrados vía `with`/shutdown limpio.
10. [ ] `py_compile` / `verify_handoff.py` limpio; opcional `ruff check --select E,F,S`.

## Notas de alcance
- No añadir dependencias (Redis/ORM/capas Repository): el daemon es stdlib + `requests`.
- No activar `antigravity-hooks.json` de ECC (fail-closed, bloquea escrituras sin `hook-bridge.js`).
