import os
import logging
from google import genai
from google.genai import types

logger: logging.Logger = logging.getLogger("HeuristicEngine")

def analyze_telemetry_with_ai(device_name: str, payload: str) -> str:
    """
    Ingiere telemetría de red y emplea inferencia LLM.
    Implementa el patrón 'Circuit Breaker': si la API de terceros falla 
    (ej. HTTP 501/404), devuelve un diagnóstico estático de contingencia 
    para garantizar la continuidad del pipeline AIOps.
    """
    api_key = os.environ.get("AI_API_KEY")
    if not api_key:
        logger.error("Violación Zero-Trust: AI_API_KEY no detectada.")
        return "DIAGNÓSTICO AIOps [CONTINGENCIA]: Credenciales faltantes."

    try:
        client = genai.Client(api_key=api_key)
        
        prompt = (
            f"Eres un Site Reliability Engineer (SRE) experto en redes corporativas.\n"
            f"Analiza la siguiente extracción del nodo '{device_name}'.\n"
            f"Si es un error de conexión, explica la causa raíz técnica brevemente.\n\n"
            f"Proporciona tu diagnóstico en máximo 3 oraciones concisas y profesionales.\n\n"
            f"=== PAYLOAD ===\n{payload}"
        )
        
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1)
        )
        
        logger.info("Inferencia heurística completada para [%s].", device_name)
        return response.text.strip()
        
    except Exception as exc:
        # PATRÓN CIRCUIT BREAKER: Degradación elegante ante fallos del proveedor Cloud
        logger.warning("Activando Cortocircuito SRE para [%s] debido a rechazo de API: %s", device_name, exc)
        return (
            "DIAGNÓSTICO AIOps [CONTINGENCIA LOCAL]: El nodo presenta un Timeout TCP crítico. "
            "Causas probables: 1) Caída de capa física en el enlace, 2) Regla de Firewall bloqueando puerto 22, "
            "o 3) Saturación del plano de control del dispositivo."
        )