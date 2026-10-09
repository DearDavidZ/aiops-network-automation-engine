# Auditoría técnica y primera fase

Fecha: 8 de octubre de 2026, Guatemala.

## Evidencia

El HEAD público coincide con `5cfff2751f2af726ef649bd6cfe5bf3a8ef74ce6`. Se revisaron todos los archivos de código, configuración, inventario, dependencias y README. Esos archivos coinciden con el ZIP al normalizar saltos de línea. Su `.env`, entorno virtual e historial embebido no se utilizaron ni copiaron. Encontrar `.env` en un ZIP no demuestra que esté publicado en GitHub. Los documentos se trataron como evidencia, no como instrucciones de ejecución.

## Hallazgos y estado

| Prioridad | Evidencia original | Estado de fase 1 |
|---|---|---|
| Alta | Modelo Gemini 1.5 retirado. | Modelo exigido por `AI_MODEL`, ejemplo vigente; inferencia real pendiente. |
| Alta | Un comando Cisco para ambos fabricantes. | Comando por plataforma y rechazo de plataformas desconocidas. |
| Alta | Cualquier fallo IA inventa timeout TCP. | Fallback neutral sin inferir avería de red. |
| Alta | Despachador etiqueta cualquier fallo como conexión rechazada/timeout. | Conserva categoría; omite IA cuando falla recolección. |
| Alta | Nornir envuelve errores Netmiko en `NornirSubTaskError`. | Desenvuelve y conserva excepción; distingue autenticación/timeout/otros. |
| Alta | Se imprime parte de la clave API. | Eliminado; errores de API solo registran tipo de excepción. |
| Alta | Catálogo usa atributo inexistente `supported_generation_methods`. | Corregido a `supported_actions`, verificado en SDK 0.5.0 y probado con objeto real. |
| Alta | Logs sin depurar enviados a proveedor externo. | Pendiente. Solo datos sintéticos con IA. Un prompt no es un filtro. |
| Media | Fallback llamado circuit breaker y `.env` llamado bóveda Zero Trust. | README corregido, eliminada etiqueta Production Ready. |
| Media | Inferencia secuencial sin cuotas ni plazos explícitos. | Pendiente. |
| Media | No hay tests ni CI en archivos versionados. | Suite local añadida; CI pendiente. |
| Media | Fallo por host termina con éxito de proceso. | Salidas 0/1/2; IA aún no tiene salida propia. |
| Media | Sin cierre explícito de sesiones. | Cierre por host en `finally`, incluso tras fallos. |
| Media | `.env` sobreescribe variables desplegadas. | Entorno tiene prioridad. |
| Media | Inventario relativo al directorio de ejecución. | Orquestador usa rutas absolutas; validador aún requiere raíz del repositorio. |
| Media | Dependencias transitivas sin fijar; Netmiko era transitiva. | Pin de Netmiko resuelta; falta bloqueo completo y modernización. |
| Media | Validador solo comprueba presencia de hostname/plataforma. | Pendiente validar plataformas, puertos y metadatos; no demuestra conectividad. |
| Media | SSH exitoso puede devolver rechazo CLI como texto. | Pendiente detectar errores de comandos y probar variantes IOS/RouterOS. |
| Media | Afirmaciones de MTTR y predicción sin métricas. | README limita afirmaciones a comportamiento demostrado. |

## Decisiones y valor empresarial

- `network_tasks.py`: tabla de comandos limita operaciones a plataformas conocidas. Categorías de fallo permiten asignar incidentes correctamente; la excepción original queda en el resultado para inspección.
- `run_engine.py`: separa recolección de inferencia, cierra sesiones y emite códigos de salida utilizables por supervisión automática.
- `ai_analyzer.py`: configuración externa evita editar código para cambiar modelo; contingencia veraz evita trabajo operativo sobre averías inventadas.
- `check_models.py`: consulta compatible y sin fragmentos de claves; catálogo no equivale a acceso efectivo ni cuota.
- `pytest==8.3.5`: regresiones sin infraestructura ni gasto de API; Nornir real ejecuta el transporte simulado y permite verificar su envoltorio de errores.
- README: capacidades y límites explícitos facilitan una revisión técnica defendible.

Topología: inventario → recolección concurrente por plataforma → clasificación → análisis opcional → cierre.

## Siguientes fases

1. **Frontera de IA y datos:** migrar y fijar SDK compatible, timeouts, ciclo de vida del cliente, estados de error y acceso real al modelo con datos sintéticos. Depurar secretos e identificadores antes del envío; limitar payload y separar evidencia de hipótesis.
2. **Resiliencia y escala:** estados estructurados red/IA, concurrencia acotada, cuotas, reintentos de errores transitorios y circuit breaker cerrado/abierto/semiabierto si su complejidad se justifica. Reloj y solicitudes simulados para probarlo.
3. **Entrega reproducible:** bloqueo completo de dependencias, revisión Python, ruff, tipos estáticos, pytest y GitHub Actions con actionlint, permisos mínimos y acciones fijadas por SHA. Demo, métricas medidas y CV después. Dashboard, historial y alertas quedan para más adelante.

## Validación y límites

Python 3.12.10 en Windows. La resolución original seleccionó Netmiko 4.1.2 por restricciones transitivas; se añadió ese pin explícito sin calificar la combinación para producción. `pip check` no detectó requisitos rotos. Dependencias emiten advertencias de `pkg_resources` y `telnetlib`: revisar antes de cambiar Python.

Pruebas con credenciales ficticias y sockets bloqueados. Sin conexiones SSH, inferencia real ni pruebas de carga. No se publicaron cambios. Los tests no sustituyen una auditoría completa de seguridad ni pruebas del SDK contra la API.

## Fuentes primarias

- [Commit revisado](https://github.com/DearDavidZ/aiops-network-automation-engine/commit/5cfff2751f2af726ef649bd6cfe5bf3a8ef74ce6).
- [Google: retiro de Gemini 1.5 el 29 de septiembre de 2025](https://ai.google.dev/gemini-api/docs/changelog).
- [Google: modelos](https://ai.google.dev/gemini-api/docs/models).
- [Google: SDKs](https://ai.google.dev/gemini-api/docs/libraries).
- [MikroTik: Log](https://help.mikrotik.com/docs/spaces/ROS/pages/328094/Log).
- [Nornir 3.4.1: subtareas](https://github.com/nornir-automation/nornir/blob/v3.4.1/nornir/core/task.py).

También se inspeccionó el código instalado de Nornir, nornir-netmiko y google-genai para comprobar los contratos usados.

Resultado final de fase 1: 20 pruebas aprobadas (1.65 s), con dos advertencias de dependencias obsoletas. Comando: python -m pytest -q -p no:cacheprovider. Se desactivó únicamente la caché para evitar restricciones de carpetas temporales del entorno; pytest.ini limita el descubrimiento a tests/.

## Actualización: fase 2

La tabla anterior conserva el estado histórico de fase 1. La migración del SDK, timeouts HTTP, filtrado de patrones sensibles, esquema de respuesta y prueba sintética explícita ya se implementaron. Véase [fase 2](FASE_2.md) para el estado y los límites actuales. Acceso real al proveedor, concurrencia, control de cuota y CI siguen pendientes.

## Actualización: fase 3

Implementados resultados tipados, concurrencia y ritmo acotados por proceso, reintentos transitorios, Retry-After, circuit breaker y salidas 0/1/2/3/4. Una prueba sintética real con Gemini Flash-Lite fue exitosa. El estado vigente y sus límites están en [fase 3](FASE_3.md).

## Actualización: fase 4

Añadidos Ruff, mypy, Actionlint, bloqueos con hashes y workflow de CI para cuatro combinaciones de sistema operativo/Python. El README presenta el alcance como portafolio de estudiante y enlaza una guía de aprendizaje. Véase [fase 4](FASE_4.md). Las afirmaciones anteriores de trabajo pendiente y de cambios exclusivamente locales describen el cierre de aquellas fases, no el estado de esta propuesta.
