import logging
from nornir.core.task import Task, Result
from nornir_netmiko.tasks import netmiko_send_command
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException
logger: logging.Logger = logging.getLogger("NetworkEngine")

def fetch_telemetry_logs(task: Task, command: str) -> Result:
    """
    Despacha comandos de telemetría de forma concurrente hacia la infraestructura.
    Incorpora blindaje contra particiones de red y fallos de autenticación AAA.
    
    Args:
        task (Task): El hilo de ejecución inyectado por el orquestador Nornir.
        command (str): El comando CLI a ejecutar (ej. 'show logging').
        
    Returns:
        Result: Objeto estructurado que contiene el payload o el error encapsulado.
    """
    logger.info("Hilo iniciado para nodo [%s] -> Extrayendo telemetría...", task.host.name)
    
    try:
        execution = task.run(
            task=netmiko_send_command,
            command_string=command,
            enable=False,
            severity_level=logging.DEBUG
        )
        logger.info("Extracción exitosa en nodo [%s]", task.host.name)
        return Result(host=task.host, result=execution.result)
        
    except (NetmikoTimeoutException, NetmikoAuthenticationException) as net_err:
        error_msg = f"Control de Fallo de Red - Conectividad/Autenticación denegada: {str(net_err)}"
        logger.error("Alerta en [%s]: %s", task.host.name, error_msg)
        return Result(host=task.host, result=error_msg, failed=True)
        
    except Exception as exc:
        logger.critical("Colapso no controlado en [%s]: %s", task.host.name, str(exc), exc_info=True)
        return Result(host=task.host, result=f"Error Crítico: {str(exc)}", failed=True)