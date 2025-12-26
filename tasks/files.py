import hashlib

from nornir.core.task import Task, Result
from nornir_scrapli.tasks import send_command

from tasks.utils import run_local


def _read_file(task: Task, path: str) -> str:
    """Reads a remote or local file and returns the content."""
    cmd = f"sudo cat {path}"

    if task.host.platform == "linux_local":
        res = task.run(task=run_local, command=cmd)
    else:
        res = task.run(task=send_command, command=cmd)

    if res.failed:
        # If the file doesn't exist, return an empty string (or handle differently)
        return ""
    return res.result


def _write_file(task: Task, path: str, content: str) -> Result:
    """
    Writes content to a remote file (using tee for sudo permissions).
    Returns a Result indicating whether it was changed or not.
    """
    # 1. Calculate hash of the new content
    new_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

    # 2. Read current content (for idempotency)
    current_content = _read_file(task, path)
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

    if task.host.platform == "linux_local":
        res = task.run(task=run_local, command=cmd)
    else:
        res = task.run(task=send_command, command=cmd)

    return Result(host=task.host, changed=True, result="File updated", failed=res.failed)


def ensure_line_in_file(task: Task, path: str, line: str, match_regex: str = None) -> Result:
    """
    Ensures that a line is present.
    If match_regex is provided, replaces the matching line.
    Otherwise appends at the end.
    """
    import re

    content = _read_file(task, path)
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

    return _write_file(task, path, final_content)
