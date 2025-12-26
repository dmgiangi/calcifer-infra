from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import fail, run_command


@automated_substep("Read OS Release")
def _get_os_release(task: Task) -> SubTaskResult:
    """Parses /etc/os-release into a dictionary."""
    # Read file
    res = run_command(task, "cat /etc/os-release")
    if res.failed:
        return SubTaskResult(success=False, message="Could not read /etc/os-release")

    data = {}
    for line in res.result.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            # Remove quotes
            data[key] = value.strip('"')

    return SubTaskResult(success=True, message="OS Release parsed", data=data)


@automated_substep("Check CPU Architecture")
def _get_cpu_arch(task: Task) -> SubTaskResult:
    """Gets architecture (amd64/arm64) via dpkg for accurate deb repo mapping."""
    res = run_command(task, "dpkg --print-architecture")
    if res.failed:
        return SubTaskResult(success=False, message="Could not determine architecture")

    arch = res.result.strip()
    return SubTaskResult(success=True, message=f"Architecture: {arch}", data=arch)


@automated_step("Gather System Facts")
def gather_system_facts(task: Task) -> Result:
    """
    Detects OS Distribution, Codename and Architecture.
    Fails if the OS is not supported (Debian/Ubuntu).
    """
    # 1. Get OS Info
    s1 = _get_os_release(task)
    if not s1.success: return fail(task, s1)
    os_data = s1.data

    # 2. Get Arch
    s2 = _get_cpu_arch(task)
    if not s2.success: return fail(task, s2)
    arch = s2.data

    # 3. Compatibility Check (The "Gatekeeper")
    supported_ids = ["ubuntu", "debian"]
    distro_id = os_data.get("ID", "unknown").lower()

    if distro_id not in supported_ids:
        return Result(
            host=task.host,
            failed=True,
            result=StandardResult(
                status=TaskStatus.FAILED,
                message=f"Unsupported OS: {distro_id}. Only {supported_ids} are supported."
            )
        )

    # 4. Save Facts to Host Context
    # This allows other tasks to use them via task.host["os_facts"]
    task.host["os_facts"] = {
        "id": distro_id,
        "codename": os_data.get("VERSION_CODENAME", "unknown"),
        "version_id": os_data.get("VERSION_ID", "unknown"),
        "arch": arch
    }

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.OK,
            message=f"OS Verified: {distro_id} {os_data.get('VERSION_ID')} ({os_data.get('VERSION_CODENAME')}) on {arch}"
        )
    )
