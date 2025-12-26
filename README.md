# 🔥 Calcifer Infrastructure Manager

Calcifer is a CLI automation tool designed to provision, manage, and tear down Kubernetes clusters and Azure Arc
integrations. It is built on top of **Nornir** for hybrid orchestration (Local + SSH) and **Typer** for the CLI
interface. The core architecture relies on a **Matrix Engine** that decouples technical tasks from high-level goals,
ensuring modularity and idempotence.

## 🚀 Key Features

* **Hybrid Orchestration**: Built on Nornir and Scrapli, Calcifer seamlessly manages tasks on the local machine (via
  subprocess) and remote nodes (via SSH).
* **Modern CLI Interface**: A clean, user-friendly CLI powered by Typer and Rich, providing clear feedback, status
  spinners, and beautiful output.
* **Idempotent Kubernetes Provisioning**: Safely re-run provisioning tasks. The system uses Kubeadm for initialization
  and Flannel for the CNI.
* **GitOps Ready**: Automatically bootstraps FluxCD, connecting your cluster to a Git repository for declarative,
  version-controlled management.
* **Agentless Azure Arc Onboarding**: Projects your Kubernetes cluster into Azure Arc without needing to install the
  `az` CLI on the remote cluster nodes. All cloud operations are executed from the local management machine.
* **Secure by Design**: Features include atomic file writes to prevent corruption, hash-checking for idempotency, and
  automatic cleanup of sensitive files (like SSH keys) from remote hosts after use.

## 🏛️ Architecture

Calcifer employs a **Matrix Engine** to orchestrate complex workflows. The logic is defined in `core/registry.py`, which
maps high-level **Goals** (like `INIT` or `ARC`) to tasks that run on specific **Host Groups** (like `local_machine` or
`k8s_control_plane`).

This decoupled design means that the engine (`core/engine.py`) simply executes the plan defined in the registry, making
the entire workflow easy to understand, modify, and extend.

```python
# core/registry.py (Simplified)
TASK_REGISTRY = {
    "INIT": {
        "local_machine": [check_dependencies, ...],
        "k8s_control_plane": [prepare_node, install_containerd, init_control_plane, setup_fluxcd],
        ...
    },
    "ARC": {
        "local_machine": [check_azure_login, install_arc_agent],
    }
}
```

## 📋 Prerequisites

To use Calcifer, you need the following installed on your **local management machine**:

* Python 3.9+
* SSH client and network access to the remote nodes.
* Azure CLI (`az`): For authentication and Arc-related tasks.
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

3. **Set up Environment Variables:**
   Create a `.env` file in the root directory. This is the most secure place for your Azure credentials.
   ```env
   # .env
   AZURE_SUBSCRIPTION_ID="your-subscription-id"
   AZURE_TENANT_ID="your-tenant-id"
   ```

4. **Configure the Inventory:**
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

5. **Configure the Cluster:**
   Edit `cluster_config.yaml` to define cluster-wide parameters and GitOps configuration.
   ```yaml
   # cluster_config.yaml
   azure:
     resource_group: "my-k8s-cluster-rg"
     location: "westeurope"

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

### Step 1: 🛡️ Trust Remote Hosts

For security, Nornir is configured to only connect to known SSH hosts. This command scans the remote hosts defined in
your inventory and adds their keys to your local `~/.ssh/known_hosts` file.

```bash
python main.py trust
```

### Step 2: 🚀 Initialize the Cluster

This is the main provisioning command. It executes the `INIT` goal, which performs the following sequence:

1. **On the local machine**: Verifies dependencies like Azure CLI.
2. **On the remote nodes**:
    * Prepares the OS (disables swap, loads kernel modules).
    * Installs `containerd`.
    * Installs `kubeadm`, `kubelet`, and `kubectl`.
    * Runs `kubeadm init` to create the control plane.
    * Fetches the `admin.conf` to your local machine.
    * Installs the Flannel CNI using the local `kubectl`.
    * Bootstraps FluxCD if enabled.

```bash
python main.py init
```

### Step 3: ☁️ Connect to Azure Arc

This command executes the `ARC` goal, which connects the newly provisioned cluster to Azure. This entire process is *
*agentless**—it runs from your local machine using the fetched `kubeconfig` and does not require `az` CLI on the cluster
nodes.

```bash
python main.py connect-arc
```

## 📂 Project Structure

```text
.
├── core/               # Core orchestration logic
│   ├── engine.py       # The "Matrix Engine" that drives Nornir
│   ├── registry.py     # Maps Goals to Tasks for each Host Group
│   ├── models.py       # Standardized result objects (OK, FAILED, etc.)
│   ├── settings.py     # Configuration loader (YAML + Env Vars)
│   └── decorators.py   # Wrappers for tasks (logging, error handling, UI)
├── tasks/              # Atomic, idempotent task functions
├── inventory/          # Nornir inventory files
│   ├── hosts.yaml      # Define your servers here
│   └── groups.yaml     # Define host groups
├── utils/              # Helper utilities like the file logger
├── main.py             # Typer CLI application entrypoint
├── cluster_config.yaml # Main configuration for your cluster
├── requirements.txt    # Python dependencies
└── calcifer.log        # Detailed log file for debugging
```
