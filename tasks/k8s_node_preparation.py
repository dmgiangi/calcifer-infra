import re
from typing import List, Dict

from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import fail
from utils.linux import (
    write_file,
    read_file,
    is_module_loaded,
    load_module,
    reload_sysctl,
    is_swap_active,
    disable_swap
)


# --- SUB-STEPS ---

@automated_substep("Load Kernel Modules")
def _load_kernel_modules(task: Task, modules: List[str]) -> SubTaskResult:
    """
    Loads required kernel modules immediately and persists them for boot.
    """
    failed_mods = []

    # 1. Create persistence file
    file_content = "\n".join(modules) + "\n"  # Add trailing newline

    # Write to /etc/modules-load.d/k8s.conf using robust write_file
    res_persist = write_file(task, "/etc/modules-load.d/k8s.conf", file_content)

    if res_persist.failed:
        return SubTaskResult(success=False, message=f"Failed to write modules config: {res_persist.result}")

    # 2. Runtime Load (modprobe)
    for mod in modules:
        # Check if loaded first (optimization)
        if not is_module_loaded(task, mod):
            # Not loaded, load it now
            res_load = load_module(task, mod)
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
    content = "\n".join(lines) + "\n"

    # 2. Write to /etc/sysctl.d/k8s.conf using robust write_file
    res_write = write_file(task, "/etc/sysctl.d/k8s.conf", content)

    if res_write.failed:
        return SubTaskResult(success=False, message=f"Failed to write sysctl config: {res_write.result}")

    # 3. Apply changes (Reload)
    # --system loads settings from all system configuration files
    res_reload = reload_sysctl(task)

    if res_reload.failed:
        return SubTaskResult(success=False, message="Failed to reload sysctl")

    return SubTaskResult(success=True, message=f"Applied {len(params)} sysctl parameters")


@automated_substep("Disable Swap (Runtime)")
def _disable_swap_runtime(task: Task) -> SubTaskResult:
    """
    Disables swap immediately using swapoff.
    """
    # Check if swap is active
    if not is_swap_active(task):
        return SubTaskResult(success=True, message="Swap already disabled")

    # Disable it
    res_off = disable_swap(task)
    if res_off.failed:
        return SubTaskResult(success=False, message="Failed to run swapoff")

    return SubTaskResult(success=True, message="Swap disabled at runtime")


@automated_substep("Disable Swap (Fstab)")
def _disable_swap_fstab(task: Task) -> SubTaskResult:
    """
    Comments out swap entries in /etc/fstab to persist across reboots.
    Uses read-modify-write pattern with write_file (ensures backup).
    """
    fstab_path = "/etc/fstab"

    # 1. Read current content
    current_content = read_file(task, fstab_path)
    if not current_content:
        # Se fallisce la lettura o è vuoto (improbabile per fstab), meglio fermarsi
        return SubTaskResult(success=False, message="Could not read /etc/fstab")

    # 2. Modify content in Python (Safe Regex)
    lines = current_content.splitlines()
    new_lines = []
    changed = False

    # Regex: Linee che NON iniziano con # e contengono 'swap'
    swap_regex = re.compile(r"^[^#].*swap")

    for line in lines:
        if swap_regex.search(line):
            new_lines.append(f"# {line} # Disabled by Calcifer")
            changed = True
        else:
            new_lines.append(line)

    if not changed:
        return SubTaskResult(success=True, message="/etc/fstab already configured (no active swap lines)")

    new_content = "\n".join(new_lines) + "\n"

    # 3. Write Back (includes Backup automatically via write_file)
    res_write = write_file(task, fstab_path, new_content)

    if res_write.failed:
        return SubTaskResult(success=False, message=f"Failed to update fstab: {res_write.result}")

    return SubTaskResult(success=True, message="/etc/fstab updated (swap commented)")


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
            status=TaskStatus.CHANGED,
            message="OS Prepared: Modules loaded, Sysctl applied, Swap disabled."
        )
    )
