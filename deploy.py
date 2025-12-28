from pyinfra.api import deploy

from tasks.azure_arc_onboarding import install_arc_agent
from tasks.azure_auth_setup import ensure_azure_login
from tasks.azure_cli_setup import ensure_azure_cli
from tasks.cri_containerd_setup import install_containerd
from tasks.gitops_flux_setup import setup_fluxcd
from tasks.k8s_control_plane_init import init_control_plane
from tasks.k8s_node_preparation import prepare_k8s_node
from tasks.k8s_tools_installation import install_kubernetes_tools
from tasks.network_connectivity import check_internet_access
from tasks.os_hostname_setup import set_hostname_and_hosts


@deploy("Initialize Cluster")
def deploy_init():
    check_internet_access()
    set_hostname_and_hosts()
    prepare_k8s_node()
    install_containerd()
    install_kubernetes_tools()
    init_control_plane()
    setup_fluxcd()


@deploy("Azure Arc Onboarding")
def deploy_arc():
    check_internet_access()
    ensure_azure_cli()
    ensure_azure_login()
    install_arc_agent()
