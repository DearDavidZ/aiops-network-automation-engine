import logging
import sys
from pathlib import Path
from typing import Any

from nornir import InitNornir
from nornir.core import Nornir
from nornir.core.inventory import Host

# Configuración del motor de logging estructurado
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger: logging.Logger = logging.getLogger("InventoryValidator")


def initialize_orchestrator(config_path: Path) -> Nornir:
    """
    Inicializa el motor de Nornir verificando la existencia del archivo maestro de configuración.

    Args:
        config_path (Path): Ruta al archivo config.yaml.

    Returns:
        Nornir: Instancia inicializada del orquestador.

    Raises:
        FileNotFoundError: Si la ruta de configuración es inválida.
        Exception: Ante fallos de parsing de YAML o esquemas de inventario corruptos.
    """
    if not config_path.is_file():
        logger.error("Ruta de configuración no encontrada: %s", config_path.resolve())
        raise FileNotFoundError(f"Archivo de configuración inexistente: {config_path}")

    try:
        logger.info("Inicializando motor Nornir desde: %s", config_path.name)
        nr_engine: Nornir = InitNornir(config_file=str(config_path))
        return nr_engine
    except Exception as exc:
        logger.critical("Fallo catastrófico al instanciar Nornir: %s", exc, exc_info=True)
        raise


def audit_inventory_schema(nr_instance: Nornir) -> None:
    """
    Ejecuta aserciones estrictas sobre los nodos cargados en memoria.

    Args:
        nr_instance (Nornir): Instancia activa del orquestador.
    """
    hosts_pool: dict[str, Host] = nr_instance.inventory.hosts

    if not hosts_pool:
        logger.error("Auditoría fallida: El inventario no contiene dispositivos.")
        sys.exit(1)

    logger.info("Auditoría iniciada: Validando %d nodo(s) registrado(s)...", len(hosts_pool))

    for host_name, host_obj in hosts_pool.items():
        # Validación de dirección IP de gestión
        if not host_obj.hostname:
            logger.error("Fallo de integridad: Nodo '%s' carece de hostname/IP.", host_name)
            sys.exit(1)

        # Validación de plataforma para controladores Netmiko
        if not host_obj.platform:
            logger.error("Fallo de integridad: Nodo '%s' no tiene plataforma asignada.", host_name)
            sys.exit(1)

        # Auditoría de metadata empresarial
        site: Any = host_obj.data.get("site", "N/A")
        role: Any = host_obj.data.get("role", "N/A")

        logger.info(
            "Nodo verificado: [%s] -> IP: %s | Plataforma: %s | Rol: %s | Sitio: %s",
            host_name,
            host_obj.hostname,
            host_obj.platform,
            role,
            site,
        )


def main() -> None:
    """Punto de entrada principal para el análisis estático del inventario."""
    project_root: Path = Path(__file__).resolve().parent.parent
    config_file_path: Path = project_root / "config" / "config.yaml"

    try:
        nornir_engine: Nornir = initialize_orchestrator(config_path=config_file_path)
        audit_inventory_schema(nr_instance=nornir_engine)
        logger.info("Resultado de pre-vuelo: Inventario validado con éxito (0 anomalías).")
    except Exception:
        logger.error("La validación de pre-vuelo abortó la ejecución.")
        sys.exit(1)


if __name__ == "__main__":
    main()
