from nornir.core.task import Task, Result
from tasks import dependencies, authentication
from utils.logger import logger


def configure_arc_workflow(task: Task) -> Result:
    """
    Orchestrator workflow for Azure Arc configuration with Rich Logging.
    """

    # --- INIZIO WORKFLOW (Livello Top) ---
    with logger.workflow(f"Azure Arc Configuration on {task.host.name}"):

        # --- STEP 1: Install System Dependencies ---
        with logger.task("1. Install System Dependencies"):
            res = task.run(
                task=dependencies.install_dependencies,
                name="install_deps"
            )
            # Controllo esito
            if res.failed:
                # Il context manager __exit__ catturerà l'eccezione se Nornir la solleva,
                # ma se Nornir sopprime l'errore, lo logghiamo noi:
                logger.log_step("error", "Dependency installation failed")
                return Result(host=task.host, failed=True, result="Workflow Aborted at Step 1")

            logger.log_step("success", "Azure CLI and tools installed")

        # --- STEP 2: Verify Authentication ---
        with logger.task("2. Verify Authentication"):
            res = task.run(
                task=authentication.check_login_status,
                name="check_auth"
            )
            if res.failed:
                logger.log_step("error", "User is not authenticated via CLI")
                return Result(host=task.host, failed=True, result="Workflow Aborted at Step 2")

            logger.log_step("success", "Authentication verified")

        # # --- STEP 3: Pre-flight Connection Check ---
        # is_connected = False
        # with logger.task("3. Check Connection Status"):
        #     check_result = task.run(
        #         task=arc_connectivity.check_connection_status,
        #         name="check_conn"
        #     )
        #
        #     # Estrazione risultato
        #     is_connected = check_result[0].result
        #
        #     if is_connected:
        #         logger.log_step("info", "Cluster is ALREADY connected to Arc")
        #     else:
        #         logger.log_step("info", "Cluster is NOT connected. Proceeding to onboard.")
        #
        # # --- Conditional Logic: Connect only if needed ---
        # if not is_connected:
        #
        #     # --- STEP 4: Setup Providers ---
        #     with logger.task("4. Setup Providers & Extensions"):
        #         res = task.run(
        #             task=arc_connectivity.setup_providers,
        #             name="setup_providers"
        #         )
        #         if res.failed:
        #             logger.log_step("error", "Failed to register resource providers")
        #             return Result(host=task.host, failed=True, result="Aborted at Step 4")
        #
        #         logger.log_step("success", "Resource providers registered")
        #
        #     # --- STEP 5: Connect Cluster to Arc ---
        #     with logger.task("5. Connect Cluster to Arc"):
        #         logger.log_step("warning", "Starting connection... this might take a minute")
        #         res = task.run(
        #             task=arc_connectivity.connect_cluster,
        #             name="connect_cluster"
        #         )
        #         if res.failed:
        #             logger.log_step("error", "Onboarding command failed")
        #             return Result(host=task.host, failed=True, result="Aborted at Step 5")
        #
        #         logger.log_step("success", "Cluster successfully connected to Azure Arc")
        #
        # else:
        #     # --- SKIP LOGIC ---
        #     # Non apriamo un task context completo, ma logghiamo lo skip
        #     logger.log_step("skip", "Skipping Steps 4 & 5 (Already Connected)")
        #
        # # --- STEP 6: Enable Features ---
        # with logger.task("6. Enable Arc Features"):
        #     res = task.run(
        #         task=features.enable_features,
        #         name="enable_features"
        #     )
        #     if res.failed:
        #         logger.log_step("warning", "Could not enable all features (Workload Identity)")
        #     else:
        #         logger.log_step("success", "Features enabled successfully")

    return Result(host=task.host, result="Arc Configuration Workflow Completed")