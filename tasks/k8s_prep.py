from typing import List, Dict

from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks.utils import run_cmd, fail


# --- SUB-STEPS ---

@automated_substep("Load Kernel Modules")
def _load_kernel_modules(task: Task, modules: List[str]) -> SubTaskResult:
    """
    Loads required kernel modules immediately and persists them for boot.
    """
    failed_mods = []

    # 1. Create persistence file
    # We construct the file content string
    file_content = "\n".join(modules)

    # Write to /etc/modules-load.d/k8s.conf
    # usage of tee ensures sudo permissions apply to the write operation
    echo_cmd = f"echo '{file_content}' | sudo tee /etc/modules-load.d/k8s.conf"
    res_persist = run_cmd(task, echo_cmd)

    if res_persist.failed:
        return SubTaskResult(success=False, message="Failed to write modules config file")

    # 2. Runtime Load (modprobe)
    for mod in modules:
        # Check if loaded first (optimization)
        check_cmd = f"lsmod | grep {mod}"
        res_check = run_cmd(task, check_cmd)

        if res_check.failed:
            # Not loaded, load it now
            res_load = run_cmd(task, f"sudo modprobe {mod}")
            if res_load.failed:
                failed_mods.append(mod)

    if failed_mods:
        return SubTaskResult(success=False, message=f"Failed to load modules: {failed_mods}")

    return SubTaskResult(success=True, message=f"Modules loaded & persisted: {', '.join(modules)}")


@automated_substep("Configure Sysctl Parameters")
def _configure_sysctl(task: Task, params: Dict[str, str]) -> SubTaskResult:
    """
    Writes sysctl params to file and reloads sysctl.
    """
    # 1. Prepare file content
    lines = [f"{key} = {value}" for key, value in params.items()]
    content = "\n".join(lines)

    # 2. Write to /etc/sysctl.d/k8s.conf
    write_cmd = f"echo '{content}' | sudo tee /etc/sysctl.d/k8s.conf"
    res_write = run_cmd(task, write_cmd)

    if res_write.failed:
        return SubTaskResult(success=False, message="Failed to write sysctl config")

    # 3. Apply changes (Reload)
    # --system loads settings from all system configuration files
    res_reload = run_cmd(task, "sudo sysctl --system")

    if res_reload.failed:
        return SubTaskResult(success=False, message="Failed to reload sysctl")

    return SubTaskResult(success=True, message=f"Applied {len(params)} sysctl parameters")


@automated_substep("Disable Swap (Runtime)")
def _disable_swap_runtime(task: Task) -> SubTaskResult:
    """
    Disables swap immediately using swapoff.
    """
    # Check if swap is active
    check_cmd = "swapon --show"
    res_check = run_cmd(task, check_cmd)

    # If result is empty, swap is already off
    if not res_check.result.strip():
        return SubTaskResult(success=True, message="Swap already disabled")

    # Disable it
    res_off = run_cmd(task, "sudo swapoff -a")
    if res_off.failed:
        return SubTaskResult(success=False, message="Failed to run swapoff")

    return SubTaskResult(success=True, message="Swap disabled at runtime")


@automated_substep("Disable Swap (Fstab)")
def _disable_swap_fstab(task: Task) -> SubTaskResult:
    """
    Comments out swap entries in /etc/fstab to persist across reboots.
    """
    # sed command to comment out lines containing 'swap' that are not already commented
    # regex explanation:
    # /^[^#].*swap/  -> Look for lines NOT starting with # that contain 'swap'
    # s/^/# /        -> Substitute start of line with '# '
    sed_cmd = "sudo sed -i '/^[^#].*swap/ s/^/# /' /etc/fstab"

    res = run_cmd(task, sed_cmd)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to update /etc/fstab")

    return SubTaskResult(success=True, message="/etc/fstab updated")


# --- MAIN TASK ---

@automated_step("Prepare Kubernetes Node")
def prepare_k8s_node(task: Task) -> Result:
    """
    Prepares the OS for Kubernetes: Modules, Sysctl, Swap.
    """
    # 1. Retrieve Config
    config = task.host.get("app_config")
    if not config or "k8s" not in config:
        return Result(host=task.host, failed=True, result=StandardResult(TaskStatus.FAILED, "Missing K8s config"))

    k8s_conf = config["k8s"]
    modules_list = k8s_conf.get("kernel_modules", [])
    sysctl_dict = k8s_conf.get("sysctl_params", {})

    # 2. Kernel Modules
    step_mod = _load_kernel_modules(task, modules_list)
    if not step_mod.success: return fail(task, step_mod)

    # 3. Sysctl Params
    step_sys = _configure_sysctl(task, sysctl_dict)
    if not step_sys.success: return fail(task, step_sys)

    # 4. Swap Runtime
    step_swap_run = _disable_swap_runtime(task)
    if not step_swap_run.success: return fail(task, step_swap_run)

    # 5. Swap Fstab
    step_swap_tab = _disable_swap_fstab(task)
    if not step_swap_tab.success: return fail(task, step_swap_tab)

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.CHANGED,  # This is almost always a "state enforcement"
            message="OS Prepared: Modules loaded, Sysctl applied, Swap disabled."
        )
    )


