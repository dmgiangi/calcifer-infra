import json
import os
import subprocess
from pathlib import Path

from nornir.core.task import Task, Result

from core.decorators import automated_step, automated_substep
from core.models import TaskStatus, StandardResult, SubTaskResult
from tasks import fail


# --- SUB-STEPS ---

@automated_substep("Check Existing Arc Connection (Local)")
def _check_arc_status(task: Task, resource_group: str, cluster_name: str) -> SubTaskResult:
    """
    Verifica se la risorsa Arc esiste già su Azure usando la CLI locale.
    """
    cmd = [
        "az", "connectedk8s", "show",
        "--name", cluster_name,
        "--resource-group", resource_group,
        "-o", "json"
    ]

    try:
        # Esecuzione Locale diretta
        proc = subprocess.run(cmd, capture_output=True, text=True)

        if proc.returncode != 0:
            # Se fallisce, assumiamo che non sia connesso
            return SubTaskResult(success=True, message="Cluster not connected yet", data=False)

        data = json.loads(proc.stdout)
        state = data.get("connectivityStatus", "Unknown")
        return SubTaskResult(success=True, message=f"Already connected (Status: {state})", data=True)

    except Exception as e:
        # Se az cli non è installata o errore grave
        return SubTaskResult(success=False, message=f"Local Check Failed: {str(e)}")


@automated_substep("Connect Cluster to Azure Arc (Local)")
def _connect_cluster(task: Task, config: dict, cluster_name: str, kubeconfig_path: str) -> SubTaskResult:
    """
    Esegue 'az connectedk8s connect' LOCALLY iniettando il KUBECONFIG.
    """
    if not Path(kubeconfig_path).exists():
        return SubTaskResult(success=False, message=f"Local Kubeconfig not found at {kubeconfig_path}")

    azure_conf = config["azure"]
    rg = azure_conf["resource_group"]
    location = azure_conf["location"]

    # Preparazione Environment con KUBECONFIG
    env = os.environ.copy()
    env["KUBECONFIG"] = str(Path(kubeconfig_path).absolute())

    # Comando
    cmd = [
        "az", "connectedk8s", "connect",
        "--name", cluster_name,
        "--resource-group", rg,
        "--location", location,
        "--yes",  # Non-interactive
        "--correlation-id", "calcifer-automation"
    ]

    try:
        # Esecuzione con timeout lungo (Arc ci mette un po' a installare gli agenti)
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)

        if proc.returncode != 0:
            return SubTaskResult(success=False, message=f"Arc connection failed: {proc.stderr}")

    except Exception as e:
        return SubTaskResult(success=False, message=f"Local Execution Error: {e}")

    return SubTaskResult(success=True, message="Arc Agents installed & connected")


# --- MAIN TASK ---

@automated_step("Onboard to Azure Arc")
def install_arc_agent(task: Task) -> Result:
    """
    Connects the Kubernetes cluster to Azure Arc management executing commands LOCALLY.
    Requires 'init' to be completed (kubeconfig must exist).
    """
    config = task.host.get("app_config")

    # Usiamo il nome dell'host remoto (inventory hostname) come nome risorsa Azure
    cluster_name = task.host.name
    resource_group = config["azure"]["resource_group"]

    # Recuperiamo il path del kubeconfig dai settings (come definito nel punto precedente)
    # Fallback se non ancora aggiunto ai settings dataclass: uso hardcoded
    kube_path = config["k8s"].get("local_kubeconfig_path", "inventory/kubeconfig_admin.yaml")

    # 1. Check Status (Locale)
    s1 = _check_arc_status(task, resource_group, cluster_name)
    if not s1.success: return fail(task, s1)

    if s1.data is True:
        return Result(
            host=task.host,
            result=StandardResult(TaskStatus.OK, s1.message)
        )

    # 2. Connect (Locale con Kubeconfig Injection)
    s2 = _connect_cluster(task, config, cluster_name, kube_path)
    if not s2.success: return fail(task, s2)

    return Result(
        host=task.host,
        result=StandardResult(TaskStatus.CHANGED, "Cluster successfully projected to Azure Arc")
    )
