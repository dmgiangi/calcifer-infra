from typing import Dict, List, Callable, Any

from tasks.authentication import ensure_azure_login
from tasks.containerd import install_containerd
from tasks.control_plane import init_control_plane
from tasks.dependencies import ensure_azure_cli
from tasks.flux import setup_fluxcd
from tasks.k8s_prep import prepare_k8s_node
from tasks.kubetools import install_kubernetes_tools
from tasks.system import set_hostname_and_hosts

# Define type for clarity
TaskChain = List[Callable[..., Any]]

# Define execution order of groups (Deployment Strategy)
GROUP_EXECUTION_ORDER = ["local_machine", "k8s_control_plane", "k8s_worker"]

# GOAL x GROUP Matrix
TASK_REGISTRY: Dict[str, Dict[str, TaskChain]] = {

    # --- GOAL: CONNECT ---
    "CONNECT": {
        "local_machine": [
            ensure_azure_login
        ],
        "k8s_control_plane": [
        ],
        "k8s_worker": [
        ]
    },

    # --- GOAL: INIT ---
    "INIT": {
        "local_machine": [
            ensure_azure_cli,
            ensure_azure_login
        ],
        "k8s_control_plane": [
            set_hostname_and_hosts,
            prepare_k8s_node,
            install_containerd,
            install_kubernetes_tools,
            init_control_plane,
            setup_fluxcd
        ],
        "k8s_worker": [
            set_hostname_and_hosts,
            prepare_k8s_node,
            install_containerd,
            install_kubernetes_tools
        ]
    },

    "DESTROY": {
        "local_machine": [
            ensure_azure_login
        ],
        "k8s_control_plane": [
        ],
        "k8s_worker": [

        ]
    }
}
