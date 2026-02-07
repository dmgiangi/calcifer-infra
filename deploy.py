from pyinfra.api import deploy

from tasks.cri_containerd_setup import install_containerd
from tasks.gitops_flux_setup import setup_fluxcd
from tasks.k8s_control_plane_init import init_control_plane
from tasks.k8s_node_preparation import prepare_k8s_node
from tasks.k8s_tools_installation import install_kubernetes_tools
from tasks.network_connectivity import check_internet_access
from tasks.os_hostname_setup import set_hostname_and_hosts


@deploy("Initialize Kubernetes Cluster")
def deploy_init():
    check_internet_access()
    set_hostname_and_hosts()
    prepare_k8s_node()
    install_containerd()
    install_kubernetes_tools()
    init_control_plane()
    setup_fluxcd()
