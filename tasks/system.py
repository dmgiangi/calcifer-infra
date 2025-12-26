from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import run_command, fail, ensure_line_in_file


# --- SUB-STEPS ---

@automated_substep("Verify/Set System Hostname")
def _ensure_hostname(task: Task, target_name: str) -> SubTaskResult:
    # 1. Check
    res = run_command(task, "hostname")
    if res.failed:
        return SubTaskResult(success=False, message="Failed to retrieve hostname")

    current_name = res.result.strip()
    if current_name == target_name:
        return SubTaskResult(success=True, message=f"Hostname already set to '{target_name}'")

    # 2. Set (Using sudo wrapper)
    set_cmd = f"hostnamectl set-hostname {target_name}"
    res_set = run_command(task, set_cmd, sudo=True)

    if res_set.failed:
        return SubTaskResult(success=False, message=f"Failed to set hostname: {res_set.result}")

    return SubTaskResult(success=True, message=f"Hostname changed: {current_name} -> {target_name}")


@automated_substep("Configure /etc/hosts (127.0.0.1)")
def _ensure_localhost_entry(task: Task) -> SubTaskResult:
    """
    Ensures '127.0.0.1 localhost' exists using secure file utility.
    """
    target_line = "127.0.0.1 localhost"
    regex = r"^127\.0\.0\.1\s+localhost"

    res = ensure_line_in_file(task, "/etc/hosts", target_line, match_regex=regex)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to update /etc/hosts")

    msg = "Localhost entry updated" if res.changed else "Localhost entry present"
    return SubTaskResult(success=True, message=msg)


@automated_substep("Configure /etc/hosts (127.0.1.1)")
def _ensure_resolution_entry(task: Task, target_name: str) -> SubTaskResult:
    """
    Ensures '127.0.1.1 <hostname>' exists, replacing old entries safely.
    """
    target_line = f"127.0.1.1 {target_name}"
    regex = r"^127\.0\.1\.1\s+"

    res = ensure_line_in_file(task, "/etc/hosts", target_line, match_regex=regex)

    if res.failed:
        return SubTaskResult(success=False, message="Failed to update resolution IP")

    msg = f"Resolution entry set to {target_name}" if res.changed else "Resolution entry correct"
    return SubTaskResult(success=True, message=msg)


# --- MAIN TASK ---

@automated_step("Configure System Hostname")
def set_hostname_and_hosts(task: Task) -> Result:
    target_hostname = task.host.name

    s1 = _ensure_hostname(task, target_hostname)
    if not s1.success: return fail(task, s1)

    s2 = _ensure_localhost_entry(task)
    if not s2.success: return fail(task, s2)

    s3 = _ensure_resolution_entry(task, target_hostname)
    if not s3.success: return fail(task, s3)

    is_changed = ("changed" in s1.message or s2.message.endswith("updated") or s3.message.startswith(
        "Resolution entry set"))

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.CHANGED if is_changed else TaskStatus.OK,
            message=f"Hostname set to {target_hostname} & /etc/hosts verified"
        )
    )
