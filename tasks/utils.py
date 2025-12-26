import shlex
import subprocess

from nornir.core.task import Task, Result
from nornir_scrapli.tasks import send_command

from core.models import SubTaskResult, StandardResult, TaskStatus
from core.state import config as global_config


def run_command(task: Task, cmd: str, sudo: bool = False) -> Result:
    """
    Unified command dispatcher.
    Handles:
    1. Platform dispatch (Local vs Remote SSH)
    2. Sudo privilege escalation (Passwordless vs Password)

    Returns:
        Result: A single Nornir Result object (not MultiResult).
    """

    # --- SUDO WRAPPING LOGIC ---
    if sudo:
        if global_config.SUDO_PASSWORD:
            # Escaping basico per la password (single quotes)
            pw = global_config.SUDO_PASSWORD.replace("'", "'\\''")

            # echo 'PASS' | sudo -S -p '' cmd
            # -S legge da stdin, -p '' nasconde il prompt
            cmd = f"echo '{pw}' | sudo -S -p '' {cmd}"
        else:
            # Passwordless sudo
            cmd = f"sudo {cmd}"

    # --- EXECUTION ---
    if task.host.platform == "linux_local":
        return _run_local_subprocess(task, cmd)
    else:
        # CORREZIONE: task.run ritorna un MultiResult (lista).
        # Dobbiamo estrarre il singolo Result (indice 0).
        multi_result = task.run(task=send_command, command=cmd)
        return multi_result[0]


def _run_local_subprocess(task: Task, command: str) -> Result:
    """Internal helper for local execution."""

    # Se il comando contiene pipe, è più sicuro usare shell=True
    # (ma attenzione all'escaping se l'input fosse non fidato).
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
            # Senza pipe, usiamo shlex.split per sicurezza
            proc = subprocess.run(
                shlex.split(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

        return Result(
            host=task.host,
            result=proc.stdout if proc.returncode == 0 else f"{proc.stdout}\nError: {proc.stderr}",
            failed=proc.returncode != 0
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
