import logging

from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException
from nornir.core.exceptions import NornirSubTaskError
from nornir.core.task import Result, Task
from nornir_netmiko.tasks import netmiko_send_command

logger: logging.Logger = logging.getLogger("NetworkEngine")

TELEMETRY_COMMANDS: dict[str, str] = {
    "cisco_ios": "show logging",
    "mikrotik_routeros": "/log print",
}


def fetch_telemetry_logs(task: Task) -> Result:
    """
    Despacha comandos de telemetría de forma concurrente hacia la infraestructura.
    Incorpora blindaje contra particiones de red y fallos de autenticación AAA.

    Args:
        task (Task): El hilo de ejecución inyectado por el orquestador Nornir.

    Returns:
        Result: Objeto estructurado que contiene el payload o el error encapsulado.
    """
    logger.info("Hilo iniciado para nodo [%s] -> Extrayendo telemetría...", task.host.name)

    try:
        command = TELEMETRY_COMMANDS.get(task.host.platform or "")
        if command is None:
            logger.error("Plataforma no soportada en [%s].", task.host.name)
            return Result(
                host=task.host,
                failed=True,
                result="UNSUPPORTED_PLATFORM: no se ejecutaron comandos.",
            )
        execution = task.run(
            task=netmiko_send_command,
            command_string=command,
            enable=False,
            severity_level=logging.DEBUG,
        )
        logger.info("Extracción exitosa en nodo [%s]", task.host.name)
        return Result(host=task.host, result=execution.result)

    except NornirSubTaskError as exc:
        cause = next((item.exception for item in exc.result if item.exception is not None), exc)
        return network_failure(task, cause)
    except Exception as exc:
        return network_failure(task, exc)


def network_failure(task: Task, cause: Exception) -> Result:
    """Conserva la excepción para auditoría sin inventar su causa raíz."""
    if isinstance(cause, NetmikoAuthenticationException):
        category = "AUTHENTICATION_ERROR"
    elif isinstance(cause, NetmikoTimeoutException):
        category = "CONNECTION_TIMEOUT"
    else:
        category = "COLLECTION_ERROR"
    logger.error("Recolección fallida en [%s]: %s", task.host.name, category)
    return Result(host=task.host, result=category, exception=cause, failed=True)
