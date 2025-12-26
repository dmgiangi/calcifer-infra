from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks.files import _write_file, ensure_line_in_file
from tasks.utils import fail, run_cmd


# --- SUB-STEPS ---

@automated_substep("Install Dependencies")
def _install_deps(task: Task) -> SubTaskResult:
    """
    Installs prerequisites for fetching repositories over HTTPS.
    """
    pkgs = "ca-certificates curl gnupg apt-transport-https software-properties-common"
    cmd = f"sudo apt-get update && sudo apt-get install -y {pkgs}"

    res = run_cmd(task, cmd)
    if res.failed:
        return SubTaskResult(success=False, message="Failed to install dependencies")
    return SubTaskResult(success=True, message="Dependencies installed")


@automated_substep("Setup Docker GPG Key")
def _setup_gpg(task: Task, distro_id: str) -> SubTaskResult:
    """
    Downloads and dearmors the Docker GPG key if not present.
    """
    keyring_path = "/etc/apt/keyrings/docker.gpg"

    # 1. Idempotency Check
    if not run_cmd(task, f"test -f {keyring_path}").failed:
        return SubTaskResult(success=True, message="GPG Key already present")

    # 2. Prepare Directory
    run_cmd(task, "sudo mkdir -p /etc/apt/keyrings")

    # 3. Download & Dearmor
    # Note: Docker usually serves the key at the same path for linux distros, 
    # but using the distro_id ensures correctness.
    url = f"https://download.docker.com/linux/{distro_id}/gpg"

    cmd = f"curl -fsSL {url} | sudo gpg --dearmor -o {keyring_path}"

    res = run_cmd(task, cmd)
    if res.failed:
        return SubTaskResult(success=False, message=f"Failed to download GPG key from {url}")

    # 4. Set Permissions
    run_cmd(task, f"sudo chmod a+r {keyring_path}")

    return SubTaskResult(success=True, message="GPG Key setup complete")


@automated_substep("Configure Docker Repository")
def _add_repo(task: Task) -> SubTaskResult:
    """
    Generates the sources.list file dynamically based on OS Facts (Arch/Distro).
    """
    facts = task.host.get("os_facts")
    if not facts:
        return SubTaskResult(success=False, message="Missing OS Facts. Run 'gather_system_facts' first.")

    distro_id = facts["id"]  # e.g., ubuntu, debian
    codename = facts["codename"]  # e.g., jammy, bookworm
    arch = facts["arch"]  # e.g., amd64, arm64

    repo_path = "/etc/apt/sources.list.d/docker.list"

    # Construct the repo line dynamically
    repo_content = (
        f"deb [arch={arch} signed-by=/etc/apt/keyrings/docker.gpg] "
        f"https://download.docker.com/linux/{distro_id} {codename} stable\n"
    )

    # Atomic write using our secure helper
    res = _write_file(task, repo_path, repo_content)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to write docker.list")

    msg = f"Repo added for {distro_id}/{codename} ({arch})" if res.changed else "Repo up-to-date"
    return SubTaskResult(success=True, message=msg)


@automated_substep("Install Containerd Package")
def _install_containerd(task: Task) -> SubTaskResult:
    """
    Updates apt cache and installs containerd.io.
    """
    # Force update to ensure the new repo is picked up
    cmd = "sudo apt-get update && sudo apt-get install -y containerd.io"
    res = run_cmd(task, cmd)

    if res.failed:
        return SubTaskResult(success=False, message="Apt install failed")

    return SubTaskResult(success=True, message="Containerd installed")


@automated_substep("Configure Containerd (config.toml)")
def _configure_containerd(task: Task) -> SubTaskResult:
    """
    Generates default config and enables SystemdCgroup.
    """
    config_path = "/etc/containerd/config.toml"

    # 1. Generate Default Config if missing
    run_cmd(task, "sudo mkdir -p /etc/containerd")

    exists = not run_cmd(task, f"test -f {config_path}").failed

    if not exists:
        gen_cmd = f"containerd config default | sudo tee {config_path}"
        if run_cmd(task, gen_cmd).failed:
            return SubTaskResult(success=False, message="Failed to generate default config")

    # 2. Patch: SystemdCgroup = true
    # We use ensure_line_in_file with regex to replace the existing setting
    target_line = "            SystemdCgroup = true"
    regex = r"\s*SystemdCgroup\s*=\s*false"

    res_patch = ensure_line_in_file(task, config_path, target_line, match_regex=regex)

    # 3. Cleanup: Ensure CRI plugin is not disabled (sanity check)
    # Using sed for deletion is simpler here as ensure_line_in_file adds/replaces
    sed_cri = f"sudo sed -i '/disabled_plugins.*cri/d' {config_path}"
    run_cmd(task, sed_cri)

    if res_patch.failed:
        return SubTaskResult(success=False, message="Failed to patch config.toml")

    msg = "Config patched (SystemdCgroup=true)" if res_patch.changed else "Config already correct"
    return SubTaskResult(success=True, message=msg)


@automated_substep("Restart Containerd Service")
def _restart_service(task: Task) -> SubTaskResult:
    """
    Restarts and enables the containerd service.
    """
    cmd = "sudo systemctl restart containerd && sudo systemctl enable containerd"
    res = run_cmd(task, cmd)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to restart service")

    return SubTaskResult(success=True, message="Service restarted & enabled")


# --- MAIN TASK ---

@automated_step("Install & Configure Containerd")
def install_containerd(task: Task) -> Result:
    """
    Full pipeline to setup Containerd as CRI for Kubernetes.
    Supports multi-arch and multi-distro via OS Facts.
    """
    # Retrieve OS Facts for dynamic configuration
    facts = task.host.get("os_facts")
    distro_id = facts.get("id", "ubuntu") if facts else "ubuntu"

    # 1. Dependencies
    s1 = _install_deps(task)
    if not s1.success: return fail(task, s1)

    # 2. GPG Key
    s2 = _setup_gpg(task, distro_id)
    if not s2.success: return fail(task, s2)

    # 3. Repository
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
            status=TaskStatus.CHANGED,  # Usually implies state enforcement
            message="Containerd installed, configured (SystemdCgroup) & running."
        )
    )
