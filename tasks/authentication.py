from nornir.core.task import Task, Result
from tasks.utils import run_local
from utils.logger import logger


def check_login_status(task: Task) -> Result:
    """
    Verifies if the host is already authenticated with Azure CLI using Rich logging.
    """

    # --- Step 1: Verification ---
    logger.log_step("info", "Verifying active Azure CLI session...")

    # Verify authentication command
    verify_cmd = task.run(task=run_local, command="az account show")

    if verify_cmd.failed:
        msg = (
            "Host is NOT authenticated. "
            "Run 'az login --use-device-code' on the node manually."
        )
        logger.log_step("error", msg)
        return Result(host=task.host, result=msg, failed=True)

    logger.log_step("success", "Active session found")

    # --- Step 2: Set Context using Injected Config ---
    # Retrieve configuration from host data (injected in runner.py)
    app_config = task.host.get("app_config")

    if not app_config:
        msg = "Configuration not found in host data."
        logger.log_step("error", msg)
        return Result(host=task.host, result=msg, failed=True)

    # Access the subscription ID safely
    az_sub = app_config["azure"]["subscription_id"]

    logger.log_step("info", f"Setting subscription context to: {az_sub}")

    set_sub_cmd = task.run(
        task=run_local,
        command=f"az account set --subscription {az_sub}"
    )

    if set_sub_cmd.failed:
        error_msg = f"Failed to set subscription: {set_sub_cmd.result}"
        logger.log_step("error", error_msg)
        return Result(host=task.host, result=error_msg, failed=True)

    logger.log_step("success", "Subscription context set correctly")

    return Result(
        host=task.host,
        result=f"Success: Authenticated and Subscription set to {az_sub}"
    )