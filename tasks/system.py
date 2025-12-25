from nornir.core.task import Task, Result
from tasks.utils import run_local
from nornir_scrapli.tasks import send_command
from core.models import TaskStatus, StandardResult, SubTaskResult
from core.decorators import automated_step, automated_substep


# --- HELPER: Command Dispatcher (Local vs Remote) ---
def _run_cmd(task: Task, cmd: str):
    """Executes shell command locally or via SSH based on platform."""
    if task.host.platform == "linux_local":
        return task.run(task=run_local, command=cmd)
    else:
        return task.run(task=send_command, command=cmd)


# --- SUB-STEPS ---

@automated_substep("Verify/Set System Hostname")
def _ensure_hostname(task: Task, target_name: str) -> SubTaskResult:
    """
    Checks the current hostname and updates it using hostnamectl if different.
    """
    # 1. Check current hostname
    res = _run_cmd(task, "hostname")
    if res.failed:
        return SubTaskResult(success=False, message="Failed to retrieve hostname")

    current_name = res.result.strip()

    if current_name == target_name:
        return SubTaskResult(success=True, message=f"Hostname already set to '{target_name}'")

    # 2. Set new hostname
    # We use sudo assuming the user has permissions
    set_cmd = f"sudo hostnamectl set-hostname {target_name}"
    res_set = _run_cmd(task, set_cmd)

    if res_set.failed:
        return SubTaskResult(success=False, message=f"Failed to set hostname: {res_set.result}")

    return SubTaskResult(success=True, message=f"Hostname changed: {current_name} -> {target_name}")


@automated_substep("Configure /etc/hosts (127.0.0.1)")
def _ensure_localhost_entry(task: Task) -> SubTaskResult:
    """
    Ensures '127.0.0.1 localhost' exists.
    Equivalent to Ansible lineinfile with state=present.
    """
    # Idempotency check: grep for the exact line
    check_cmd = "grep -q '^127.0.0.1\\s\\+localhost' /etc/hosts"
    res = _run_cmd(task, check_cmd)

    if not res.failed:
        return SubTaskResult(success=True, message="Localhost entry present")

    # If missing, append it
    # We generally don't want to delete existing 127.0.0.1 lines if they have other aliases,
    # but strictly ensuring localhost is present.
    update_cmd = "echo '127.0.0.1 localhost' | sudo tee -a /etc/hosts"
    res_upd = _run_cmd(task, update_cmd)

    if res_upd.failed:
        return SubTaskResult(success=False, message="Failed to append localhost entry")

    return SubTaskResult(success=True, message="Localhost entry added")


@automated_substep("Configure /etc/hosts (127.0.1.1)")
def _ensure_resolution_entry(task: Task, target_name: str) -> SubTaskResult:
    """
    Ensures '127.0.1.1 <hostname>' exists.
    Replaces any existing 127.0.1.1 entry to avoid duplicates.
    """
    # 1. Check if the CORRECT entry already exists
    # grep -q exits with 0 if found, 1 if not
    check_cmd = f"grep -q '^127.0.1.1\\s\\+{target_name}$' /etc/hosts"
    res = _run_cmd(task, check_cmd)

    if not res.failed:
        return SubTaskResult(success=True, message=f"Entry '127.0.1.1 {target_name}' present")

    # 2. Update Logic
    # Strategy: Remove ANY existing 127.0.1.1 line using sed, then append the correct one.
    # This prevents drift (e.g., if hostname changed, we remove the old entry).

    # Step A: Remove old line (if any)
    # || true ensures it doesn't fail if line is missing
    clean_cmd = "sudo sed -i '/^127.0.1.1/d' /etc/hosts"
    _run_cmd(task, clean_cmd)

    # Step B: Append new line
    add_cmd = f"echo '127.0.1.1 {target_name}' | sudo tee -a /etc/hosts"
    res_add = _run_cmd(task, add_cmd)

    if res_add.failed:
        return SubTaskResult(success=False, message="Failed to update /etc/hosts")

    return SubTaskResult(success=True, message=f"Updated 127.0.1.1 to {target_name}")


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