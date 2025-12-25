from functools import wraps
from nornir.core.task import Task, Result
from core.models import TaskStatus, StandardResult
from utils.logger import sys_logger


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