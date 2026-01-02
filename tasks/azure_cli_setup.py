from pyinfra.operations import apt

from utils.logger import log_operation


@log_operation
def ensure_azure_cli():
    """
    Ensures Azure CLI is installed.
    """
    # 1. Add Microsoft Key
    apt.key(
        name="Add Microsoft Apt Key",
        src="https://packages.microsoft.com/keys/microsoft.asc",
    )

    # 2. Add Repo
    apt.repo(
        name="Add Azure CLI Repo",
        src="deb [arch=amd64] https://packages.microsoft.com/repos/azure-cli/ jammy main",
        filename="azure-cli",
    )

    # 3. Install
    apt.packages(
        name="Install Azure CLI",
        packages=["azure-cli"],
        update=True,
    )
