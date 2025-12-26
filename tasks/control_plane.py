from pathlib import Path

from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import fail, run_command, write_file


# --- SUB-STEPS ---

@automated_substep("Check Cluster Status")
def _check_initialization(task: Task) -> SubTaskResult:
    """
    Checks if /etc/kubernetes/admin.conf exists to determine if init is needed.
    """
    cmd = "test -f /etc/kubernetes/admin.conf"
    res = run_command(task, cmd)

    if not res.failed:
        return SubTaskResult(success=True, message="Cluster already initialized", data=True)

    return SubTaskResult(success=True, message="Cluster not initialized", data=False)


@automated_substep("Generate Kubeadm Config")
def _create_kubeadm_config(task: Task, pod_cidr: str) -> SubTaskResult:
    """
    Creates /tmp/kubeadm-config.yaml using the secure write_file utility.
    """
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
    # USIAMO write_file INVECE DI PRINTF
    # Gestisce automaticamente MD5 check e scrittura sicura via base64
    res = write_file(task, "/tmp/kubeadm-config.yaml", config_content)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to write kubeadm-config.yaml")

    return SubTaskResult(success=True, message="Config created")


@automated_substep("Run Kubeadm Init")
def _run_kubeadm_init(task: Task) -> SubTaskResult:
    """
    Executes kubeadm init.
    """
    cmd = "sudo kubeadm init --config /tmp/kubeadm-config.yaml --upload-certs"

    res = run_command(task, cmd)

    # CLEANUP: Rimuoviamo il file di config dopo l'uso per sicurezza
    run_command(task, "rm /tmp/kubeadm-config.yaml", sudo=True)

    if res.failed:
        return SubTaskResult(success=False, message=f"Init failed. Output: {res.result[-200:]}")

    return SubTaskResult(success=True, message="Control Plane Initialized")


@automated_substep("Setup User Kubeconfig")
def _setup_user_kubeconfig(task: Task) -> SubTaskResult:
    """
    Copies admin.conf to ~/.kube/config and sets permissions for the current user.
    """
    # 1. Create directory
    run_command(task, "mkdir -p $HOME/.kube")

    # 2. Copy file (requires sudo to read source)
    cp_cmd = "sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config"
    res_cp = run_command(task, cp_cmd)

    if res_cp.failed:
        return SubTaskResult(success=False, message="Failed to copy kubeconfig")

    # 3. Fix permissions
    chown_cmd = "sudo chown $(id -u):$(id -g) $HOME/.kube/config"
    res_chown = run_command(task, chown_cmd)

    if res_chown.failed:
        return SubTaskResult(success=False, message="Failed to set permissions")

    return SubTaskResult(success=True, message="User kubeconfig configured")


@automated_substep("Install CNI Plugin")
def _install_cni(task: Task, manifest_url: str) -> SubTaskResult:
    """
    Applies the CNI manifest (Flannel).
    """
    cmd = f"kubectl apply -f {manifest_url}"
    res = run_command(task, cmd)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to apply CNI manifest")

    return SubTaskResult(success=True, message="CNI Plugin installed")


@automated_substep("Untaint Control Plane")
def _untaint_node(task: Task) -> SubTaskResult:
    """
    Allows workloads to run on the Control Plane.
    """
    node_name = task.host.name
    cmd = f"kubectl taint nodes {node_name} node-role.kubernetes.io/control-plane:NoSchedule-"

    res = run_command(task, cmd)

    if res.failed:
        if "not found" in res.result:
            return SubTaskResult(success=True, message="Taint already removed")
        return SubTaskResult(success=False, message=f"Failed to untaint: {res.result}")

    return SubTaskResult(success=True, message="Control Plane untainted")


@automated_substep("Fetch Admin Config")
def _fetch_kubeconfig_local(task: Task) -> SubTaskResult:
    """
    Reads the remote admin.conf and writes it to the LOCAL project directory.
    """
    cat_cmd = "sudo cat /etc/kubernetes/admin.conf"
    res_cat = run_command(task, cat_cmd)

    if res_cat.failed:
        return SubTaskResult(success=False, message="Failed to read remote admin.conf")

    remote_content = res_cat.result

    local_path = Path("inventory/kubeconfig_admin.yaml")
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "w") as f:
            f.write(remote_content)
    except Exception as e:
        return SubTaskResult(success=False, message=f"Failed to write local file: {e}")

    return SubTaskResult(success=True, message=f"Saved to {local_path}")


# --- MAIN TASK ---

@automated_step("Initialize Control Plane")
def init_control_plane(task: Task) -> Result:
    """
    Initializes the K8s Control Plane (Kubeadm Init), Network, and Local Config.
    """
    config = task.host.get("app_config")
    pod_cidr = config["k8s"]["pod_network_cidr"]
    cni_url = config["k8s"]["cni_manifest_url"]

    step_check = _check_initialization(task)
    is_initialized = step_check.data

    if not is_initialized:
        s2 = _create_kubeadm_config(task, pod_cidr)
        if not s2.success: return fail(task, s2)

        s3 = _run_kubeadm_init(task)
        if not s3.success: return fail(task, s3)

    s4 = _setup_user_kubeconfig(task)
    if not s4.success: return fail(task, s4)

    s5 = _install_cni(task, cni_url)
    if not s5.success: return fail(task, s5)

    s6 = _untaint_node(task)
    if not s6.success: return fail(task, s6)

    s7 = _fetch_kubeconfig_local(task)
    if not s7.success: return fail(task, s7)

    status_msg = "Cluster Initialized" if not is_initialized else "Cluster Already Up (Verified CNI/Taints)"

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.CHANGED if not is_initialized else TaskStatus.OK,
            message=status_msg
        )
    )
