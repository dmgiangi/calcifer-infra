import os
import subprocess
from pathlib import Path

from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import fail
from utils.linux import (
    run_command,
    write_file,
    read_file,
    remote_file_exists,
    remove_file
)


@automated_substep("Check Cluster Status")
def _check_initialization(task: Task) -> SubTaskResult:
    """
    Checks if /etc/kubernetes/admin.conf exists.
    """
    if remote_file_exists(task, "/etc/kubernetes/admin.conf"):
        return SubTaskResult(success=True, message="Cluster already initialized", data=True)

    return SubTaskResult(success=True, message="Cluster not initialized", data=False)


@automated_substep("Generate Kubeadm Config")
def _create_kubeadm_config(task: Task, pod_cidr: str) -> SubTaskResult:
    node_ip = task.host.hostname
    node_name = task.host.name

    config_content = f"""
apiVersion: kubeadm.k8s.io/v1beta3
kind: InitConfiguration
nodeRegistration:
  name: "{node_name}"
  kubeletExtraArgs:
    node-ip: "{node_ip}"
  taints: []
---
apiVersion: kubeadm.k8s.io/v1beta3
kind: ClusterConfiguration
networking:
  podSubnet: "{pod_cidr}"
"""
    res = write_file(task, "/tmp/kubeadm-config.yaml", config_content)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to write kubeadm-config.yaml")

    return SubTaskResult(success=True, message="Config created")


@automated_substep("Run Kubeadm Init")
def _run_kubeadm_init(task: Task) -> SubTaskResult:
    cmd = "kubeadm init --config /tmp/kubeadm-config.yaml --upload-certs"
    res = run_command(task, cmd, sudo=True)

    # CLEANUP
    remove_file(task, "/tmp/kubeadm-config.yaml", sudo=True)

    if res.failed:
        return SubTaskResult(success=False, message=f"Init failed. Output: {res.result[-200:]}")

    return SubTaskResult(success=True, message="Control Plane Initialized")


@automated_substep("Fetch Admin Config")
def _fetch_kubeconfig_local(task: Task, local_path_str: str) -> SubTaskResult:
    """
    Reads remote admin.conf and writes it to the configured LOCAL path.
    """
    # 1. Read Remote
    remote_content = read_file(task, "/etc/kubernetes/admin.conf")

    if not remote_content:
        return SubTaskResult(success=False, message="Failed to read remote admin.conf or file is empty")

    # 2. Write Local (using configured path)
    local_path = Path(local_path_str)
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "w") as f:
            f.write(remote_content)
        os.chmod(local_path, 0o600)
    except Exception as e:
        return SubTaskResult(success=False, message=f"Failed to write local file: {e}")

    return SubTaskResult(success=True, message=f"Saved to {local_path}")


@automated_substep("Setup User Kubeconfig (Remote)")
def _setup_user_kubeconfig(task: Task) -> SubTaskResult:
    # Use $HOME expansion from shell
    run_command(task, "mkdir -p $HOME/.kube")

    cp_cmd = "cp -i /etc/kubernetes/admin.conf $HOME/.kube/config"
    res_cp = run_command(task, cp_cmd, sudo=True)

    if res_cp.failed:
        return SubTaskResult(success=False, message="Failed to copy kubeconfig")

    chown_cmd = "chown $(id -u):$(id -g) $HOME/.kube/config"
    res_chown = run_command(task, chown_cmd, sudo=True)

    if res_chown.failed:
        return SubTaskResult(success=False, message="Failed to set permissions")

    return SubTaskResult(success=True, message="Remote User kubeconfig configured")


@automated_substep("Install CNI Plugin (Local)")
def _install_cni(task: Task, manifest_url: str, kubeconfig_path: str) -> SubTaskResult:
    """
    Applies CNI locally using the configured kubeconfig path.
    """
    if not Path(kubeconfig_path).exists():
        return SubTaskResult(success=False, message=f"Local kubeconfig not found at {kubeconfig_path}")

    cmd = f"export KUBECONFIG={Path(kubeconfig_path).absolute()} && kubectl apply -f {manifest_url}"

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        if proc.returncode != 0:
            return SubTaskResult(success=False, message=f"CNI Install Failed: {proc.stderr}")
    except Exception as e:
        return SubTaskResult(success=False, message=f"Local execution error: {e}")

    return SubTaskResult(success=True, message="CNI Plugin installed via Local Kubectl")


@automated_substep("Untaint Control Plane (Local)")
def _untaint_node(task: Task, kubeconfig_path: str) -> SubTaskResult:
    """
    Untaints node locally using the configured kubeconfig path.
    """
    node_name = task.host.name

    cmd = (
        f"export KUBECONFIG={Path(kubeconfig_path).absolute()} && "
        f"kubectl taint nodes {node_name} node-role.kubernetes.io/control-plane:NoSchedule-"
    )

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        if proc.returncode != 0 and "not found" not in proc.stderr:
            return SubTaskResult(success=False, message=f"Untaint Failed: {proc.stderr}")
    except Exception as e:
        return SubTaskResult(success=False, message=f"Local execution error: {e}")

    return SubTaskResult(success=True, message="Control Plane untainted via Local Kubectl")


# --- MAIN TASK ---

@automated_step("Initialize Control Plane")
def init_control_plane(task: Task) -> Result:
    """
    Initializes K8s CP and configures it locally using paths from Settings.
    """
    config = task.host.get("app_config")

    # Retrieve parameters from Settings
    pod_cidr = config["k8s"]["pod_network_cidr"]
    cni_url = config["k8s"]["cni_manifest_url"]
    local_kube_path = config["k8s"]["local_kubeconfig_path"]  # <--- FROM SETTINGS

    # 1. Check Status
    step_check = _check_initialization(task)
    is_initialized = step_check.data

    if not is_initialized:
        s2 = _create_kubeadm_config(task, pod_cidr)
        if not s2.success: return fail(task, s2)

        s3 = _run_kubeadm_init(task)
        if not s3.success: return fail(task, s3)

    # 4. Fetch Config (We pass the configured path)
    s4 = _fetch_kubeconfig_local(task, local_kube_path)
    if not s4.success: return fail(task, s4)

    # 5. Remote User Config
    s5 = _setup_user_kubeconfig(task)
    if not s5.success: return fail(task, s5)

    # 6. Install CNI (We pass the configured path)
    s6 = _install_cni(task, cni_url, local_kube_path)
    if not s6.success: return fail(task, s6)

    # 7. Untaint (We pass the configured path)
    s7 = _untaint_node(task, local_kube_path)
    if not s7.success: return fail(task, s7)

    status_msg = "Cluster Initialized & Configured" if not is_initialized else "Cluster Already Up"

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.CHANGED if not is_initialized else TaskStatus.OK,
            message=status_msg
        )
    )
