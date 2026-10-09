# Aprende y verifica el proyecto paso a paso

Este es un portafolio de estudiante. Puedes defenderlo explicando sus decisiones y demostrando sus pruebas; no necesitas presentarte como senior. Dedica una sesión a cada paso y escribe con tus palabras lo que observaste antes de avanzar.

## 1. Preparar una copia de trabajo

Abre la carpeta del repositorio en tu editor y una terminal PowerShell en esa misma carpeta. Usa Python 3.12; no uses 3.13 con estas dependencias de red.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock.txt
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m pytest -q
```

No necesitas activar el entorno con estos comandos. Debes ver `No broken requirements found` y `110 passed`. Pueden aparecer dos advertencias heredadas sobre `pkg_resources` y `telnetlib`; están documentadas y pendientes de modernización. Las pruebas no necesitan `.env`, equipos ni cuenta de Google. Si falla la instalación, conserva el mensaje antes de intentar modificar dependencias.

**Qué aprender:** el entorno aísla las bibliotecas y el archivo de bloqueo conserva las versiones y hashes. Esto ayuda a otra persona a reproducir tu trabajo.

## 2. Seguir el recorrido de un evento

Lee en este orden:

| Archivo | Pregunta que debes poder responder |
|---|---|
| `config/config.yaml` y `inventory/` | ¿De dónde salen los dispositivos y cuántos trabajos de red pueden ejecutarse? |
| `src/core/network_tasks.py` | ¿Por qué Cisco y MikroTik necesitan comandos distintos? |
| `src/run_engine.py` | ¿Cómo se separan los fallos de recolección y los fallos de IA? |
| `src/core/telemetry_privacy.py` | ¿Qué patrones se ocultan antes de enviar datos? ¿Cuáles podrían escapar? |
| `src/core/ai_analyzer.py` | ¿Qué diferencia hay entre una observación y una hipótesis? |
| `src/core/ai_resilience.py` | ¿Cuándo se deja de llamar temporalmente al proveedor? |

El programa consulta logs y propone comprobaciones humanas. No cambia la configuración de los dispositivos. Un timeout de Gemini no demuestra una avería de red.

## 3. Entender una prueba pequeña

Lee `tests/test_diagnostic_integrity.py` y localiza las pruebas del comando por plataforma. Ejecuta solo ese archivo:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_diagnostic_integrity.py -v
```

Identifica qué se prepara, qué función se ejecuta y qué comprueba cada `assert`. Los dobles simulan respuestas y errores; Nornir conserva su funcionamiento real. Explica por qué rechazar una plataforma desconocida evita ejecutar un comando equivocado.

## 4. Observar la concurrencia y la protección

```powershell
.venv\Scripts\python.exe -m scripts.demo_resilience
.venv\Scripts\python.exe -m pytest tests/test_ai_resilience.py -v
```

La demo imprime resultados de una simulación y actualiza `docs/DEMO_RESULTS.json` con tus tiempos. Ese archivo aparecerá modificado en Git; no tienes que publicar tu medición para completar el ejercicio. Compara un trabajador con tres: los tiempos cambian entre máquinas y no representan rendimiento de Gemini ni mejora de MTTR. Lee `test_breaker_recovery_and_stale_response`: un reloj simulado permite comprobar recuperación sin esperar tiempo real.

**Qué aprender:** la concurrencia reduce espera cuando hay tareas independientes; limitarla ayuda a controlar carga. El circuit breaker evita insistir ante fallos transitorios, pero no corrige al proveedor.

## 5. Revisar los controles locales

```powershell
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy
```

Ruff detecta errores de estilo y ciertos errores comunes; mypy revisa contratos de tipos en la aplicación. Ninguno demuestra que la lógica sea correcta. Esa responsabilidad se complementa con pytest. Algunas bibliotecas externas no tienen tipos adecuados y se excluyen de la revisión estricta; los tests sí se revisan con Ruff.

## 6. Revisar la propuesta en GitHub

Abre el pull request y revisa `Files changed` en grupos: red, IA, resiliencia, pruebas y documentación. Puedes dejar comentarios con las líneas que quieras estudiar. En `Checks` espera cinco trabajos: uno de calidad y cuatro combinaciones de sistema operativo y Python. Abre un trabajo y consulta sus pasos; el resultado de pytest muestra cuántas pruebas se ejecutaron.

Una marca verde acredita esos controles para ese commit. No acredita funcionamiento en routers reales ni preparación para producción. El borrador conserva la propuesta para estudio; la incorporación a `main` es un paso posterior de revisión.

Para practicar después de revisar, crea una rama personal y añade una prueba pequeña de una plataforma no soportada. Ejecuta primero ese test y luego la suite completa. Evita cambiar varios módulos a la vez: una modificación pequeña permite entender la relación entre el cambio y su resultado.

## 7. Explicarlo en una entrevista

Una presentación honesta puede ser: «Estoy desarrollando un proyecto de aprendizaje que recolecta logs con Nornir y separa errores de red de errores del proveedor de IA. Incorporé pruebas simuladas y CI para comprobar los cambios sin equipos ni gasto de API. Todavía debo validarlo con equipos de laboratorio y actualizar las dependencias de red».

Antes de usar esa presentación, verifica que puedas mostrar una prueba y explicar su resultado. Una inferencia sintética real fue exitosa con el modelo indicado en `.env.example`; eso valida esa llamada concreta, no la exactitud general de los diagnósticos. No atribuyas experiencia empresarial ni métricas de producción a la demo.

La siguiente fase sugerida es validar inventario y respuestas CLI, con una mejora pequeña por sesión. Dashboard y auto-remediación pueden esperar hasta que esta base sea comprensible y verificable.
