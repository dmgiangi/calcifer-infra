from typing import Dict, List, Callable, Any

from tasks.arc import install_arc_agent
from tasks.authentication import ensure_azure_login
from tasks.connectivity import check_internet_access
from tasks.containerd import install_containerd
from tasks.control_plane import init_control_plane
from tasks.dependencies import ensure_azure_cli
from tasks.facts import gather_system_facts
from tasks.flux import setup_fluxcd
from tasks.k8s_prep import prepare_k8s_node
from tasks.kubetools import install_kubernetes_tools
from tasks.system import set_hostname_and_hosts

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
