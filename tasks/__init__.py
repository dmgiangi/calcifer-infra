import datetime
import os
import shlex
import subprocess
import tempfile

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


import uuid
import hashlib
from nornir.core.task import Task, Result


# Assicurati di importare run_command e read_file correttamente dal tuo progetto


def write_file(task: Task, path: str, content: str, owner: str = "root:root", permissions: str = "644") -> Result:
    """
    Writes content to a remote file using SCP (Stage 1) and Sudo Move (Stage 2).
    Includes automatic VERSIONED BACKUP of the existing file before overwriting.
    Accepts optional owner and permissions.
    """
    # 1. Calcolo Hash (Idempotenza)
    new_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

    # Leggiamo il file remoto attuale (se esiste)
    current_content = read_file(task, path)
    current_hash = hashlib.md5(current_content.encode('utf-8')).hexdigest()

    if new_hash == current_hash:
        return Result(host=task.host, changed=False, result="File is up to date")

    # 2. Preparazione File Temporanei
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f_local:
        f_local.write(content)
        local_temp_path = f_local.name

    remote_temp_path = f"/tmp/calcifer_{uuid.uuid4().hex}"

    try:
        # 3. Trasferimento SCP (Esecuzione Locale)
        host = task.host.hostname
        user = task.host.username
        port = str(task.host.port or 22)

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

        # --- FASE DI BACKUP ---
        # Verifichiamo se il file di destinazione esiste già
        check_exists = run_command(task, f"test -f {path}")

        if not check_exists.failed:
            # a. Creiamo la directory di backup nella home dell'utente (o root se sudo cambia HOME)
            backup_dir = "$HOME/.calcifer_backups"

            # b. Generiamo il nome file versionato
            # /etc/hosts -> _etc_hosts
            safe_filename = path.replace("/", "_")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{backup_dir}/{safe_filename}.{timestamp}.bak"

            # c. Eseguiamo il backup (mkdir + cp)
            # Usiamo sudo=True perché il file originale potrebbe essere di root
            backup_cmd = f"mkdir -p {backup_dir} && cp {path} {backup_path}"

            res_bkp = run_command(task, backup_cmd, sudo=True)

            if res_bkp.failed:
                # Se il backup fallisce, INTERROMPIAMO per sicurezza
                run_command(task, f"rm {remote_temp_path}")  # Pulizia tmp
                return Result(host=task.host, failed=True, result=f"Backup failed: {res_bkp.result}")

        # 4. Finalizzazione (SUDO MV)
        mv_cmd = f"mv {remote_temp_path} {path}"
        res_move = run_command(task, mv_cmd, sudo=True)

        if res_move.failed:
            run_command(task, f"rm {remote_temp_path}")
            return Result(host=task.host, failed=True, result=f"Move failed: {res_move.result}")

        # 5. Fix Owner and Permissions
        chown_cmd = f"chown {owner} {path}"
        run_command(task, chown_cmd, sudo=True)

        chmod_cmd = f"chmod {permissions} {path}"
        run_command(task, chmod_cmd, sudo=True)

        return Result(host=task.host, changed=True, result=f"File updated (Backup saved)")
    except Exception as e:
        return Result(host=task.host, failed=True, result=f"Unexpected error: {str(e)}")
    finally:
        if os.path.exists(local_temp_path):
            os.remove(local_temp_path)


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
