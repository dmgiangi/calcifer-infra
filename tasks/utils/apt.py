import os

from nornir.core.task import Task

from core.models import SubTaskResult
from .command import run_command
from .files import write_file, remote_file_exists


def add_apt_repository(
        task: Task,
        repo_name: str,
        repo_string: str,
        gpg_key_url: str,
        gpg_key_path: str,
) -> SubTaskResult:
    """
    Adds an APT repository and its GPG key idempotently.

    Args:
        task: The Nornir task.
        repo_name: A short name for the repository (e.g., 'docker').
        repo_string: The full line for the sources.list file.
        gpg_key_url: The URL to download the GPG key from.
        gpg_key_path: The path to save the dearmored GPG key.

    Returns:
        A SubTaskResult indicating success or failure.
    """
    # 1. Manage GPG Key
    keyring_dir = os.path.dirname(gpg_key_path)
    run_command(task, f"mkdir -p {keyring_dir}", sudo=True)

    # Check if key exists
    if not remote_file_exists(task, gpg_key_path):
        temp_key_path = f"/tmp/{repo_name}.gpg.asc"

        # Download the key
        download_cmd = f"curl -fsSL {gpg_key_url} -o {temp_key_path}"
        res_download = run_command(task, download_cmd)
        if res_download.failed:
            return SubTaskResult(success=False, message=f"Failed to download GPG key from {gpg_key_url}")

        # Dearmor the key
        dearmor_cmd = f"gpg --dearmor -o {gpg_key_path} {temp_key_path}"
        res_dearmor = run_command(task, dearmor_cmd, sudo=True)

        # Cleanup
        run_command(task, f"rm {temp_key_path}")

        if res_dearmor.failed:
            return SubTaskResult(success=False, message="Failed to dearmor GPG key")

        # Set permissions
        run_command(task, f"chmod a+r {gpg_key_path}", sudo=True)

    # 2. Add APT Repository
    repo_path = f"/etc/apt/sources.list.d/{repo_name}.list"
    res_write = write_file(task, repo_path, repo_string)
    if res_write.failed:
        return SubTaskResult(success=False, message=f"Failed to write repository file: {res_write.result}")

    return SubTaskResult(success=True, message=f"APT repository '{repo_name}' configured.")
