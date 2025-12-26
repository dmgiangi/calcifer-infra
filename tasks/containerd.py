from nornir.core.task import Task, Result
from nornir_scrapli.tasks import send_command

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks.utils import run_local, fail


# --- HELPER ---
def _run_cmd(task: Task, cmd: str):
    """Executes shell command locally or via SSH based on platform."""
    if task.host.platform == "linux_local":
        return task.run(task=run_local, command=cmd)
    else:
        return task.run(task=send_command, command=cmd)


# --- SUB-STEPS ---

@automated_substep("Install Dependencies")
def _install_deps(task: Task) -> SubTaskResult:
    """
    Installs prerequisites (curl, gnupg, lsb-release, etc.).
    """
    pkgs = "ca-certificates curl gnupg apt-transport-https software-properties-common lsb-release"
    # -y for auto-yes, -qq for quiet
    cmd = f"sudo apt-get update && sudo apt-get install -y {pkgs}"

    res = _run_cmd(task, cmd)
    if res.failed:
        return SubTaskResult(success=False, message="Failed to install dependencies")

    return SubTaskResult(success=True, message="Dependencies installed")


@automated_substep("Setup Docker GPG Key")
def _setup_gpg(task: Task) -> SubTaskResult:
    """
    Downloads and dearmors the Docker GPG key if not present.
    """
    keyring_path = "/etc/apt/keyrings/docker.gpg"

    # 1. Check if key exists
    check_cmd = f"test -f {keyring_path}"
    if not _run_cmd(task, check_cmd).failed:
        return SubTaskResult(success=True, message="GPG Key already present")

    # 2. Setup directory
    _run_cmd(task, "sudo mkdir -p /etc/apt/keyrings")

    # 3. Download & Dearmor (Pipeline)
    url = "https://download.docker.com/linux/ubuntu/gpg"
    # curl -> gpg dearmor -> tee to file
    cmd = f"curl -fsSL {url} | sudo gpg --dearmor -o {keyring_path}"

    res = _run_cmd(task, cmd)
    if res.failed:
        return SubTaskResult(success=False, message="Failed to download/dearmor GPG key")

    # Ensure permissions
    _run_cmd(task, f"sudo chmod a+r {keyring_path}")

    return SubTaskResult(success=True, message="GPG Key setup complete")


@automated_substep("Add Docker Repository")
def _add_repo(task: Task) -> SubTaskResult:
    """
    Adds the Docker/Containerd repository to sources.list.d.
    """
    repo_file = "/etc/apt/sources.list.d/docker.list"

    # Check if file exists
    if not _run_cmd(task, f"test -f {repo_file}").failed:
        return SubTaskResult(success=True, message="Repository file already exists")

    # Determine Architecture and OS Release dynamically
    # We assume standard Ubuntu/Debian structure here as per Ansible role

    # Get codename (e.g., jammy, focal)
    res_rel = _run_cmd(task, "lsb_release -cs")
    if res_rel.failed:
        return SubTaskResult(success=False, message="Failed to detect OS release")
    codename = res_rel.result.strip()

    repo_line = (
        f"deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] "
        f"https://download.docker.com/linux/ubuntu {codename} stable"
    )

    cmd = f"echo '{repo_line}' | sudo tee {repo_file}"
    res = _run_cmd(task, cmd)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to add repository file")

    return SubTaskResult(success=True, message="Repository added")


@automated_substep("Install Containerd")
def _install_containerd(task: Task) -> SubTaskResult:
    """
    Installs the containerd.io package.
    """
    # Force update to ensure the new repo is read
    cmd = "sudo apt-get update && sudo apt-get install -y containerd.io"
    res = _run_cmd(task, cmd)

    if res.failed:
        return SubTaskResult(success=False, message="Apt install failed")

    return SubTaskResult(success=True, message="Containerd installed")


@automated_substep("Configure Containerd (config.toml)")
def _configure_containerd(task: Task) -> SubTaskResult:
    """
    Generates default config and applies K8s specific settings (SystemdCgroup).
    """
    config_path = "/etc/containerd/config.toml"

    # 1. Generate Default Config if missing
    # We create the dir just in case
    _run_cmd(task, "sudo mkdir -p /etc/containerd")

    # We check if file exists. 
    # NOTE: If you want to FORCE reset the config every time, remove the check.
    # For idempotency with safety, we check first.
    exists = not _run_cmd(task, f"test -f {config_path}").failed

    if not exists:
        gen_cmd = f"containerd config default | sudo tee {config_path}"
        if _run_cmd(task, gen_cmd).failed:
            return SubTaskResult(success=False, message="Failed to generate default config")

    # 2. Apply SystemdCgroup = true
    # Equivalent to Ansible replace module
    # sed -i 's/search_pattern/replacement/g' file
    sed_cgroup = "sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' " + config_path
    res_sed = _run_cmd(task, sed_cgroup)

    # 3. Ensure CRI is not disabled
    # Equivalent to Ansible lineinfile state=absent
    # We remove lines matching "disabled_plugins.*cri"
    sed_cri = "sudo sed -i '/disabled_plugins.*cri/d' " + config_path
    _run_cmd(task, sed_cri)

    if res_sed.failed:
        return SubTaskResult(success=False, message="Failed to patch config.toml")

    return SubTaskResult(success=True, message="Config patched (SystemdCgroup=true)")


@automated_substep("Restart Containerd Service")
def _restart_service(task: Task) -> SubTaskResult:
    """
    Restarts and enables containerd.
    """
    cmd = "sudo systemctl restart containerd && sudo systemctl enable containerd"
    res = _run_cmd(task, cmd)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to restart service")

    return SubTaskResult(success=True, message="Service restarted & enabled")


# --- MAIN TASK ---

@automated_step("Install & Configure Containerd")
def install_containerd(task: Task) -> Result:
    """
    Full pipeline to setup Containerd as CRI for Kubernetes.
    """

    # 1. Dependencies
    s1 = _install_deps(task)
    if not s1.success: return fail(task, s1)

    # 2. GPG Key
    s2 = _setup_gpg(task)
    if not s2.success: return fail(task, s2)

    # 3. Repo
    s3 = _add_repo(task)
    if not s3.success: return fail(task, s3)

    # 4. Install Package
    s4 = _install_containerd(task)
    if not s4.success: return fail(task, s4)

    # 5. Configure (config.toml)
    s5 = _configure_containerd(task)
    if not s5.success: return fail(task, s5)

    # 6. Service Restart
    s6 = _restart_service(task)
    if not s6.success: return fail(task, s6)

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.CHANGED,
            message="Containerd installed, configured (SystemdCgroup) & running."
        )
    )
