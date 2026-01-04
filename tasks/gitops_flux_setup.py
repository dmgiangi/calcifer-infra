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
    ssh_user = host.data.ssh_user
    remote_ssh_dir = f"/home/{ssh_user}/.ssh"
    remote_key_path = f"{remote_ssh_dir}/flux_identity"

    files.directory(
        name="Ensure .ssh directory exists",
        path=remote_ssh_dir,
        mode="700",
        user=ssh_user,
        group=ssh_user,
    )

    files.put(
        name="Upload Flux SSH Key",
        src=config.local_key_path,
        dest=remote_key_path,
        mode="600",
        user=ssh_user,
        group=ssh_user,
    )

    # 3. Bootstrap
    github_url = config.github_url
    if github_url.startswith("https://github.com/"):
        # Convert HTTPS to SSH for Flux
        # From: https://github.com/user/repo.git
        # To:   ssh://git@github.com/user/repo.git
        github_url = github_url.replace("https://github.com/", "ssh://git@github.com/")

    bootstrap_cmd = (
        f"flux bootstrap git "
        f"--url={github_url} "
        f"--branch={config.branch} "
        f"--path={config.cluster_path} "
        f"--private-key-file={remote_key_path} "
        f"--silent"
    )

    server.shell(
        name="Bootstrap Flux GitOps",
        commands=[f"export KUBECONFIG=/etc/kubernetes/admin.conf && {bootstrap_cmd}"],
    )

    # 4. Cleanup
    server.shell(
        name="Cleanup Flux SSH Key",
        commands=[f"rm -f {remote_key_path}"],
    )
