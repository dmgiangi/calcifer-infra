import subprocess
import shlex
from nornir.core.task import Task, Result


def run_local(task: Task, command: str) -> Result:
    """Esegue comandi nativi OS senza passare per SSH/Scrapli"""
    # Esegue il comando
    proc = subprocess.run(
        shlex.split(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    # Prepara il risultato Nornir
    # Se returncode != 0, è fallito
    return Result(
        host=task.host,
        result=proc.stdout if proc.returncode == 0 else f"{proc.stdout}\nError: {proc.stderr}",
        failed=proc.returncode != 0
    )