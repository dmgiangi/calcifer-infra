from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import fail, run_command, write_file, read_file


# --- SUB-STEPS ---

@automated_substep("Install Dependencies")
def _install_deps(task: Task) -> SubTaskResult:
    """
    Installs prerequisites for fetching repositories over HTTPS.
    """
    pkgs = "ca-certificates curl gnupg apt-transport-https software-properties-common"
    cmd = f"sudo apt-get update && sudo apt-get install -y {pkgs}"

    res = run_command(task, cmd)
    if res.failed:
        return SubTaskResult(success=False, message="Failed to install dependencies")
    return SubTaskResult(success=True, message="Dependencies installed")


@automated_substep("Setup Docker GPG Key")
def _setup_gpg(task: Task, distro_id: str) -> SubTaskResult:
    """
    Downloads and dearmors the Docker GPG key if not present.
    """
    keyring_path = "/etc/apt/keyrings/docker.gpg"
    temp_key_path = "/tmp/docker.gpg.asc"

    # 1. Idempotency Check
    if not run_command(task, f"test -f {keyring_path}").failed:
        return SubTaskResult(success=True, message="GPG Key already present")

    # 2. Prepare Directory
    run_command(task, "mkdir -p /etc/apt/keyrings", True)

    # 3. Download
    url = f"https://download.docker.com/linux/{distro_id}/gpg"
    download_cmd = f"curl -fsSL {url} -o {temp_key_path}"
    res_download = run_command(task, download_cmd)
    if res_download.failed:
        return SubTaskResult(success=False, message=f"Failed to download GPG key from {url}")

    # 4. Dearmor
    dearmor_cmd = f"gpg --dearmor -o {keyring_path} {temp_key_path}"
    res_dearmor = run_command(task, dearmor_cmd, sudo=True)

    # 5. Cleanup
    run_command(task, f"rm {temp_key_path}")

    if res_dearmor.failed:
        return SubTaskResult(success=False, message="Failed to dearmor GPG key")

    # 6. Set Permissions
    run_command(task, f"chmod a+r {keyring_path}", True)

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
    res = write_file(task, repo_path, repo_content)

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
    res = run_command(task, cmd)

    if res.failed:
        return SubTaskResult(success=False, message="Apt install failed")

    return SubTaskResult(success=True, message="Containerd installed")


@automated_substep("Configure Containerd (config.toml)")
def _configure_containerd(task: Task) -> SubTaskResult:
    """
    Generates default config and enables SystemdCgroup.
    """
    config_path = "/etc/containerd/config.toml"
    import re

    # 1. Generate Default Config if missing
    run_command(task, "mkdir -p /etc/containerd", True)

    exists = not run_command(task, f"test -f {config_path}").failed

    if not exists:
        gen_cmd = "containerd config default"
        res_gen = run_command(task, gen_cmd)
        if res_gen.failed:
            return SubTaskResult(success=False, message="Failed to generate default config")

        res_write = write_file(task, config_path, res_gen.result)
        if res_write.failed:
            return SubTaskResult(success=False, message=f"Failed to write config file: {res_write.result}")

    # 2. Patch: SystemdCgroup = true and remove disabled_plugins for cri
    content = read_file(task, config_path)

    # Enable SystemdCgroup
    content = re.sub(r"(\s*SystemdCgroup\s*=\s*)false", r"\1true", content)

    # Remove CRI from disabled_plugins
    content = re.sub(r'(disabled_plugins\s*=\s*\[.*)("cri",?.*\])', r'\1]', content)

    res_patch = write_file(task, config_path, content)

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
    res = run_command(task, cmd)

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
