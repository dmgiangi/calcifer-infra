import datetime
import hashlib
import os
import re
import shlex
import subprocess
import tempfile
import uuid
from typing import List, Union

from nornir.core.task import Task, Result
from nornir_scrapli.tasks import send_command

from core.models import SubTaskResult


# --- CORE EXECUTION ---

def run_command(task: Task, cmd: str, sudo: bool = False) -> Result:
    """
    Unified command dispatcher.
    Handles:
    1. Platform dispatch (Local vs Remote SSH)
    2. Sudo privilege escalation (Passwordless)

    Returns:
        Result: A single Nornir Result object.
    """
    if sudo:
        cmd = f"sudo -n {cmd}"

    if task.host.platform == "linux_local":
        return _run_local_subprocess(task, cmd)
    else:
        # task.run returns a MultiResult (list-like)
        multi_result = task.run(task=send_command, command=cmd)
        result = multi_result[0]

        # Handle sudo password requirement failure
        if result.failed and "sudo: a password is required" in result.result:
            user = task.host.username
            host = task.host.hostname
            return Result(
                host=task.host,
                failed=True,
                result=f"Sudo privileges missing for user '{user}' on '{host}' (NOPASSWD required)."
            )
        return result


def _run_local_subprocess(task: Task, command: str) -> Result:
    """Internal helper for local execution."""
    # Use shell=True if pipes are involved
    use_shell = "|" in command or "&&" in command or "||" in command or ">" in command

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
            proc = subprocess.run(
                shlex.split(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

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


# --- FILE OPERATIONS ---

def remote_file_exists(task: Task, path: str) -> bool:
    """Checks if a remote file exists safely."""
    cmd = f"test -f {path} && echo '__EXISTS__' || echo '__MISSING__'"
    res = run_command(task, cmd)
    return "__EXISTS__" in res.result


def read_file(task: Task, path: str) -> str:
    """Reads a remote or local file and returns the content."""
    if not remote_file_exists(task, path):
        return ""

    res = run_command(task, f"cat {path}", sudo=True)  # sudo to be safe reading root files
    if res.failed:
        return ""
    return res.result


def write_file(
        task: Task,
        path: str,
        content: str,
        owner: str = "root:root",
        permissions: str = "644",
        sudo: bool = True
) -> Result:
    """
    Writes content to a remote file using SCP and Sudo Move.
    Includes automatic versioned backup.
    """
    # 1. Idempotency Check
    new_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
    current_content = read_file(task, path)
    current_hash = hashlib.md5(current_content.encode('utf-8')).hexdigest()

    if new_hash == current_hash:
        # Check permissions/owner even if content is same?
        # For simplicity, we assume if content is same, we are good or logic is elsewhere.
        # Ideally we should check/fix permissions here too.
        return Result(host=task.host, changed=False, result="File is up to date")

    # 2. Local Temp File
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f_local:
        f_local.write(content)
        local_temp_path = f_local.name

    remote_temp_path = f"/tmp/calcifer_{uuid.uuid4().hex}"

    try:
        # 3. Transfer (SCP)
        host = task.host.hostname
        user = task.host.username
        port = str(task.host.port or 22)

        # If local execution, just cp
        if task.host.platform == "linux_local":
            subprocess.run(f"cp {local_temp_path} {remote_temp_path}", shell=True, check=True)
        else:
            scp_cmd = [
                "scp", "-P", port,
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                local_temp_path,
                f"{user}@{host}:{remote_temp_path}"
            ]
            proc = subprocess.run(
                scp_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            if proc.returncode != 0:
                return Result(host=task.host, failed=True, result=f"SCP Failed: {proc.stderr}")

        # 4. Backup
        if remote_file_exists(task, path):
            backup_dir = "$HOME/.calcifer_backups"
            safe_filename = path.replace("/", "_")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{backup_dir}/{safe_filename}.{timestamp}.bak"

            cmd_bkp = f"mkdir -p {backup_dir} && cp {path} {backup_path}"
            res_bkp = run_command(task, cmd_bkp, sudo=sudo)
            if res_bkp.failed:
                run_command(task, f"rm {remote_temp_path}")
                return Result(host=task.host, failed=True, result=f"Backup failed: {res_bkp.result}")

        # 5. Move to Destination
        res_mv = run_command(task, f"mv {remote_temp_path} {path}", sudo=sudo)
        if res_mv.failed:
            run_command(task, f"rm {remote_temp_path}")
            return Result(host=task.host, failed=True, result=f"Move failed: {res_mv.result}")

        # 6. Permissions
        run_command(task, f"chown {owner} {path}", sudo=sudo)
        run_command(task, f"chmod {permissions} {path}", sudo=sudo)

        return Result(host=task.host, changed=True, result="File updated (Backup saved)")

    except Exception as e:
        return Result(host=task.host, failed=True, result=f"Unexpected error: {str(e)}")
    finally:
        if os.path.exists(local_temp_path):
            os.remove(local_temp_path)


def ensure_line_in_file(task: Task, path: str, line: str, match_regex: str = None, sudo: bool = True) -> Result:
    """Ensures a line exists in a file, optionally replacing via regex."""
    content = read_file(task, path)
    lines = content.splitlines()
    new_lines = []
    found = False

    if match_regex:
        regex = re.compile(match_regex)
        for l in lines:
            if regex.search(l):
                new_lines.append(line)
                found = True
            else:
                new_lines.append(l)
        if not found:
            new_lines.append(line)
    else:
        if line in lines:
            return Result(host=task.host, changed=False, result="Line already exists")
        new_lines = lines + [line]

    final_content = "\n".join(new_lines) + "\n"
    return write_file(task, path, final_content, sudo=sudo)


def make_directory(task: Task, path: str, sudo: bool = False) -> Result:
    """Creates a directory (mkdir -p)."""
    return run_command(task, f"mkdir -p {path}", sudo=sudo)


def remove_file(task: Task, path: str, sudo: bool = False, recursive: bool = False) -> Result:
    """Removes a file or directory."""
    flags = "-rf" if recursive else "-f"
    return run_command(task, f"rm {flags} {path}", sudo=sudo)


def copy_file(task: Task, src: str, dest: str, sudo: bool = False) -> Result:
    """Copies a file on the remote host."""
    return run_command(task, f"cp -r {src} {dest}", sudo=sudo)


def change_owner(task: Task, path: str, owner: str, sudo: bool = True, recursive: bool = False) -> Result:
    """Changes file ownership."""
    flags = "-R" if recursive else ""
    return run_command(task, f"chown {flags} {owner} {path}", sudo=sudo)


def change_mode(task: Task, path: str, mode: str, sudo: bool = True, recursive: bool = False) -> Result:
    """Changes file permissions."""
    flags = "-R" if recursive else ""
    return run_command(task, f"chmod {flags} {mode} {path}", sudo=sudo)


# --- PACKAGE MANAGEMENT (APT) ---

def apt_install(task: Task, packages: Union[str, List[str]], update: bool = True) -> Result:
    """Installs packages via apt-get."""
    if isinstance(packages, list):
        pkg_str = " ".join(packages)
    else:
        pkg_str = packages

    if update:
        res_up = run_command(task, "apt-get update", sudo=True)
        if res_up.failed:
            return Result(host=task.host, failed=True, result=f"Apt update failed: {res_up.result}")

    cmd = f"DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg_str}"
    return run_command(task, cmd, sudo=True)


def add_apt_repository(
        task: Task,
        repo_name: str,
        repo_string: str,
        gpg_key_url: str,
        gpg_key_path: str,
) -> SubTaskResult:
    """Adds an APT repository and GPG key."""
    # 1. Prepare Keyring Dir
    keyring_dir = os.path.dirname(gpg_key_path)
    run_command(task, f"mkdir -p {keyring_dir}", sudo=True)

    # 2. Download & Dearmor Key
    if not remote_file_exists(task, gpg_key_path):
        temp_key_path = f"/tmp/{repo_name}.gpg.asc"

        res_dl = run_command(task, f"curl -fsSL {gpg_key_url} -o {temp_key_path}")
        if res_dl.failed:
            return SubTaskResult(success=False, message=f"Failed to download GPG key from {gpg_key_url}")

        res_dearmor = run_command(task, f"gpg --dearmor -o {gpg_key_path} {temp_key_path}", sudo=True)
        run_command(task, f"rm {temp_key_path}")  # Cleanup

        if res_dearmor.failed:
            return SubTaskResult(success=False, message="Failed to dearmor GPG key")

        run_command(task, f"chmod a+r {gpg_key_path}", sudo=True)

    # 3. Write Repo File
    repo_path = f"/etc/apt/sources.list.d/{repo_name}.list"
    res_write = write_file(task, repo_path, repo_string)
    if res_write.failed:
        return SubTaskResult(success=False, message=f"Failed to write repo file: {res_write.result}")

    return SubTaskResult(success=True, message=f"APT repository '{repo_name}' configured.")


# --- SYSTEM SERVICES ---

def systemctl(task: Task, service: str, action: str, enable: bool = False, sudo: bool = True) -> Result:
    """
    Manages systemd services.
    Actions: start, stop, restart, reload, status
    """
    cmd = f"systemctl {action} {service}"
    if enable:
        cmd += f" && systemctl enable {service}"

    return run_command(task, cmd, sudo=sudo)


# --- TOOLS / COMMANDS ---

def command_exists(task: Task, command: str) -> bool:
    """Checks if a command exists in PATH (using 'which')."""
    return not run_command(task, f"which {command}").failed


def curl_download(task: Task, url: str, dest: str, sudo: bool = False) -> Result:
    """Downloads a file using curl."""
    return run_command(task, f"curl -fsSL {url} -o {dest}", sudo=sudo)
