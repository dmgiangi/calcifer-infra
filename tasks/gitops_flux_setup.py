from pyinfra import host
from pyinfra.operations import server, files

from utils.logger import log_operation


@log_operation
def setup_fluxcd():
    """
    Install & Bootstrap FluxCD.
    """
    config = host.data.app_config.k8s.flux
    if not config.enabled:
        return

    # 1. Install CLI
    server.shell(
        name="Install Flux CLI",
        commands=["curl -s https://fluxcd.io/install.sh | sudo bash"],
    )

    # 2. Upload SSH Key
    files.put(
        name="Upload Flux SSH Key",
        src=config.local_key_path,
        dest=config.remote_key_path,
        mode="600",
    )

    # 3. Bootstrap
    bootstrap_cmd = (
        f"flux bootstrap git "
        f"--url={config.github_url} "
        f"--branch={config.branch} "
        f"--path={config.cluster_path} "
        f"--private-key-file={config.remote_key_path} "
        f"--silent"
    )

    server.shell(
        name="Bootstrap Flux GitOps",
        commands=[f"export KUBECONFIG=/etc/kubernetes/admin.conf && {bootstrap_cmd}"],
    )

    # 4. Cleanup
    server.shell(
        name="Cleanup Flux SSH Key",
        commands=[f"rm -f {config.remote_key_path}"],
    )
