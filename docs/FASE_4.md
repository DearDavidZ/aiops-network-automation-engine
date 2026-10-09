# Fase 4: entrega reproducible y aprendizaje

Fecha: 9 de octubre de 2026. El proyecto conserva su condición experimental y se presenta como portafolio de estudiante.

## Cambios y propósito

| Control | Utilidad práctica |
|---|---|
| Ruff 0.17.0 | Mantener estilo consistente y detectar errores comunes antes de revisar cambios. |
| mypy 2.4.0 en modo estricto | Revisar tipos de la aplicación y scripts; dependencias externas sin tipos se omiten. |
| pytest 8.3.5 | Probar resultados y fallos sin red, equipos ni gasto de API. |
| Actionlint 1.7.12 | Detectar errores en la definición del workflow antes de confiar en la automatización. |
| Bloqueo con uv 0.13.0 | Fijar dependencias indirectas y hashes para reproducir instalaciones. |
| Matriz de CI | Comprobar Windows/Linux y Python 3.11/3.12; no presume compatibilidad con 3.13. |

El workflow se ejecuta en pull requests, cambios a `main` y solicitud manual. Solo tiene permiso de lectura del contenido, acciones fijadas por SHA, plazo de diez minutos por trabajo y cancelación de ejecuciones anteriores de la misma referencia. Actionlint se descarga de su publicación oficial con comprobación SHA256. No hay claves de IA en CI ni solicitudes a equipos reales.

## Reproducir

Instala `requirements-dev.lock.txt` como indica la [guía de aprendizaje](APRENDER_PASO_A_PASO.md). Ejecuta Ruff, mypy y pytest con el Python del entorno. Para validar Actionlint localmente, instala el ejecutable oficial de la versión fijada para tu sistema y ejecuta `actionlint` desde la raíz; GitHub Actions realiza esta validación automáticamente.

Cuando se decide actualizar una dependencia, modifica primero su pin en el archivo de requisitos, regenera ambos bloqueos y revisa el cambio:

```powershell
.venv\Scripts\uv.exe pip compile requirements.txt --universal --python-version 3.11 --generate-hashes --output-file requirements.lock.txt
.venv\Scripts\uv.exe pip compile requirements-dev.txt --universal --python-version 3.11 --generate-hashes --output-file requirements-dev.lock.txt
```

Después instala el bloqueo en un entorno nuevo y ejecuta los controles. Regenerar hashes por sí solo no audita la seguridad de las dependencias.

## Evidencia local y límites

Windows: 110 pruebas aprobadas con Python 3.11.17 y 110 con Python 3.12.10. Ruff, formato, mypy, Actionlint y `pip check` sin errores. La prueba en 3.11 utilizó un entorno nuevo instalado con hashes. Las restricciones de carpetas temporales del entorno del asistente requirieron ejecutar pytest fuera de su aislamiento; no se cambió la lógica de las pruebas por ello.

Siguen las advertencias de `pkg_resources` y `telnetlib`. No se hicieron nuevas llamadas a Gemini en esta fase. Las pruebas en Linux se comprueban mediante GitHub Actions; su resultado debe consultarse en el run asociado al pull request.

Los archivos de fases anteriores conservan resultados históricos. Para estudiar el estado actual empieza por README y la guía, y usa el resultado de CI del commit que estés revisando. No se configura protección de ramas ni se incorpora automáticamente la propuesta a `main`.
