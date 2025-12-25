from nornir.core.task import Task, Result
from tasks.utils import run_local
from core.models import TaskStatus, StandardResult


def ensure_azure_login(task: Task) -> Result:
    """
    Verifies authentication and sets the correct subscription context.
    Dependency: Requires 'app_config' injected in task.host.
    """

    # 1. Retrieve Configuration (Dependency Injection)
    config = task.host.get("app_config")
    if not config or "azure" not in config:
        return Result(
            host=task.host,
            failed=True,
            result=StandardResult(
                status=TaskStatus.FAILED,
                message="Missing 'app_config' or 'azure' settings in host inventory."
            )
        )

    target_sub_id = config["azure"]["subscription_id"]

    # 2. Check Session State
    verify_cmd = task.run(task=run_local, command="az account show")

    if verify_cmd.failed:
        # If verification fails, it's a blocking failure for the INIT goal
        return Result(
            host=task.host,
            failed=True,  # Nornir generic failure
            result=StandardResult(
                status=TaskStatus.FAILED,
                message="Host is not authenticated. Manual 'az login' required."
            )
        )

    # 3. Check Subscription Context
    # We parse the JSON output (in a real scenario) or just grep.
    # For simplicity, we assume if 'az account show' works, we check the ID inside or set it.

    # Let's try to set it directly to be sure (Idempotent action)
    set_sub_cmd = task.run(
        task=run_local,
        command=f"az account set --subscription {target_sub_id}"
    )

    if set_sub_cmd.failed:
        # This is a nuance: Login is OK, but Subscription is wrong/missing
        return Result(
            host=task.host,
            failed=True,
            result=StandardResult(
                status=TaskStatus.FAILED,
                message=f"Logged in, but failed to set subscription {target_sub_id}. Check permissions."
            )
        )

    return Result(
        host=task.host,
        result=StandardResult(
            status=TaskStatus.OK,
            message=f"Authenticated and context set to {target_sub_id}"
        )
    )