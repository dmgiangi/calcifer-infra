from pathlib import Path

from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks.utils import fail, run_cmd


# --- SUB-STEPS ---

@automated_substep("Check Cluster Status")
def _check_initialization(task: Task) -> SubTaskResult:
    """
    Checks if /etc/kubernetes/admin.conf exists to determine if init is needed.
    """
    cmd = "test -f /etc/kubernetes/admin.conf"
    res = run_cmd(task, cmd)

    if not res.failed:
        return SubTaskResult(success=True, message="Cluster already initialized", data=True)

    return SubTaskResult(success=True, message="Cluster not initialized", data=False)


@automated_substep("Generate Kubeadm Config")
def _create_kubeadm_config(task: Task, pod_cidr: str) -> SubTaskResult:
    """
    Creates /tmp/kubeadm-config.yaml with dynamic Node IP and CIDR.
    """
    # task.host.hostname is the connection IP (ansible_host)
    # task.host.name is the inventory name (inventory_hostname)
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
    # Write to remote /tmp
    # We use echo with heredoc-like structure or printf to handle newlines
    # Using printf is safer for multiline variables
    cmd = f"printf '{config_content}' > /tmp/kubeadm-config.yaml"

    res = run_cmd(task, cmd)
    if res.failed:
        return SubTaskResult(success=False, message="Failed to write kubeadm-config.yaml")

    return SubTaskResult(success=True, message="Config created")


@automated_substep("Run Kubeadm Init")
def _run_kubeadm_init(task: Task) -> SubTaskResult:
    """
    Executes kubeadm init. This might take a while.
    """
    # Using sudo. --upload-certs is good practice for HA, added implicitly.
    cmd = "sudo kubeadm init --config /tmp/kubeadm-config.yaml --upload-certs"

    # Increase timeout for this specific command as init can take time (pulling images)
    # Note: Scrapli might need timeout adjustment in connection options, 
    # but usually default is enough if images are cached.
    res = run_cmd(task, cmd)

    if res.failed:
        # Extract last lines of error for context
        return SubTaskResult(success=False, message=f"Init failed. Output: {res.result[-200:]}")

    return SubTaskResult(success=True, message="Control Plane Initialized")


@automated_substep("Setup User Kubeconfig")
def _setup_user_kubeconfig(task: Task) -> SubTaskResult:
    """
    Copies admin.conf to ~/.kube/config and sets permissions for the current user.
    """
    # 1. Create directory
    run_cmd(task, "mkdir -p $HOME/.kube")

    # 2. Copy file (requires sudo to read source)
    cp_cmd = "sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config"
    res_cp = run_cmd(task, cp_cmd)

    if res_cp.failed:
        return SubTaskResult(success=False, message="Failed to copy kubeconfig")

    # 3. Fix permissions
    # We use $(id -u):$(id -g) to get current user/group ID dynamically
    chown_cmd = "sudo chown $(id -u):$(id -g) $HOME/.kube/config"
    res_chown = run_cmd(task, chown_cmd)

    if res_chown.failed:
        return SubTaskResult(success=False, message="Failed to set permissions")

    return SubTaskResult(success=True, message="User kubeconfig configured")


@automated_substep("Install CNI Plugin")
def _install_cni(task: Task, manifest_url: str) -> SubTaskResult:
    """
    Applies the CNI manifest (Flannel).
    """
    cmd = f"kubectl apply -f {manifest_url}"
    res = run_cmd(task, cmd)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to apply CNI manifest")

    return SubTaskResult(success=True, message="CNI Plugin installed")


@automated_substep("Untaint Control Plane")
def _untaint_node(task: Task) -> SubTaskResult:
    """
    Allows workloads to run on the Control Plane (Single Node Setup).
    Handles 'not found' error gracefully.
    """
    node_name = task.host.name
    cmd = f"kubectl taint nodes {node_name} node-role.kubernetes.io/control-plane:NoSchedule-"

    res = run_cmd(task, cmd)

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
    # 1. Read remote content
    cat_cmd = "sudo cat /etc/kubernetes/admin.conf"
    res_cat = run_cmd(task, cat_cmd)

    if res_cat.failed:
        return SubTaskResult(success=False, message="Failed to read remote admin.conf")

    remote_content = res_cat.result

    # 2. Write locally
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
    # Config retrieval
    config = task.host.get("app_config")
    pod_cidr = config["k8s"]["pod_network_cidr"]
    cni_url = config["k8s"]["cni_manifest_url"]

    # 1. Check Status
    step_check = _check_initialization(task)
    is_initialized = step_check.data  # Boolean

    if not is_initialized:
        # --- FRESH INSTALL ---

        # 2. Create Config
        s2 = _create_kubeadm_config(task, pod_cidr)
        if not s2.success: return fail(task, s2)

        # 3. Kubeadm Init
        s3 = _run_kubeadm_init(task)
        if not s3.success: return fail(task, s3)

    # --- CONVERGENCE (Run always) ---

    # 4. Setup User Kubeconfig (Ensure ~/.kube/config exists)
    s4 = _setup_user_kubeconfig(task)
    if not s4.success: return fail(task, s4)

    # 5. Install CNI
    s5 = _install_cni(task, cni_url)
    if not s5.success: return fail(task, s5)

    # 6. Untaint (Optional, good for dev clusters)
    s6 = _untaint_node(task)
    if not s6.success: return fail(task, s6)

    # 7. Fetch Config locally
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
