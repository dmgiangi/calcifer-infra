from nornir.core.task import Task, Result

from core.decorators import automated_step
from core.decorators import console
from core.models import TaskStatus, StandardResult
from utils.linux import check_connectivity


@automated_step("Check Internet Connectivity")
def check_internet_access(task: Task) -> Result:
    """
    Verifies if the host can reach the internet (Ping 1.1.1.1).
    Uses the unified run_command dispatcher.
    """
    target = "1.1.1.1"

    # run_command automatically handles local vs remote (SSH)
    cmd_result = check_connectivity(task, target, count=2)

    # --- RESULT ANALYSIS ---
    if cmd_result.failed:
        return Result(
            host=task.host,
            failed=True,
            result=StandardResult(
                status=TaskStatus.FAILED,
                message=f"Unreachable: {target}. Check network/DNS."
            )
        )

    output = cmd_result.result
    msg = f"Connectivity to {target} verified."

    if "avg" in output:
        try:
            # Rough parsing of Linux latency
            avg_latency = output.split("avg")[1].split("/")[1]
            msg += f" (Latency: {avg_latency}ms)"
        except Exception as e:
            console.print(f"[Warning] Failed to parse ping output: {output} with error: {e}.")

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.OK,
            message=msg
        )
    )