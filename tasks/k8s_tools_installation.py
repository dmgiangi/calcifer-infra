from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import fail, run_command, add_apt_repository, apt_install


def _get_k8s_version(task: Task) -> str:
    """Helper to retrieve and format K8s version (e.g., 'v1.29')."""
    config = task.host.get("app_config")
    version = config["k8s"]["version"]  # e.g. "1.29" or "v1.29"

    # Ensure it starts with 'v' for the URL construction
    if not version.startswith("v"):
        return f"v{version}"
    return version


# --- SUB-STEPS ---

@automated_substep("Add Kubernetes APT Repository")
def _add_kubernetes_repo(task: Task, k8s_version: str) -> SubTaskResult:
    """
    Adds the Kubernetes repository using the centralized apt utility.
    """
    facts = task.host.get("os_facts")
    if not facts:
        return SubTaskResult(success=False, message="Missing OS Facts")

    arch = facts["arch"]

    key_path = "/etc/apt/keyrings/kubernetes-apt-keyring.gpg"

    repo_string = (
        f"deb [arch={arch} signed-by={key_path}] "
        f"https://pkgs.k8s.io/core:/stable:/{k8s_version}/deb/ /\n"
    )

    return add_apt_repository(
        task,
        repo_name="kubernetes",
        repo_string=repo_string,
        gpg_key_url=f"https://pkgs.k8s.io/core:/stable:/{k8s_version}/deb/Release.key",
        gpg_key_path=key_path,
    )


@automated_substep("Install Kube Tools")
def _install_packages(task: Task) -> SubTaskResult:
    """
    Installs kubelet, kubeadm, and kubectl.
    """
    res = apt_install(task, "kubelet kubeadm kubectl")

    if res.failed:
        return SubTaskResult(success=False, message=f"Apt install failed: {res.result}")

    return SubTaskResult(success=True, message="Packages installed")


@automated_substep("Hold Package Versions")
def _hold_packages(task: Task) -> SubTaskResult:
    """
    Prevents automatic upgrades using apt-mark hold.
    """
    cmd = "apt-mark hold kubelet kubeadm kubectl"
    res = run_command(task, cmd, sudo=True)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to hold packages")

    return SubTaskResult(success=True, message="Version lock enabled (held)")


@automated_substep("Enable Kubelet Service")
def _enable_service(task: Task) -> SubTaskResult:
    """
    Enables kubelet so it starts on boot, but doesn't start it immediately 
    (it crashes until configured by kubeadm).
    """
    cmd = "systemctl enable kubelet"
    res = run_command(task, cmd, sudo=True)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to enable service")

    return SubTaskResult(success=True, message="Kubelet enabled")


# --- MAIN TASK ---

@automated_step("Install Kubernetes Tools")
def install_kubernetes_tools(task: Task) -> Result:
    """
    Installs kubeadm, kubelet, and kubectl for the configured version.
    """
    # 0. Get Version from Settings
    k8s_ver = _get_k8s_version(task)

    # 1. Add Repo and GPG Key
    s1 = _add_kubernetes_repo(task, k8s_ver)
    if not s1.success: return fail(task, s1)

    # 2. Install Packages
    s2 = _install_packages(task)
    if not s2.success: return fail(task, s2)

    # 3. Hold Versions
    s3 = _hold_packages(task)
    if not s3.success: return fail(task, s3)

    # 4. Enable Service
    s4 = _enable_service(task)
    if not s4.success: return fail(task, s4)

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.CHANGED,
            message=f"Kubernetes tools ({k8s_ver}) installed & held."
        )
    )
