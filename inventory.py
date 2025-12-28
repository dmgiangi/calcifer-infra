import yaml

from core.settings import load_settings

# Load App Configuration
app_config = load_settings()

# Load Hosts from YAML
try:
    with open("inventory/hosts.yaml", "r") as f:
        hosts_yaml = yaml.safe_load(f) or {}
except FileNotFoundError:
    hosts_yaml = {}

# Define Groups for Pyinfra
k8s_control_plane = []
local_machine = []
k8s_worker = []

for name, host_data in hosts_yaml.items():
    groups = host_data.get("groups", [])
    hostname = host_data.get("hostname")
    user = host_data.get("username")

    # Common Data
    data = {
        "ssh_user": user,
        "app_config": app_config,
    }

    # Map to Pyinfra connector
    if "local_machine" in groups:
        # Use @local connector for the machine running pyinfra
        local_machine.append(("@local", data))
    elif "k8s_control_plane" in groups:
        k8s_control_plane.append((hostname, data))
    elif "k8s_worker" in groups:
        k8s_worker.append((hostname, data))
