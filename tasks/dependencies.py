from nornir.core.task import Task, Result
from tasks.utils import run_local
from core.models import TaskStatus, StandardResult


def ensure_azure_cli(task: Task) -> Result:
    """
    Ensures Azure CLI is installed on the host.
    Idempotent: Checks existence before attempting installation.
    """

    # 1. Idempotency Check
    check_cmd = task.run(task=run_local, command="which az")

    if not check_cmd.failed:
        return Result(
            host=task.host,
            result=StandardResult(
                status=TaskStatus.OK,
                message="Azure CLI is already installed."
            )
        )

    # 2. Installation Logic (Debian/Ubuntu specific)
    # Note: In a production framework, commands might be fetched from a mapped dict based on task.host.platform
    install_cmds = [
        "apt-get update",
        "apt-get install -y ca-certificates curl apt-transport-https lsb-release gnupg",
        "mkdir -p /etc/apt/keyrings",
        "curl -sLS https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | sudo tee /etc/apt/keyrings/microsoft.gpg > /dev/null",
        "chmod go+r /etc/apt/keyrings/microsoft.gpg",
        "echo 'deb [arch=amd64 signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/azure-cli/ jammy main' | sudo tee /etc/apt/sources.list.d/azure-cli.list",
        "apt-get update && apt-get install -y azure-cli"
    ]

    for cmd in install_cmds:
        # Assuming passwordless sudo or privileged user
        res = task.run(task=run_local, command=f"sudo {cmd}")

        if res.failed:
            return Result(
                host=task.host,
                failed=True,
                result=StandardResult(
                    status=TaskStatus.FAILED,
                    message=f"Installation failed at step '{cmd}': {res.result}"
                )
            )

    return Result(
        host=task.host,
        changed=True,
        result=StandardResult(
            status=TaskStatus.CHANGED,
            message="Azure CLI successfully installed."
        )
    )