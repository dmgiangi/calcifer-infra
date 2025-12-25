from nornir.core.task import Task, Result

from tasks.utils import run_local


def install_dependencies(task: Task) -> Result:
    """
    Ensures that the necessary system dependencies are installed on the host.

    Current scope:
    - Azure CLI (az)
    - Excluded: Helm (to test if Arc agent handles it automatically)
    """

    # --- Pre-flight Check ---
    # We check if 'az' is already in the system path.
    # If the command returns exit code 0, it means it's installed.
    check_cmd = task.run(task=run_local, command="which az")

    if not check_cmd.failed:
        return Result(
            host=task.host,
            result="Skipped (Azure CLI already installed)"
        )

    # --- Installation Logic ---
    # If we are here, 'az' is missing. We proceed with the installation steps
    # strictly following Microsoft's official guide for Debian/Ubuntu.

    # We use a list of commands to keep the execution clean and sequential.
    install_cmds = [
        # 1. Update apt cache and install transport/ca-certificates
        "apt-get update",
        "apt-get install -y ca-certificates curl apt-transport-https lsb-release gnupg",

        # 2. Create the directory for keyrings if it doesn't exist
        "mkdir -p /etc/apt/keyrings",

        # 3. Download and store the Microsoft signing key
        "curl -sLS https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | sudo tee /etc/apt/keyrings/microsoft.gpg > /dev/null",
        "chmod go+r /etc/apt/keyrings/microsoft.gpg",

        # 4. Add the Azure CLI software repository
        "echo 'deb [arch=amd64 signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/azure-cli/ jammy main' | sudo tee /etc/apt/sources.list.d/azure-cli.list",

        # 5. Update cache again and install the specific package
        "apt-get update && apt-get install -y azure-cli"
    ]

    # Iterate through the commands. We assume the user has sudo privileges
    # without a password or the session is already privileged.
    for cmd in install_cmds:
        # We prepend 'sudo' to ensure we have root permissions for package management.
        res = task.run(task=run_local, command=f"sudo {cmd}")

        # Fail-fast: if any command in the chain fails, we abort immediately.
        if res.failed:
            return Result(
                host=task.host,
                result=f"Dependency Installation Failed at step: '{cmd}'. Error: {res.result}",
                failed=True
            )

    return Result(
        host=task.host,
        result="Success: Azure CLI installed",
        changed=True
    )