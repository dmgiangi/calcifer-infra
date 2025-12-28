from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import fail
from utils.linux import (
    apt_install,
    add_apt_repository,
    run_command,
    write_file,
    read_file,
    remote_file_exists,
    make_directory,
    systemctl
)


# --- SUB-STEPS ---

@automated_substep("Install Dependencies")
def _install_deps(task: Task) -> SubTaskResult:
    """
    Installs prerequisites for fetching repositories over HTTPS.
    """
    pkgs = "ca-certificates curl gnupg apt-transport-https software-properties-common"
    res = apt_install(task, pkgs)
    
    if res.failed:
        return SubTaskResult(success=False, message=f"Failed to install dependencies: {res.result}")
    return SubTaskResult(success=True, message="Dependencies installed")


@automated_substep("Configure Docker Repository")
def _add_docker_repo(task: Task) -> SubTaskResult:
    """
    Adds the Docker repository using the centralized apt utility.
    """
    facts = task.host.get("os_facts")
    if not facts:
        return SubTaskResult(success=False, message="Missing OS Facts. Run 'gather_system_facts' first.")

    distro_id = facts.get("id", "ubuntu")
    codename = facts.get("codename", "jammy")
    arch = facts.get("arch", "amd64")

    key_path = "/etc/apt/keyrings/docker.gpg"

    repo_string = (
        f"deb [arch={arch} signed-by={key_path}] "
        f"https://download.docker.com/linux/{distro_id} {codename} stable\n"
    )

    return add_apt_repository(
        task,
        repo_name="docker",
        repo_string=repo_string,
        gpg_key_url=f"https://download.docker.com/linux/{distro_id}/gpg",
        gpg_key_path=key_path,
    )


@automated_substep("Install Containerd Package")
def _install_containerd(task: Task) -> SubTaskResult:
    """
    Updates apt cache and installs containerd.io.
    """
    res = apt_install(task, "containerd.io")

    if res.failed:
        return SubTaskResult(success=False, message=f"Apt install failed: {res.result}")

    return SubTaskResult(success=True, message="Containerd installed")


@automated_substep("Configure Containerd (config.toml)")
def _configure_containerd(task: Task) -> SubTaskResult:
    """
    Generates default config and enables SystemdCgroup.
    """
    config_path = "/etc/containerd/config.toml"
    import re

    # 1. Generate Default Config if missing
    make_directory(task, "/etc/containerd", sudo=True)

    if not remote_file_exists(task, config_path):
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
    content = re.sub(r'(disabled_plugins\s*=\s*\[.*)("cri",?.*\\])', r'\1]', content)
    
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
    res = systemctl(task, "containerd", "restart", enable=True)

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
    # 1. Dependencies
    s1 = _install_deps(task)
    if not s1.success: return fail(task, s1)

    # 2. Add Docker Repo (includes GPG)
    s2 = _add_docker_repo(task)
    if not s2.success: return fail(task, s2)

    # 3. Install Package
    s3 = _install_containerd(task)
    if not s3.success: return fail(task, s3)

    # 4. Configure (config.toml)
    s4 = _configure_containerd(task)
    if not s4.success: return fail(task, s4)

    # 5. Service Restart
    s5 = _restart_service(task)
    if not s5.success: return fail(task, s5)

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.CHANGED,  # Usually implies state enforcement
            message="Containerd installed, configured (SystemdCgroup) & running."
        )
    )
