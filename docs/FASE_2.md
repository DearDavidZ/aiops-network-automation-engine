# Fase 2: frontera de IA y datos

## Qué cambia y por qué

El flujo es **telemetría → depuración local → control de tamaño → Gemini → validación y depuración de respuesta**. Se mantiene la recolección de Nornir y la inferencia secuencial; esta fase modifica la frontera del proveedor.

| Componente | Decisión | Valor empresarial |
|---|---|---|
| `ai_config.py` | Configuración tipada; valida modelo, clave y rangos antes de abrir cliente. Clave excluida del repr. | Fallos detectables sin transmitir datos ni imprimir configuración sensible. |
| `telemetry_privacy.py` | Depuración local conservadora, rechazo de entradas excesivas y claves PEM. | Reduce exposición y volumen; preserva señales operativas cuando es posible. |
| `ai_analyzer.py` | SDK fijado, timeout HTTP, un intento y cierre en finally. | Recursos liberados y comportamiento predecible ante proveedor caído o sin cuota. |
| `Diagnosis` | Esquema con observaciones, hipótesis y comprobaciones, listas y textos acotados. | Permite revisar hipótesis sin presentarlas como causa raíz comprobada. |
| `check_models.py` | Catálogo acotado a 100 modelos y prueba de inferencia explícita con evento sintético. | Distingue catálogo de acceso real, con códigos de salida útiles. |
| Pruebas de contrato | SDK real contra HTTP simulado. | Detectan cambios de serialización y verifican el contenido enviado sin costo de API. |

## Dependencias

- `google-genai==2.29.0`, verificado en metadatos de PyPI y código instalado.
- `pydantic==2.14.0`, requerido para satisfacer el rango del SDK actualizado.
- `httpx==0.28.1`, transporte del SDK y excepciones de timeout usadas directamente.

No se modernizó el stack de red ni se generó todavía un lock multiplataforma de dependencias indirectas. Siguen pendientes las advertencias de Nornir/Netmiko sobre pkg_resources y telnetlib.

## Contrato de entrada

Las credenciales se leen del entorno; `.env` tiene menor prioridad. `AI_MODEL` debe tener un identificador Gemini, opcionalmente precedido de `models/`; validarlo no demuestra su existencia ni acceso.

`AI_TIMEOUT_MS`: 20000 por defecto, de 1000 a 120000. El SDK recibe milisegundos y los convierte para HTTPX. Es un timeout del transporte (conexión/lectura/escritura/pool), **no un plazo total estricto** de pared para la ejecución. `HttpRetryOptions(attempts=1)` desactiva los reintentos implícitos del SDK. El control de cuota y plazos globales corresponde a la fase siguiente.

`AI_MAX_PAYLOAD_CHARS`: 8000 por defecto, de 256 a 32000. El límite absoluto previo a depurar es 65536 caracteres. Después se depura y se comprueba el tamaño, sin truncar: así no se cortan secretos ni se omite silenciosamente evidencia. Son caracteres, no tokens ni bytes.

## Alcance del filtro

- Omite el nombre real del nodo en el prompt; usa un alias constante.
- Elimina valores conocidos de nombre de nodo, clave API, usuario y contraseña de red.
- Elimina líneas que contienen patrones de contraseñas, tokens, secretos, autorización, cookies, comunidades SNMP y claves API, incluidos nombres compuestos frecuentes.
- Rechaza claves privadas PEM, incluso incompletas.
- Sustituye URLs, correos, IPv4/IPv6, MAC, nombres DNS y patrones de cuentas.
- Elimina controles de texto y controles bidireccionales reconocidos.
- Depura también los textos estructurados devueltos antes de exponerlos al orquestador.

Es una reducción de datos basada en patrones: puede ocultar datos útiles, incluyendo horas que se parezcan a IPv6. No reconoce toda identidad, nombre de cliente, cadena codificada, secreto fragmentado o dato empresarial sin etiqueta. No es una garantía de anonimización ni DLP completo. Tampoco cambia todos los logs internos de Nornir. Usar datos sintéticos hasta validar la política de envío de datos de la organización.

## Contrato de salida

El SDK solicita JSON y la aplicación vuelve a validar el texto con Pydantic. Campos obligatorios: `observations` (1–3), `hypotheses` (0–3), `checks` (1–3); cada texto admite 1–600 caracteres, sin campos adicionales. El límite solicitado es 1024 tokens de salida y se rechaza texto recibido superior a 16000 caracteres. Una respuesta que no termine normalmente, esté bloqueada, vacía o no cumpla esquema se marca no disponible.

Los datos y la instrucción del sistema van separados. No hay herramientas ni ejecución de acciones; las instrucciones no garantizan resistencia total a prompt injection. La validación estructural tampoco prueba que las observaciones o hipótesis del modelo sean verdaderas. Se conserva revisión humana.

Errores 401/403, 404, 429 y timeout tienen mensajes diferenciados. Errores del SDK y del servidor no exponen su cuerpo o mensaje crudo. El fallo IA sigue separado de la red. El orquestador conserva su contrato de texto y códigos de salida de fase 1; la salida 0 **todavía no certifica disponibilidad de IA**.

El cliente síncrono se crea y cierra por llamada. La reutilización/pooling junto con concurrencia acotada se abordará en la siguiente fase.

## Comprobación real opcional

Con las dependencias instaladas y `.env` configurado localmente, `python check_models.py --probe` envía exclusivamente un evento sintético fijo. Consume API/cuota. No lee inventario ni envía logs operativos. Salida 0 significa respuesta recibida y validada; 1 indica análisis no disponible. No ejecutar el recolector para probar por primera vez una clave.

Durante esta fase no se utilizó el `.env` del ZIP ni se realizó inferencia real. La suite prueba también el comando de comprobación con HTTP simulado. El acceso real de la cuenta queda pendiente de esa comprobación, no demostrado por los tests.

## Fuentes primarias

- [Google Gen AI SDK y gestión de clientes](https://googleapis.github.io/python-genai/).
- [Publicación google-genai 2.29.0](https://pypi.org/project/google-genai/2.29.0/).
- [Publicación Pydantic 2.14.0](https://pypi.org/project/pydantic/2.14.0/).

Se inspeccionaron también los campos HttpOptions/HttpRetryOptions y el transporte de la versión instalada para verificar unidades, número de intentos y propiedad del cliente HTTP.

## Resultado de verificación

78 pruebas aprobadas en 11.80 s con Python 3.12.10 en Windows. Comando: python -m pytest -q -p no:cacheprovider. pip check no detectó requisitos rotos. Las dos advertencias corresponden al stack de red heredado. Se verificaron solicitudes y respuestas con transporte HTTP simulado, incluyendo timeout, 401/403/404/429/500/503, cierre, privacidad, esquemas y el comando --probe. No hubo inferencia real ni publicación en GitHub.

## Evolución posterior

La [fase 3](FASE_3.md) añadió coordinación de solicitudes, nuevos códigos de salida y una prueba real exitosa con datos sintéticos. También corrigió la incompatibilidad de additionalProperties detectada por la API real. Las referencias anteriores a inferencia pendiente y al contrato de salida previo describen el estado histórico de fase 2.
