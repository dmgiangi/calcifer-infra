import shlex
import subprocess

from nornir.core.task import Task, Result
from nornir_scrapli.tasks import send_command

from core.models import SubTaskResult, StandardResult, TaskStatus


def run_command(task: Task, cmd: str, sudo: bool = False) -> Result:
    """
    Unified command dispatcher.
    Handles:
    1. Platform dispatch (Local vs Remote SSH)
    2. Sudo privilege escalation (Passwordless)

    Returns:
        Result: A single Nornir Result object (not MultiResult).
    """

    # --- SUDO WRAPPING LOGIC ---
    if sudo:
        cmd = f"sudo -n {cmd}"

    # --- EXECUTION ---
    if task.host.platform == "linux_local":
        result = run_local_subprocess(task, cmd)
    else:
        # CORRECTION: task.run returns a MultiResult (list).
        # We need to extract the single Result (index 0).
        multi_result = task.run(task=send_command, command=cmd, )
        result = multi_result[0]

    # --- Advanced Error Handling ---
    if result.failed and "sudo: a password is required" in result.result:
        user = task.host.username
        host = task.host.hostname
        error_msg = f"Sudo privileges missing. Please configure 'NOPASSWD' for user '{user}' in /etc/sudoers on host '{host}'."
        return Result(
            host=task.host,
            failed=True,
            result=error_msg
        )

    return result


def run_local_subprocess(task: Task, command: str) -> Result:
    """Internal helper for local execution."""

    # If the command contains pipes, it is safer to use shell=True
    # (but be careful with escaping if the input is untrusted).
    use_shell = "|" in command

    try:
        if use_shell:
            proc = subprocess.run(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
        else:
            # Without pipes, we use shlex.split for safety
            proc = subprocess.run(
                shlex.split(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

        # Combine stdout and stderr for a complete picture on failure
        output = proc.stdout
        if proc.returncode != 0:
            output += f"\nError: {proc.stderr}"

        return Result(
            host=task.host,
            result=output,
            failed=proc.returncode != 0,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except Exception as e:
        return Result(
            host=task.host,
            failed=True,
            result=f"Local execution exception: {str(e)}"
        )


def fail(task: Task, sub_res: SubTaskResult) -> Result:
    return Result(
        host=task.host,
        failed=True,
        result=StandardResult(TaskStatus.FAILED, sub_res.message)
    )
