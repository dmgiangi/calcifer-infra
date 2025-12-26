from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
# Assicurati di aver creato tasks/files.py come discusso nel passo precedente
from tasks.files import _write_file
from tasks.utils import run_cmd, fail


# --- SUB-STEPS ---

@automated_substep("Install Dependencies Prerequisites")
def _install_prerequisites(task: Task) -> SubTaskResult:
    """
    Installs system packages required for fetching repositories.
    """
    # -y for auto-yes, -qq for quiet to reduce log noise
    # We update first to ensure package lists are fresh
    pkgs = "ca-certificates curl apt-transport-https lsb-release gnupg"
    cmd = f"sudo apt-get update && sudo apt-get install -y {pkgs}"

    res = run_cmd(task, cmd)
    if res.failed:
        return SubTaskResult(success=False, message=f"Failed to install prerequisites: {res.result}")

    return SubTaskResult(success=True, message="Prerequisites installed")


@automated_substep("Setup Microsoft GPG Key")
def _setup_microsoft_gpg(task: Task) -> SubTaskResult:
    """
    Downloads and dearmors the Microsoft GPG key if not present.
    """
    keyring_path = "/etc/apt/keyrings/microsoft.gpg"

    # 1. Idempotency Check: Don't download if exists
    # We use 'test -f' via shell
    if not run_cmd(task, f"test -f {keyring_path}").failed:
        return SubTaskResult(success=True, message="GPG Key already present")

    # 2. Ensure directory exists
    run_cmd(task, "sudo mkdir -p /etc/apt/keyrings")

    # 3. Download & Dearmor
    # Pipeline: curl -> gpg -> tee
    url = "https://packages.microsoft.com/keys/microsoft.asc"
    cmd = f"curl -sLS {url} | gpg --dearmor | sudo tee {keyring_path} > /dev/null"

    res = run_cmd(task, cmd)
    if res.failed:
        return SubTaskResult(success=False, message="Failed to download/dearmor GPG key")

    # 4. Secure permissions (readable by apt)
    run_cmd(task, f"sudo chmod go+r {keyring_path}")

    return SubTaskResult(success=True, message="GPG Key setup complete")


@automated_substep("Configure Azure CLI Repo")
def _configure_azure_repo(task: Task) -> SubTaskResult:
    """
    Creates the apt sources list file using atomic write.
    """
    repo_path = "/etc/apt/sources.list.d/azure-cli.list"

    # Note: We are hardcoding 'jammy' here as per your original script.
    # To make it dynamic, we could use $(lsb_release -cs) but requires handling in Python.
    # Keeping it simple and robust for now.
    repo_content = (
        "deb [arch=amd64 signed-by=/etc/apt/keyrings/microsoft.gpg] "
        "https://packages.microsoft.com/repos/azure-cli/ jammy main\n"
    )

    # _write_file handles hashing (md5) and atomic write via base64
    res = _write_file(task, repo_path, repo_content)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to write repo list file")

    status_msg = "Repo list updated" if res.changed else "Repo list up-to-date"
    return SubTaskResult(success=True, message=status_msg)


@automated_substep("Install Azure CLI Package")
def _install_package(task: Task) -> SubTaskResult:
    """
    Updates apt cache and installs the actual azure-cli package.
    """
    # Check if installed first to save time? 
    # Apt is generally smart, but 'which az' is faster.
    if not run_cmd(task, "which az").failed:
        return SubTaskResult(success=True, message="Azure CLI already installed (binary found)")

    # Update is mandatory after adding a new repo
    cmd = "sudo apt-get update && sudo apt-get install -y azure-cli"

    res = run_cmd(task, cmd)
    if res.failed:
        return SubTaskResult(success=False, message="Apt install failed")

    return SubTaskResult(success=True, message="Package installed")


# --- MAIN TASK ---

@automated_step("Ensure Azure CLI Installation")
def ensure_azure_cli(task: Task) -> Result:
    """
    Orchestrates the installation of Azure CLI.
    """

    # 1. Prerequisites
    s1 = _install_prerequisites(task)
    if not s1.success: return fail(task, s1)

    # 2. GPG Key
    s2 = _setup_microsoft_gpg(task)
    if not s2.success: return fail(task, s2)

    # 3. Repository Config (Idempotent File Write)
    s3 = _configure_azure_repo(task)
    if not s3.success: return fail(task, s3)

    # 4. Install Package
    s4 = _install_package(task)
    if not s4.success: return fail(task, s4)

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.OK,  # Or CHANGED if we tracked deep changes
            message="Azure CLI installed & configured"
        )
    )
