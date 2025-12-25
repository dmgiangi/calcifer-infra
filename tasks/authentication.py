import os
from dotenv import load_dotenv
from nornir.core.task import Task, Result

from tasks.utils import run_local
from utils.logger import logger

load_dotenv()
AZ_SUB = os.getenv("AZURE_SUBSCRIPTION_ID")


def check_login_status(task: Task) -> Result:
    """
    Verifies if the host is already authenticated with Azure CLI using Rich logging.
    """

    # --- Step 1: Verification ---
    # Usiamo il logger per dare feedback immediato su cosa sta succedendo
    logger.log_step("info", "Verifying active Azure CLI session...")

    verify_cmd = task.run(task=run_local, command="az account show")

    if verify_cmd.failed:
        msg = (
            "Host is NOT authenticated. "
            "Run 'az login --use-device-code' on the node manually."
        )
        # Logghiamo l'errore visivamente
        logger.log_step("error", msg)

        return Result(
            host=task.host,
            result=msg,
            failed=True
        )

    # Se siamo qui, il login c'è
    logger.log_step("success", "Active session found")

    # --- Step 2: Set Context ---
    if not AZ_SUB:
        msg = "AZURE_SUBSCRIPTION_ID is missing in .env file."
        logger.log_step("error", msg)
        return Result(host=task.host, result=msg, failed=True)

    logger.log_step("info", f"Setting subscription context to: {AZ_SUB}")

    set_sub_cmd = task.run(
        task=run_local,
        command=f"az account set --subscription {AZ_SUB}"
    )

    if set_sub_cmd.failed:
        error_msg = f"Failed to set subscription: {set_sub_cmd.result}"
        logger.log_step("error", error_msg)
        return Result(
            host=task.host,
            result=error_msg,
            failed=True
        )

    # Log finale di successo per questa sotto-operazione
    logger.log_step("success", "Subscription context set correctly")

    return Result(
        host=task.host,
        result=f"Success: Authenticated and Subscription set to {AZ_SUB}"
    )