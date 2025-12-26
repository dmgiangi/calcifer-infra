from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks.files import ensure_line_in_file
from tasks.utils import run_cmd


# --- SUB-STEPS ---

@automated_substep("Verify/Set System Hostname")
def _ensure_hostname(task: Task, target_name: str) -> SubTaskResult:
    """
    Checks the current hostname and updates it using hostnamectl if different.
    """
    # 1. Check current hostname
    res = run_cmd(task, "hostname")
    if res.failed:
        return SubTaskResult(success=False, message="Failed to retrieve hostname")

    current_name = res.result.strip()

    if current_name == target_name:
        return SubTaskResult(success=True, message=f"Hostname already set to '{target_name}'")

    # 2. Set new hostname
    # We use sudo assuming the user has permissions
    set_cmd = f"sudo hostnamectl set-hostname {target_name}"
    res_set = run_cmd(task, set_cmd)

    if res_set.failed:
        return SubTaskResult(success=False, message=f"Failed to set hostname: {res_set.result}")

    return SubTaskResult(success=True, message=f"Hostname changed: {current_name} -> {target_name}")


@automated_substep("Configure /etc/hosts (127.0.0.1)")
def _ensure_localhost_entry(task: Task) -> SubTaskResult:
    """
    Ensures '127.0.0.1 localhost' exists using Python logic.
    """
    # Vogliamo assicurarci che ci sia "127.0.0.1 localhost"
    # Usiamo una regex per trovare se c'è già una definizione per 127.0.0.1
    # Se c'è, la sostituiamo/aggiorniamo o controlliamo se localhost è presente.
    # Per semplicità, e come da specifica ansible: ensure line exists.

    target_line = "127.0.0.1 localhost"
    # Cerchiamo riga che inizia con 127.0.0.1
    regex = r"^127\.0\.0\.1\s+localhost"

    res = ensure_line_in_file(task, "/etc/hosts", target_line, match_regex=regex)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to update /etc/hosts")

    msg = "Localhost entry updated" if res.changed else "Localhost entry present"
    return SubTaskResult(success=True, message=msg)


@automated_substep("Configure /etc/hosts (127.0.1.1)")
def _ensure_resolution_entry(task: Task, target_name: str) -> SubTaskResult:
    """
    Ensures '127.0.1.1 <hostname>' exists, replacing old entries.
    """
    target_line = f"127.0.1.1 {target_name}"
    # Regex: Qualsiasi riga che inizia con 127.0.1.1
    regex = r"^127\.0\.1\.1\s+"

    res = ensure_line_in_file(task, "/etc/hosts", target_line, match_regex=regex)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to update resolution IP")

    msg = f"Resolution entry set to {target_name}" if res.changed else "Resolution entry correct"
    return SubTaskResult(success=True, message=msg)


# --- MAIN TASK ---

@automated_step("Configure System Hostname")
def set_hostname_and_hosts(task: Task) -> Result:
    """
    Sets the system hostname to match the inventory name and updates /etc/hosts.
    """
    # The target hostname is the name defined in hosts.yaml
    target_hostname = task.host.name

    # 1. Set System Hostname
    step_host = _ensure_hostname(task, target_hostname)
    if not step_host.success:
        return Result(host=task.host, failed=True, result=StandardResult(TaskStatus.FAILED, step_host.message))

    # 2. Fix Localhost
    step_lo = _ensure_localhost_entry(task)
    if not step_lo.success:
        return Result(host=task.host, failed=True, result=StandardResult(TaskStatus.FAILED, step_lo.message))

    # 3. Fix Resolution IP
    step_res = _ensure_resolution_entry(task, target_hostname)
    if not step_res.success:
        return Result(host=task.host, failed=True, result=StandardResult(TaskStatus.FAILED, step_res.message))

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.CHANGED if "changed" in step_host.message or "Updated" in step_res.message else TaskStatus.OK,
            message=f"Hostname set to {target_hostname} & /etc/hosts updated"
        )
    )
