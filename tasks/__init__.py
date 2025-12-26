import hashlib
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


def read_file(task: Task, path: str) -> str:
    """Reads a remote or local file and returns the content."""
    res = run_command(task, f"cat {path}", True)

    if res.failed:
        # If the file doesn't exist, return an empty string (or handle differently)
        return ""
    return res.result


def write_file(task: Task, path: str, content: str) -> Result:
    """
    Writes content to a remote file (using tee for sudo permissions).
    Returns a Result indicating whether it was changed or not.
    """
    # 1. Calculate hash of the new content
    new_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

    # 2. Read current content (for idempotency)
    current_content = read_file(task, path)
    current_hash = hashlib.md5(current_content.encode('utf-8')).hexdigest()

    if new_hash == current_hash:
        return Result(host=task.host, changed=False, result="File is up to date")

    # 3. Write (using a secure technique with heredoc and quotes to avoid injection)
    # Example: cat << 'EOF' > file ...
    # Note: special characters in content must be handled.
    # A robust method for small/medium files is using printf or base64 to avoid escaping issues.

    # Use base64 to avoid any bash escaping issues
    import base64
    b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')

    # Command: decode base64 and write to file via tee
    cmd = f"echo '{b64_content}' | base64 -d | sudo tee {path} > /dev/null"

    res = run_command(task, cmd)

    return Result(host=task.host, changed=True, result="File updated", failed=res.failed)


def ensure_line_in_file(task: Task, path: str, line: str, match_regex: str = None) -> Result:
    """
    Ensures that a line is present.
    If match_regex is provided, replaces the matching line.
    Otherwise appends at the end.
    """
    import re

    content = read_file(task, path)
    lines = content.splitlines()
    new_lines = []
    found = False

    if match_regex:
        regex = re.compile(match_regex)
        for l in lines:
            if regex.search(l):
                new_lines.append(line)  # Replace
                found = True
            else:
                new_lines.append(l)  # Keep
        if not found:
            new_lines.append(line)  # Add if not found
    else:
        # Exact search
        if line in lines:
            return Result(host=task.host, changed=False, result="Line already exists")
        new_lines = lines + [line]

    final_content = "\n".join(new_lines) + "\n"  # Ensure trailing newline

    return write_file(task, path, final_content)
