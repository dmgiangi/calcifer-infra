from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import fail, run_command
from tasks.files import _write_file


def _get_k8s_version(task: Task) -> str:
    """Helper to retrieve and format K8s version (e.g., 'v1.29')."""
    config = task.host.get("app_config")
    version = config["k8s"]["version"]  # e.g. "1.29" or "v1.29"

    # Ensure it starts with 'v' for the URL construction
    if not version.startswith("v"):
        return f"v{version}"
    return version


# --- SUB-STEPS ---

@automated_substep("Install Apt Dependencies")
def _install_deps(task: Task) -> SubTaskResult:
    """
    Installs transport and curl dependencies.
    """
    pkgs = "apt-transport-https ca-certificates curl gnupg"
    cmd = f"sudo apt-get update && sudo apt-get install -y {pkgs}"

    res = run_command(task, cmd)
    if res.failed:
        return SubTaskResult(success=False, message="Failed to install dependencies")
    return SubTaskResult(success=True, message="Dependencies installed")


@automated_substep("Setup Kubernetes Repo Key")
def _setup_k8s_key(task: Task, k8s_version: str) -> SubTaskResult:
    """
    Downloads and dearmors the Kubernetes GPG key.
    URL format depends on major.minor version.
    """
    keyring_path = "/etc/apt/keyrings/kubernetes-apt-keyring.gpg"

    # Idempotency: check if key exists
    if not run_command(task, f"test -f {keyring_path}").failed:
        return SubTaskResult(success=True, message="K8s Keyring already present")

    # Ensure dir exists
    run_command(task, "mkdir -p /etc/apt/keyrings", True)

    # Download URL
    # Format: https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key
    url = f"https://pkgs.k8s.io/core:/stable:/{k8s_version}/deb/Release.key"

    # Pipeline: curl -> gpg dearmor -> tee
    cmd = f"curl -fsSL {url} | sudo gpg --dearmor -o {keyring_path}"

    res = run_command(task, cmd)
    if res.failed:
        return SubTaskResult(success=False, message=f"Failed to download key for {k8s_version}")

    return SubTaskResult(success=True, message=f"Key setup for {k8s_version}")


@automated_substep("Add Kubernetes Repository")
def _add_k8s_repo(task: Task, k8s_version: str) -> SubTaskResult:
    """
    Adds the signed repository dynamically via OS Facts.
    """
    facts = task.host.get("os_facts")
    if not facts:
        return SubTaskResult(success=False, message="Missing OS Facts")

    # Kubetools repo è standard per debian/ubuntu, ma l'architettura è importante
    arch = facts["arch"]

    repo_path = "/etc/apt/sources.list.d/kubernetes.list"

    # Formato: deb [signed-by=...] https://.../ /
    # Aggiungiamo [arch=...] per robustezza
    repo_content = (
        f"deb [arch={arch} signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] "
        f"https://pkgs.k8s.io/core:/stable:/{k8s_version}/deb/ /\n"
    )

    res = _write_file(task, repo_path, repo_content)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to write k8s repo file")

    msg = f"K8s Repo set for {k8s_version} ({arch})" if res.changed else "K8s Repo up-to-date"
    return SubTaskResult(success=True, message=msg)


@automated_substep("Install Kube Tools")
def _install_packages(task: Task) -> SubTaskResult:
    """
    Installs kubelet, kubeadm, and kubectl.
    """
    # We update to see the new repo packages
    cmd = "sudo apt-get update && sudo apt-get install -y kubelet kubeadm kubectl"
    res = run_command(task, cmd)

    if res.failed:
        return SubTaskResult(success=False, message="Apt install failed")

    return SubTaskResult(success=True, message="Packages installed")


@automated_substep("Hold Package Versions")
def _hold_packages(task: Task) -> SubTaskResult:
    """
    Prevents automatic upgrades using apt-mark hold.
    """
    cmd = "sudo apt-mark hold kubelet kubeadm kubectl"
    res = run_command(task, cmd)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to hold packages")

    return SubTaskResult(success=True, message="Version lock enabled (held)")


@automated_substep("Enable Kubelet Service")
def _enable_service(task: Task) -> SubTaskResult:
    """
    Enables kubelet so it starts on boot, but doesn't start it immediately 
    (it crashes until configured by kubeadm).
    """
    cmd = "sudo systemctl enable kubelet"
    res = run_command(task, cmd)

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

    # 1. Dependencies
    s1 = _install_deps(task)
    if not s1.success: return fail(task, s1)

    # 2. Key Setup
    s2 = _setup_k8s_key(task, k8s_ver)
    if not s2.success: return fail(task, s2)

    # 3. Add Repo
    s3 = _add_k8s_repo(task, k8s_ver)
    if not s3.success: return fail(task, s3)

    # 4. Install Packages
    s4 = _install_packages(task)
    if not s4.success: return fail(task, s4)

    # 5. Hold Versions
    s5 = _hold_packages(task)
    if not s5.success: return fail(task, s5)

    # 6. Enable Service
    s6 = _enable_service(task)
    if not s6.success: return fail(task, s6)

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.CHANGED,
            message=f"Kubernetes tools ({k8s_ver}) installed & held."
        )
    )