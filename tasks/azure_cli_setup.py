from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import fail
from utils.linux import add_apt_repository, apt_install, command_exists


# --- SUB-STEPS ---

@automated_substep("Add Azure CLI APT Repository")
def _add_azure_cli_repo(task: Task) -> SubTaskResult:
    """
    Adds the Azure CLI repository using the centralized apt utility.
    """
    facts = task.host.get("os_facts")
    if not facts:
        return SubTaskResult(success=False, message="OS Facts not found. Run 'gather_system_facts' first.")

    arch = facts["arch"]
    codename = facts["codename"]

    key_path = "/etc/apt/keyrings/microsoft.gpg"

    repo_string = (
        f"deb [arch={arch} signed-by={key_path}] "
        f"https://packages.microsoft.com/repos/azure-cli/ {codename} main\n"
    )

    return add_apt_repository(
        task,
        repo_name="azure-cli",
        repo_string=repo_string,
        gpg_key_url="https://packages.microsoft.com/keys/microsoft.asc",
        gpg_key_path=key_path,
    )


@automated_substep("Install Azure CLI Package")
def _install_package(task: Task) -> SubTaskResult:
    """
    Updates apt cache and installs the actual azure-cli package.
    """
    res = apt_install(task, "azure-cli")
    if res.failed:
        return SubTaskResult(success=False, message=f"Apt install failed: {res.result}")

    return SubTaskResult(success=True, message="Package installed")


# --- MAIN TASK ---

@automated_step("Ensure Azure CLI Installation")
def ensure_azure_cli(task: Task) -> Result:
    """
    Orchestrates the installation of Azure CLI.
    """
    # 0. Check if Azure CLI is already installed
    if command_exists(task, "az"):
        return Result(
            host=task.host,
            result=StandardResult(
                status=TaskStatus.OK,
                message="Azure CLI already installed (binary found), skipping installation steps."
            )
        )

    # 1. Add Repo and GPG Key
    s1 = _add_azure_cli_repo(task)
    if not s1.success: return fail(task, s1)

    # 2. Install Package
    s2 = _install_package(task)
    if not s2.success: return fail(task, s2)

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.CHANGED,
            message="Azure CLI installed & configured"
        )
    )