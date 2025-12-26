from pathlib import Path

from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import fail, run_command
from tasks.files import _write_file


# --- SUB-STEPS ---

@automated_substep("Install Flux CLI")
def _install_flux_cli(task: Task) -> SubTaskResult:
    check_cmd = "which flux"
    if not run_command(task, check_cmd).failed:
        return SubTaskResult(success=True, message="Flux CLI already installed")

    cmd = "curl -sS https://fluxcd.io/install.sh | sudo bash"
    res = run_command(task, cmd)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to install Flux CLI")

    return SubTaskResult(success=True, message="Flux CLI installed")


@automated_substep("Configure Flux SSH Key")
def _configure_ssh_key(task: Task, local_path: str, remote_path: str) -> SubTaskResult:
    # 1. Read Local Key
    local_file = Path(local_path)
    if not local_file.exists():
        return SubTaskResult(success=False, message=f"Local key not found at {local_path}")

    try:
        key_content = local_file.read_text().strip()
    except Exception as e:
        return SubTaskResult(success=False, message=f"Failed to read local key: {e}")

    # 2. Ensure Remote Directory
    remote_dir = str(Path(remote_path).parent)
    run_command(task, f"mkdir -p {remote_dir}")

    # 3. Write Remote File (Secure)
    # WARNING: Owned by root initially
    res_write = _write_file(task, remote_path, key_content)

    if res_write.failed:
        return SubTaskResult(success=False, message="Failed to write remote key file")

    # 4. Fix Permissions & Ownership (Secure 600)
    run_command(task, f"chmod 0600 {remote_path}", sudo=True)
    run_command(task, f"chown $(id -u):$(id -g) {remote_path}", sudo=True)

    return SubTaskResult(success=True, message="SSH Key configured")


@automated_substep("Bootstrap Flux & Cleanup")
def _bootstrap_flux(task: Task, config: dict) -> SubTaskResult:
    """
    Runs 'flux bootstrap' and CLEANS UP the private key afterwards.
    """
    marker_file = "/var/lib/flux_bootstrapped"

    if not run_command(task, f"test -f {marker_file}").failed:
        return SubTaskResult(success=True, message="Bootstrap already completed")

    flux_conf = config["k8s"]["flux"]
    url = flux_conf["github_url"]
    branch = flux_conf["branch"]
    path = flux_conf["cluster_path"]
    key_path = flux_conf["remote_key_path"]

    bootstrap_cmd = (
        f"export KUBECONFIG=/etc/kubernetes/admin.conf && "
        f"flux bootstrap git "
        f"--url={url} "
        f"--branch={branch} "
        f"--path={path} "
        f"--private-key-file={key_path} "
        f"--silent"
    )

    # Execute Bootstrap
    res = run_command(task, bootstrap_cmd)

    # --- SECURITY CLEANUP ---
    # Delete the private key file from the host.
    # It is now safely stored as a Kubernetes Secret.
    run_command(task, f"rm -f {key_path}", sudo=True)

    if res.failed:
        err_snippet = res.result[-200:] if res.result else "Unknown Error"
        return SubTaskResult(success=False, message=f"Bootstrap failed: {err_snippet}")

    run_command(task, f"touch {marker_file}", sudo=True)

    return SubTaskResult(success=True, message="Flux Bootstrapped (Key cleaned up)")


# --- MAIN TASK ---

@automated_step("Install & Bootstrap FluxCD")
def setup_fluxcd(task: Task) -> Result:
    config = task.host.get("app_config")

    if not config["k8s"]["flux"]["enabled"]:
        return Result(host=task.host, result=StandardResult(TaskStatus.SKIPPED, "Flux disabled"))

    local_key = config["k8s"]["flux"]["local_key_path"]
    remote_key = config["k8s"]["flux"]["remote_key_path"]

    s1 = _install_flux_cli(task)
    if not s1.success: return fail(task, s1)

    s2 = _configure_ssh_key(task, local_path=local_key, remote_path=remote_key)
    if not s2.success: return fail(task, s2)

    s3 = _bootstrap_flux(task, config)
    if not s3.success: return fail(task, s3)

    return Result(
        host=task.host,
        result=StandardResult(TaskStatus.CHANGED, "GitOps Pipeline Active")
    )