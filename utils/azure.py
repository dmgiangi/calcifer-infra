import json

from nornir.core.task import Task, Result

from utils.linux import _run_command, command_exists


def az_account_show(task: Task) -> Result:
    """Shows current Azure account details."""
    return _run_command(task, "az account show -o json")


def az_account_set(task: Task, subscription_id: str) -> Result:
    """Sets the active Azure subscription."""
    res = _run_command(task, f"az account set --subscription {subscription_id}")

    # Verification
    if not res.failed:
        show_res = az_account_show(task)
        if not show_res.failed:
            try:
                data = json.loads(show_res.result)
                if data.get("id") != subscription_id:
                    return Result(host=task.host, failed=True,
                                  result=f"Verification failed: Subscription ID mismatch. Expected {subscription_id}, got {data.get('id')}")
            except json.JSONDecodeError:
                return Result(host=task.host, failed=True,
                              result="Verification failed: Could not parse az account show output")

    return res


def az_extension_list(task: Task) -> Result:
    """Lists installed Azure extensions."""
    return _run_command(task, "az extension list -o json")


def az_provider_list(task: Task, query: str = None) -> Result:
    """Lists Azure providers."""
    cmd = "az provider list -o json"
    if query:
        cmd += f" --query \"{query}\""
    return _run_command(task, cmd)


def az_connectedk8s_show(task: Task, resource_group: str, cluster_name: str) -> Result:
    """Shows details of an Azure Arc connected cluster."""
    cmd = f"az connectedk8s show --name {cluster_name} --resource-group {resource_group} -o json"
    # This command might fail if the cluster is not found, which is valid for status checks.
    # We let the caller handle the failure/exit code interpretation.
    return _run_command(task, cmd)


def az_connectedk8s_connect(
        task: Task,
        resource_group: str,
        cluster_name: str,
        location: str,
        kubeconfig_path: str
) -> Result:
    """Connects a K8s cluster to Azure Arc."""
    # We need to inject KUBECONFIG ENV var. 
    # _run_command supports "env VAR=val cmd" via generic shell execution if strictly string.
    # But for robustness with local/remote platform, best to use export syntax.
    cmd = (
        f"export KUBECONFIG={kubeconfig_path} && "
        f"az connectedk8s connect "
        f"--name {cluster_name} "
        f"--resource-group {resource_group} "
        f"--location {location} "
        f"--yes "
        f"--correlation-id calcifer-automation"
    )
    return _run_command(task, cmd)


def az_is_installed(task: Task) -> bool:
    """Checks if az CLI is installed."""
    return command_exists(task, "az")
