# 🔥 Calcifer Infrastructure Manager

Calcifer is a CLI automation tool designed to provision, manage, and tear down Kubernetes clusters. It is built on top
of **Pyinfra** for hybrid orchestration (Local + SSH) and **Typer** for the CLI interface. The core architecture relies
on a modular task system that ensures idempotence and reproducibility.

## 🚀 Key Features

* **Hybrid Orchestration**: Built on Pyinfra, Calcifer seamlessly manages tasks on the local machine (via subprocess)
  and remote nodes (via SSH).
* **Modern CLI Interface**: A clean, user-friendly CLI powered by Typer and Rich, providing clear feedback, status
  spinners, and beautiful output.
* **Idempotent Kubernetes Provisioning**: Safely re-run provisioning tasks. The system uses Kubeadm for initialization
  and Flannel for the CNI.
* **GitOps Ready**: Automatically bootstraps FluxCD, connecting your cluster to a Git repository for declarative,
  version-controlled management.
* **Secure by Design**: Features include atomic file writes to prevent corruption, hash-checking for idempotency, and
  automatic cleanup of sensitive files (like SSH keys) from remote hosts after use.

## 🏛️ Architecture

Calcifer uses a deploy-based architecture where workflows are defined as sequences of atomic tasks. Each deploy function
orchestrates multiple tasks that run on specific host groups (like `local_machine` or `k8s_control_plane`).

```python
# deploy.py (Simplified)
@deploy("Initialize Cluster")
def deploy_init():
  check_internet_access()
  set_hostname_and_hosts()
  prepare_k8s_node()
  install_containerd()
  install_kubernetes_tools()
  init_control_plane()
  setup_fluxcd()
```

## 📋 Prerequisites

To use Calcifer, you need the following installed on your **local management machine**:

* Python 3.9+
* SSH client and network access to the remote nodes.
* Kubectl: For post-init cluster operations.

## ⚙️ Installation & Configuration

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/calcifer-infra.git
   cd calcifer-infra
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the Inventory:**
   Edit `inventory/hosts.yaml` to define your target nodes.
   ```yaml
   # inventory/hosts.yaml
   cp-node-01:
     hostname: 192.168.1.100  # Use the actual IP address
     groups:
       - k8s_control_plane

   localhost:
     hostname: 127.0.0.1
     groups:
       - local_machine
   ```

4. **Configure the Cluster:**
   Edit `cluster_config.yaml` to define cluster-wide parameters and GitOps configuration.
   ```yaml
   # cluster_config.yaml
   environment: prod

   k8s:
     version: "1.29"
     flux:
       enabled: true
       github_url: "ssh://git@github.com/your-username/your-gitops-repo.git"
       branch: "main"
       cluster_path: "clusters/production"
   ```

## 🎮 Usage Workflow

Calcifer's CLI provides semantic commands to guide you through the infrastructure lifecycle.

### Step 1: 🚀 Initialize the Cluster

This is the main provisioning command. It performs the following sequence on the remote nodes:

* Prepares the OS (disables swap, loads kernel modules).
* Installs `containerd`.
* Installs `kubeadm`, `kubelet`, and `kubectl`.
* Runs `kubeadm init` to create the control plane.
* Fetches the `admin.conf` to your local machine.
* Installs the Flannel CNI.
* Bootstraps FluxCD if enabled.

```bash
python main.py init
```

## 📂 Project Structure

```text
.
├── core/               # Core orchestration logic
│   ├── models.py       # Standardized result objects (OK, FAILED, etc.)
│   ├── settings.py     # Configuration loader (YAML + Env Vars)
│   └── state.py        # Runtime configuration state
├── tasks/              # Atomic, idempotent task functions
├── inventory/          # Pyinfra inventory files
│   ├── hosts.yaml      # Define your servers here
│   └── groups.yaml     # Define host groups
├── utils/              # Helper utilities like the file logger
├── main.py             # Typer CLI application entrypoint
├── deploy.py           # Deploy workflows definitions
├── cluster_config.yaml # Main configuration for your cluster
├── requirements.txt    # Python dependencies
└── calcifer.log        # Detailed log file for debugging
```
