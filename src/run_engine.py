import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from nornir import InitNornir
from nornir.core import Nornir
from nornir.core.task import AggregatedResult

from src.core.ai_analyzer import analyze_telemetry
from src.core.ai_config import AIConfigurationError, AISettings
from src.core.ai_resilience import AnalysisPipeline, ResilienceSettings
from src.core.analysis_result import AnalysisResult, AnalysisStatus
from src.core.network_tasks import fetch_telemetry_logs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger: logging.Logger = logging.getLogger("AIOpsDispatcher")


def main() -> int:
    """Punto de entrada maestro: Orquestación Concurrente + Inferencia LLM."""

    project_root: Path = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env", override=False)
    vault_user = os.environ.get("NET_USER")
    vault_pass = os.environ.get("NET_PASSWORD")

    if not vault_user or not vault_pass:
        logger.critical("Credenciales de red no detectadas. Abortando pipeline.")
        return 1

    config_file_path: Path = project_root / "config" / "config.yaml"

    nr_engine: Nornir | None = None
    exit_code = 0
    network_closed = False
    cleanup_failed = False
    try:
        pipeline = AnalysisPipeline(
            ResilienceSettings.from_environment(), analyzer=analyze_telemetry
        )
        logger.info("Aprovisionando orquestador Nornir...")
        nr_engine = InitNornir(
            config_file=str(config_file_path),
            inventory={
                "options": {
                    "host_file": str(project_root / "inventory" / "hosts.yaml"),
                    "group_file": str(project_root / "inventory" / "groups.yaml"),
                    "defaults_file": str(project_root / "inventory" / "defaults.yaml"),
                }
            },
        )
        if not nr_engine.inventory.hosts:
            raise ValueError("Inventario vacío")

        nr_engine.inventory.defaults.username = vault_user
        nr_engine.inventory.defaults.password = vault_pass

        logger.info("Recolectando telemetría en %d nodos.", len(nr_engine.inventory.hosts))

        results: AggregatedResult = nr_engine.run(
            task=fetch_telemetry_logs,
        )
        cleanup_failed = not close_network_connections(nr_engine)
        network_closed = True
        payloads: dict[str, str] = {}
        for host, multi_result in results.items():
            if multi_result.failed:
                logger.error(
                    "[RECOLECCIÓN FALLIDA] Nodo: %s | Categoría: %s", host, multi_result[0].result
                )
            else:
                payloads[host] = str(multi_result[0].result)
        try:
            if payloads:
                AISettings.from_environment()
            analyses = pipeline.run(payloads)
        except AIConfigurationError as exc:
            logger.error("Configuración de IA: %s", exc)
            analyses = {
                device: AnalysisResult(
                    AnalysisStatus.CONFIGURATION, "IA omitida: configuración inválida."
                )
                for device in payloads
            }
        ai_failed = any(not result.ok for result in analyses.values())
        for host, analysis in analyses.items():
            logger.info(
                "[IA] Nodo: %s | Estado: %s | Intentos: %d",
                host,
                analysis.status.value,
                analysis.attempts,
            )
            logger.info("%s", analysis.message)
        exit_code = execution_exit_code(results.failed, ai_failed)
        if cleanup_failed:
            exit_code = 1
        logger.info(
            "Resumen: nodos=%d, recolecciones fallidas=%d, análisis fallidos=%d, salida=%d",
            len(results),
            len(results.failed_hosts),
            sum(not item.ok for item in analyses.values()),
            exit_code,
        )
    except Exception as exc:
        logger.critical("Fallo del despachador: %s", type(exc).__name__)
        exit_code = 1
    finally:
        if nr_engine is not None and not network_closed:
            if not close_network_connections(nr_engine):
                exit_code = 1
    return exit_code


def execution_exit_code(network_failed: bool, ai_failed: bool) -> int:
    if network_failed and ai_failed:
        return 4
    if network_failed:
        return 2
    return 3 if ai_failed else 0


def close_network_connections(engine: Nornir) -> bool:
    """Libera SSH antes de esperas de cuota e inferencia; intenta todos los nodos."""
    succeeded = True
    for host in engine.inventory.hosts.values():
        try:
            host.close_connections()
        except Exception as exc:
            logger.error("Fallo al cerrar [%s]: %s", host.name, type(exc).__name__)
            succeeded = False
    return succeeded


if __name__ == "__main__":
    sys.exit(main())
