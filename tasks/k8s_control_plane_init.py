from pyinfra import host
from pyinfra.operations import server, files


def init_control_plane():
    """
    Initializes K8s CP and configures it locally using paths from Settings.
    """
    config = host.data.app_config.k8s
    pod_cidr = config.get("pod_network_cidr", "10.244.0.0/16")
    cni_url = config.get("cni_manifest_url")
    local_kube_path = config.get("local_kubeconfig_path")

    node_name = host.data.get("hostname") or host.name

    # 1. Generate Config
    config_content = f"""
apiVersion: kubeadm.k8s.io/v1beta3
kind: InitConfiguration
nodeRegistration:
  name: "{node_name}"
  taints: []
---
apiVersion: kubeadm.k8s.io/v1beta3
kind: ClusterConfiguration
networking:
  podSubnet: "{pod_cidr}"
"""
    files.put(
        name="Generate Kubeadm Config",
        dest="/tmp/kubeadm-config.yaml",
        content=config_content,
    )

    # 2. Init
    server.shell(
        name="Run Kubeadm Init",
        commands=["kubeadm init --config /tmp/kubeadm-config.yaml --upload-certs"],
    )

    # 3. Setup User Kubeconfig (Remote)
    server.shell(
        name="Setup Remote User Kubeconfig",
        commands=[
            "mkdir -p $HOME/.kube",
            "cp -i /etc/kubernetes/admin.conf $HOME/.kube/config",
            "chown $(id -u):$(id -g) $HOME/.kube/config",
        ],
    )

    # 4. Fetch Config to Local Controller
    files.get(
        name="Fetch Admin Kubeconfig to Local Machine",
        src="/etc/kubernetes/admin.conf",
        dest=local_kube_path,
    )

    # 5. Install CNI
    server.shell(
        name="Install CNI Plugin",
        commands=[f"export KUBECONFIG=/etc/kubernetes/admin.conf && kubectl apply -f {cni_url}"],
    )

    # 6. Untaint Node
    server.shell(
        name="Untaint Control Plane Node",
        commands=[
            f"export KUBECONFIG=/etc/kubernetes/admin.conf && kubectl taint nodes {node_name} node-role.kubernetes.io/control-plane:NoSchedule-"],
    )