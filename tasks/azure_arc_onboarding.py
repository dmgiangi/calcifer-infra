from pyinfra import host
from pyinfra.operations import server

from utils.logger import log_operation


@log_operation
def install_arc_agent():
    """
    Onboard to Azure Arc.
    """
    config = host.data.app_config.azure
    k8s_conf = host.data.app_config.k8s

    cluster_name = host.data.get("hostname") or host.name
    resource_group = config.resource_group
    location = config.location
    kube_path = k8s_conf.local_kubeconfig_path

    server.shell(
        name="Connect Cluster to Azure Arc",
        commands=[
            f"az connectedk8s connect --name {cluster_name} --resource-group {resource_group} --location {location} --yes"
        ],
        env={
            "KUBECONFIG": kube_path
        }
    )