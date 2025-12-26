import shlex
import subprocess

from nornir.core.task import Task, Result
from nornir_scrapli.tasks import send_command

from core.models import SubTaskResult, TaskStatus, StandardResult


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


def run_cmd(task: Task, cmd: str):
    """Executes shell command locally or via SSH based on platform."""
    if task.host.platform == "linux_local":
        return task.run(task=run_local, command=cmd)
    else:
        return task.run(task=send_command, command=cmd)


def fail(task: Task, sub_res: SubTaskResult) -> Result:
    return Result(
        host=task.host,
        failed=True,
        result=StandardResult(TaskStatus.FAILED, sub_res.message)
    )
