from typing import Dict, List, Callable, Any

from tasks.azure_arc_onboarding import install_arc_agent
from tasks.azure_auth_setup import ensure_azure_login
from tasks.azure_cli_setup import ensure_azure_cli
from tasks.cri_containerd_setup import install_containerd
from tasks.gitops_flux_setup import setup_fluxcd
from tasks.k8s_control_plane_init import init_control_plane
from tasks.k8s_node_preparation import prepare_k8s_node
from tasks.k8s_tools_installation import install_kubernetes_tools
from tasks.network_connectivity import check_internet_access
from tasks.os_facts_gathering import gather_system_facts
from tasks.os_hostname_setup import set_hostname_and_hosts

TaskChain = List[Callable[..., Any]]

GROUP_EXECUTION_ORDER = ["local_machine", "k8s_control_plane", "k8s_worker"]

TASK_REGISTRY: Dict[str, Dict[str, TaskChain]] = {

    # --- GOAL: INIT (Cluster Provisioning) ---
    "INIT": {
        "local_machine": [
            check_internet_access,
            gather_system_facts,
            ensure_azure_cli,
            ensure_azure_login
        ],
        "k8s_control_plane": [
            check_internet_access,
            gather_system_facts,
            set_hostname_and_hosts,
            # --- Provisioning ---
            prepare_k8s_node,
            install_containerd,
            install_kubernetes_tools,
            # --- K8s & GitOps ---
            init_control_plane,
            setup_fluxcd
        ],
        "k8s_worker": [
            check_internet_access,
            gather_system_facts,
            set_hostname_and_hosts,
            prepare_k8s_node,
            install_containerd,
            install_kubernetes_tools,
        ]
    },

    # --- GOAL: ARC (Cloud Projection) ---
    "ARC": {
        "local_machine": [
            check_internet_access,
            gather_system_facts,
            ensure_azure_cli,
            ensure_azure_login,
            install_arc_agent

        ],
        "k8s_control_plane": [
        ],
        "k8s_worker": []
    }
}
