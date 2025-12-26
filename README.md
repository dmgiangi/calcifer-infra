# Calcifer Infrastructure Manager

Calcifer is a CLI automation tool designed to provision, manage, and tear down Kubernetes clusters and Azure Arc
integrations.

It is built on top of **Nornir** for hybrid orchestration (Local + SSH) and **Typer** for the CLI interface. The core
architecture relies on a **Matrix Engine** that decouples technical tasks from high-level goals, ensuring modularity and
idempotence.

## 🚀 Features

* **Matrix Orchestration**: Goals (Check, Init, Destroy) are mapped to Host Groups (Local, Control Plane, Workers) via a
  central registry.
* **Idempotent Design**: Provisioning commands can be safely re-run to ensure the desired state.
* **Hybrid Execution**: Seamlessly manages tasks on the local machine (subprocess) and remote nodes (SSH/Scrapli).
* **Rich UI & Logging**: clean, beautiful console output for the operator, with detailed technical logs saved to
  `calcifer.log` for debugging.
* **Type-Safe Configuration**: Centralized settings management using Python dataclasses.

## 📂 Project Structure

```text
.
├── core/
│   ├── engine.py       # The orchestrator that drives Nornir based on the Registry
│   ├── registry.py     # Defines the "Goal x Group" task mapping
│   ├── models.py       # Standardized result objects (OK, WARNING, FAILED)
│   ├── settings.py     # Env var loading and configuration injection
│   └── decorators.py   # Wrappers for logging and crash prevention
├── tasks/              # Atomic, pure functions (business logic only)
├── inventory/          # Nornir inventory (hosts.yaml, groups.yaml)
├── utils/              # Logging utilities
├── main.py             # CLI Entry point
└── inventory_config.yaml         # Nornir configuration
```

## 🛠️ Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/dmgiangi/calcifer-infra.git
   cd calcifer-infra
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Setup Environment:**
   Create a `.env` file in the root directory with your Azure details:
   ```env
   AZURE_SUBSCRIPTION_ID=your-subscription-id
   AZURE_TENANT_ID=your-tenant-id
   AZURE_LOCATION=westeurope
   # Optional
   ENV=dev
   ```

## 🎮 Usage

The CLI provides three main semantic commands. You can enable autocompletion by running
`python main.py --install-completion`.

### 1. Verify (Read-Only)

Runs pre-flight checks (connectivity, dependencies, authentication) across all relevant groups without modifying the
system.

```bash
# Run verification on all hosts defined in the registry
python main.py verify

# Run only on a specific target
python main.py verify --target calcifer
```

### 2. Initialize (Provisioning)

Executes the provisioning pipeline. This includes installing dependencies (like Azure CLI), configuring the OS,
initializing Kubernetes, and connecting to Azure Arc.

```bash
python main.py init
```

### 3. Destroy (Teardown)

**Warning: Destructive Operation.**
Disconnects the cluster from Azure Arc (cleaning up cloud resources) and resets the local/remote cluster configuration.
Requires confirmation.

```bash
python main.py destroy
```

## ⚙️ Configuration & Extending

### The Registry

The logic of "who does what" is defined in `core/registry.py`. To add a new step to the provisioning process, simply add
your task function to the appropriate list in the `TASK_REGISTRY` dictionary.

```python
"INIT": {
    "local_machine": [ensure_azure_cli, ensure_azure_login],
    "k8s_control_plane": [ensure_azure_cli, install_arc_agent]
}
```

### Adding New Tasks

Create a new file in `tasks/`. Ensure your function:

1. Accepts a Nornir `Task` object.
2. Is decorated with `@automated_step`.
3. Returns a `Result` containing a `StandardResult` model.

## 📝 Logging

* **Console**: Shows only high-level status (✅ OK, ⚠️ Warning, ❌ Failed) and progress.
* **File**: Full technical details, stack traces, and debug info are written to `calcifer.log`.