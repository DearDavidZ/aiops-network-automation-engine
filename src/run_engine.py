import os
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv
from nornir import InitNornir
from nornir.core import Nornir
from nornir.core.task import AggregatedResult

from src.core.network_tasks import fetch_telemetry_logs
# 1. IMPORTACIÓN SRE: Reconectamos el cerebro heurístico (LLM)
from src.core.ai_analyzer import analyze_telemetry_with_ai

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger: logging.Logger = logging.getLogger("AIOpsDispatcher")

def main() -> None:
    """Punto de entrada maestro: Orquestación Concurrente + Inferencia LLM."""
    
    # Inyección Zero-Trust con recarga forzada (override=True)
    load_dotenv(override=True)
    vault_user = os.environ.get("NET_USER")
    vault_pass = os.environ.get("NET_PASSWORD")
    
    if not vault_user or not vault_pass:
        logger.critical("Violación Zero-Trust: Credenciales no detectadas en el entorno. Abortando pipeline.")
        sys.exit(1)

    project_root: Path = Path(__file__).resolve().parent.parent
    config_file_path: Path = project_root / "config" / "config.yaml"
    
    try:
        logger.info("Aprovisionando orquestador Nornir...")
        nr_engine: Nornir = InitNornir(config_file=str(config_file_path))
        
        nr_engine.inventory.defaults.username = vault_user
        nr_engine.inventory.defaults.password = vault_pass
        
        target_command = "show logging"
        logger.info("Disparando ejecución concurrente: '%s' en %d nodos.", target_command, len(nr_engine.inventory.hosts))
        
        results: AggregatedResult = nr_engine.run(
            task=fetch_telemetry_logs,
            command=target_command
        )
        
        # 2. FUSIÓN AIOPS: Ingesta de resultados hacia la Inteligencia Artificial
        logger.info("--- Resumen de Ejecución e Inferencia AIOps ---")
        for host, multi_result in results.items():
            task_result = multi_result[0]
            payload_str = str(task_result.result)
            
            logger.info("Solicitando diagnóstico a Gemini AI para nodo [%s]...", host)
            # Invocación sincrónica al LLM para evaluar la topología
            ai_diagnosis = analyze_telemetry_with_ai(device_name=str(host), payload=payload_str)
            
            if task_result.failed:
                logger.error("[FALLO DE RED] Nodo: %s | Causa: Conexión rechazada/Timeout", host)
                logger.warning("[DIAGNÓSTICO AIOps] \n%s", ai_diagnosis)
            else:
                logger.info("[ÉXITO] Nodo: %s | Payload extraído correctamente.", host)
                logger.info("[DIAGNÓSTICO AIOps] \n%s", ai_diagnosis)
                
    except Exception as exc:
        logger.critical("Colapso en el despachador principal: %s", exc, exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()