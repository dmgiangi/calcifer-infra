import hashlib
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
        multi_result = task.run(task=send_command, command=cmd)
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
    # Use base64 to avoid any bash escaping issues
    import base64
    b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')

    # Command: decode base64 and write to file via tee
    cmd = f"echo '{b64_content}' | base64 -d | sudo -n tee {path} > /dev/null"

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
