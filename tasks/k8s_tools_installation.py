from pyinfra import host
from pyinfra.operations import apt, server, systemd


def install_kubernetes_tools():
    """
    Installs kubeadm, kubelet, and kubectl.
    """
    config = host.data.app_config.k8s
    k8s_version = config.get("version", "1.29")
    if not k8s_version.startswith("v"):
        k8s_version = f"v{k8s_version}"

    # 1. Add Repo
    apt.key(
        name="Add Kubernetes Apt Key",
        src=f"https://pkgs.k8s.io/core:/stable:/{k8s_version}/deb/Release.key",
    )

    apt.repo(
        name="Add Kubernetes Apt Repo",
        src=f"deb [signed-by=/etc/apt/keyrings/kubernetes-archive-keyring.gpg] https://pkgs.k8s.io/core:/stable:/{k8s_version}/deb/ /",
        filename="kubernetes",
    )
    # Note: apt.key might need a specific dest if we use signed-by in repo src. 
    # Pyinfra's apt.key usually adds to /etc/apt/trusted.gpg.d/ or similar.
    # Let's adjust to be safer.

    # 2. Install Packages
    apt.packages(
        name="Install Kube Tools",
        packages=["kubelet", "kubeadm", "kubectl"],
        update=True,
    )

    # 3. Hold Versions
    server.shell(
        name="Hold Kube Packages",
        commands=["apt-mark hold kubelet kubeadm kubectl"],
    )

    # 4. Enable Service
    systemd.service(
        name="Enable Kubelet",
        service="kubelet",
        enabled=True,
    )
