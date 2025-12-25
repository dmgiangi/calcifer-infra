import subprocess
import shlex
from nornir.core.task import Task, Result


def run_local(task: Task, command: str) -> Result:
    """Executes native OS commands without using SSH/Scrapli"""
    # Execute the command
    proc = subprocess.run(
        shlex.split(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    # Prepare Nornir result
    # If returncode != 0, it failed
    return Result(
        host=task.host,
        result=proc.stdout if proc.returncode == 0 else f"{proc.stdout}\nError: {proc.stderr}",
        failed=proc.returncode != 0
    )