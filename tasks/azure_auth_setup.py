import json

from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import fail
from utils.azure import (
    az_is_installed,
    az_account_show,
    az_account_set,
    az_extension_list,
    az_provider_list
)


@automated_substep("Check Execution Environment")
def _check_environment(task: Task) -> SubTaskResult:
    if task.host.platform != "linux_local" and "local_machine" not in task.host.groups:
        return SubTaskResult(success=True, message="Remote Target (Skipping logic)", data="SKIP")
    return SubTaskResult(success=True, message="Local Execution Confirmed")


@automated_substep("Check Azure CLI Binary")
def _check_cli_installed(task: Task) -> SubTaskResult:
    if not az_is_installed(task):
        return SubTaskResult(success=False, message="Binary 'az' not found")
    return SubTaskResult(success=True, message="CLI Found")


@automated_substep("Check Login Session")
def _check_active_session(task: Task) -> SubTaskResult:
    # Here we return session data in 'data' to use it later
    res = az_account_show(task)
    if res.failed:
        return SubTaskResult(success=False, message="No active session (az login required)")

    try:
        data = json.loads(res.result)
        return SubTaskResult(success=True, message="Session Active", data=data)
    except Exception as e:
        return SubTaskResult(success=False, exception=e, message="JSON parse error on auth data")


@automated_substep("Verify Subscription Context")
def _verify_subscription(task: Task, current_sub_id: str) -> SubTaskResult:
    # Retrieve target from injected config
    config = task.host.get("app_config")
    # Note: Assuming config is a dict (thanks to asdict in engine.py)
    if not config or "azure" not in config:
        return SubTaskResult(success=False, message="Missing app_config in inventory")

    target_sub = config["azure"]["subscription_id"]

    if current_sub_id == target_sub:
        return SubTaskResult(success=True, message=f"Context Correct ({target_sub})")

    # Attempt to switch
    res = az_account_set(task, target_sub)
    if res.failed:
        return SubTaskResult(success=False, message=f"Failed to switch to {target_sub}")

    return SubTaskResult(success=True, message=f"Context Switched to {target_sub}")


@automated_substep("Check Arc Extensions")
def _check_extensions(task: Task) -> SubTaskResult:
    required = ["connectedk8s"]

    res = az_extension_list(task)
    if res.failed:
        return SubTaskResult(success=False, message="Failed to list extensions")

    installed = [x["name"] for x in json.loads(res.result)]
    missing = [x for x in required if x not in installed]

    if missing:
        return SubTaskResult(success=False, message=f"Missing extensions: {missing}")

    return SubTaskResult(success=True, message="Extensions OK")


@automated_substep("Check Resource Providers")
def _check_providers(task: Task) -> SubTaskResult:
    required = [
        "Microsoft.Kubernetes",
        "Microsoft.KubernetesConfiguration",
        "Microsoft.ExtendedLocation"
    ]

    # original query: "[?registrationState=='Registered'].namespace"
    res = az_provider_list(task, query="[?registrationState=='Registered'].namespace")

    if res.failed:
        return SubTaskResult(success=False, message="Failed to list providers")

    registered = json.loads(res.result)
    missing = [x for x in required if x not in registered]

    if missing:
        return SubTaskResult(success=False, message=f"Missing providers: {missing}")

    return SubTaskResult(success=True, message="Providers OK")


# --- MAIN TASK (Aggregator) ---

@automated_step("Ensure Azure Login & Prerequisites")
def ensure_azure_login(task: Task) -> Result:
    """
    Main Orchestrator Task for Authentication.
    Aggregates atomic sub-steps defined above.
    """

    # 1. Environment Guard
    step_env = _check_environment(task)
    if not step_env.success: return fail(task, step_env)
    if step_env.data == "SKIP":
        return Result(host=task.host, result=StandardResult(TaskStatus.OK, "Skipped (Remote Host)"))

    # 2. CLI Check
    step_cli = _check_cli_installed(task)
    if not step_cli.success: return fail(task, step_cli)

    # 3. Session Check
    step_login = _check_active_session(task)
    if not step_login.success: return fail(task, step_login)

    # Extract current ID from data passed by subtask
    current_sub_id = step_login.data.get("id")

    # 4. Subscription Check
    step_sub = _verify_subscription(task, current_sub_id)
    if not step_sub.success: return fail(task, step_sub)

    # 5. Extensions Check
    step_ext = _check_extensions(task)
    if not step_ext.success: return fail(task, step_ext)

    # 6. Providers Check
    step_prov = _check_providers(task)
    if not step_prov.success: return fail(task, step_prov)

    # --- SUCCESS ---
    # Build a nice summary message
    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.OK,
            message="Ready | CLI, Auth, Sub, Exts & Providers verified."
        )
    )