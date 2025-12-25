from typing import Dict, List, Callable, Any

from tasks.authentication import ensure_azure_login
from tasks.connectivity import check_internet_access
from tasks.system import set_hostname_and_hosts

# Define type for clarity
TaskChain = List[Callable[..., Any]]

# Define execution order of groups (Deployment Strategy)
GROUP_EXECUTION_ORDER = ["local_machine", "k8s_control_plane", "k8s_worker"]

# GOAL x GROUP Matrix
TASK_REGISTRY: Dict[str, Dict[str, TaskChain]] = {

    # --- GOAL: CHECK ---
    "CHECK": {
        "local_machine": [
            check_internet_access,
            ensure_azure_login
        ],
        "k8s_control_plane": [
            check_internet_access
        ],
        "k8s_worker": [
            check_internet_access
        ]
    },

    # --- GOAL: INIT ---
    "INIT": {
        "local_machine": [
        ],
        "k8s_control_plane": [
            set_hostname_and_hosts
        ],
        "k8s_worker": [

        ]
    },

    "DESTROY": {
        "local_machine": [
        ],
        "k8s_control_plane": [
        ],
        "k8s_worker": [

        ]
    }
}
