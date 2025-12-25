from nornir_scrapli.tasks import send_command
from nornir.core.task import Task, Result


def check_ssh_connection(task: Task) -> Result:
    """
    Lightweight task that runs 'uptime' to verify
    SSH connectivity and authentication.
    """
    # Run a trivial command
    try:
        cmd = task.run(task=send_command, command="uptime")
    except Exception as e:
        return Result(host=task.host, result=f"❌ CRITICAL SSH ERROR: {e}", failed=True)

    if cmd.failed:
        return Result(host=task.host, result="❌ Connection Failed", failed=True)

    uptime_str = cmd.result.strip()
    return Result(host=task.host, result=f"✅ Connected! ({uptime_str})")