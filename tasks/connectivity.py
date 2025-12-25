from nornir.core.task import Task, Result
from nornir_scrapli.tasks import send_command

from tasks.utils import run_local
from core.models import TaskStatus, StandardResult
from core.decorators import automated_step


@automated_step("Check Internet Connectivity")
def check_internet_access(task: Task) -> Result:
    """
    Verifies if the host can reach the internet (Ping 1.1.1.1).
    Adapts execution based on host platform (local vs remote).
    """
    target = "1.1.1.1"
    # Universal Linux command
    cmd_string = f"ping -c 2 {target}"

    # --- DISPATCHER LOGIC ---
    # Decide which "driver" to use based on the platform defined in inventory
    if task.host.platform == "linux_local":
        # Local Execution (subprocess)
        # run_local is defined in tasks/utils.py
        cmd_result = task.run(task=run_local, command=cmd_string)
    else:
        # Remote Execution (SSH via Scrapli)
        # send_command handles the SSH session
        cmd_result = task.run(task=send_command, command=cmd_string)

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

    # Extract average latency (optional, for better UI)
    # Typical output: "rtt min/avg/max/mdev = 12.3/14.5/..."
    output = cmd_result.result
    msg = f"Connectivity to {target} verified."

    if "avg" in output:
        try:
            # Rough parsing to extract latency
            avg_latency = output.split("avg")[1].split("/")[1]
            msg += f" (Latency: {avg_latency}ms)"
        except:
            pass

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.OK,
            message=msg
        )
    )