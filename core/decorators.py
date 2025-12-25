from functools import wraps

from nornir.core.task import Task, Result
from rich.console import Console

from core.models import TaskStatus, StandardResult, SubTaskResult
from core.state import config as global_config
from utils.logger import sys_logger

console = Console()


def automated_step(step_name: str):
    """
    Decorator that makes tasks robust.
    1. Logs start and end to file.
    2. Catches unexpected exceptions (Crash Prevention).
    3. Ensures return value is compatible with MatrixEngine.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(task: Task, *args, **kwargs) -> Result:
            host_name = task.host.name
            sys_logger.info(f"START task='{step_name}' host='{host_name}'")

            try:
                # Execution of the actual task
                result = func(task, *args, **kwargs)

                # Consistency check for logging
                status = "UNKNOWN"
                if isinstance(result.result, StandardResult):
                    status = result.result.status.value

                sys_logger.info(f"END task='{step_name}' host='{host_name}' status='{status}'")
                return result

            except Exception as e:
                # CATCH-ALL: If code explodes, catch it here.
                error_msg = f"CRITICAL EXCEPTION in '{step_name}': {str(e)}"
                sys_logger.error(error_msg, exc_info=True)  # exc_info logs the full stacktrace to file

                # Return a managed failure that the Engine can display as ❌
                return Result(
                    host=task.host,
                    failed=True,
                    result=StandardResult(
                        status=TaskStatus.FAILED,
                        message=f"System Error: {str(e)}"
                    )
                )

        return wrapper

    return decorator


def automated_substep(step_name: str):
    """
    Decorator for internal sub-steps.
    In VERBOSE mode, uses a spinner that transforms into the final result.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(task: Task, *args, **kwargs) -> SubTaskResult:
            host_name = task.host.name

            # LOG SU FILE (Sempre)
            sys_logger.info(f"[{host_name}] [SUB-START] '{step_name}'")

            result = None
            error_to_raise = None

            # --- ESECUZIONE ---
            try:
                if global_config.VERBOSE:
                    # UI MODE: Mostra spinner temporaneo
                    # Quando questo blocco finisce, la riga sparisce
                    with console.status(f"    [dim]🔹 {step_name}...[/dim]", spinner="dots"):
                        result = func(task, *args, **kwargs)
                else:
                    # SILENT MODE: Esegue e basta
                    result = func(task, *args, **kwargs)

            except Exception as e:
                # Catturiamo l'eccezione per gestirla dopo
                error_to_raise = e

            # --- GESTIONE RISULTATO E UI FINALE ---

            # Caso 1: CRASH (Eccezione)
            if error_to_raise:
                error_msg = f"Exception in '{step_name}': {str(error_to_raise)}"
                sys_logger.error(f"[{host_name}] [SUB-CRASH] {error_msg}", exc_info=True)

                if global_config.VERBOSE:
                    # La riga dello spinner è sparita, stampiamo l'errore statico
                    console.print(f"    [bold red]💥 CRASH {step_name}[/bold red]: {str(error_to_raise)}")

                return SubTaskResult(success=False, message=error_msg)

            # Caso 2: ESECUZIONE COMPLETATA (Success o Fail logico)
            status_log = "OK" if result.success else "FAIL"
            log_msg = f"[{host_name}] [SUB-END] '{step_name}' -> {status_log} ({result.message})"

            if result.success:
                sys_logger.info(log_msg)
                if global_config.VERBOSE:
                    # Stampa la spunta verde al posto dello spinner
                    console.print(f"    [green]✔[/green] [dim]{step_name}[/dim]")
            else:
                sys_logger.warning(log_msg)
                if global_config.VERBOSE:
                    # Stampa la X rossa con il messaggio di errore
                    console.print(f"    [red]✖ {step_name}[/red]: [dim]{result.message}[/dim]")

            return result

        return wrapper

    return decorator
