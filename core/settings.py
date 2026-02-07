import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Union

import yaml
from dotenv import load_dotenv

# Load env vars if present
load_dotenv()


# --- DATACLASSES (SCHEMA) ---

@dataclass
class FluxSettings:
    """Defines GitOps configuration."""
    enabled: bool = False
    github_url: str = ""
    branch: str = "main"
    cluster_path: str = ""
    # Structural defaults (can be overridden by YAML)
    remote_key_path: str = "/tmp/flux_identity"
    local_key_path: str = None


@dataclass
class K8sSettings:
    """Defines Kubernetes node and cluster configuration."""
    version: str = "1.29"
    pod_network_cidr: str = "10.244.0.0/16"
    cni_manifest_url: str = "https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml"

    local_kubeconfig_path: str = "inventory/kubeconfig_admin.yaml"
    flux: FluxSettings = field(default_factory=FluxSettings)

    # Empty defaults: Le liste reali devono essere nel cluster_config.yaml
    kernel_modules: List[str] = field(default_factory=list)
    sysctl_params: Dict[str, str] = field(default_factory=dict)


@dataclass
class AppSettings:
    """Root configuration object."""
    k8s: K8sSettings = field(default_factory=K8sSettings)
    environment: str = "dev"


# --- LOADER LOGIC ---

def load_settings(config_path: str = "cluster_config.yaml") -> AppSettings:
    """
    Loads configuration merging: Defaults (Schema) < YAML File (Config) < Environment Vars (Secrets).
    """

    # 1. Load YAML Config
    file_config = {}
    path = Path(config_path)
    if path.exists():
        try:
            with open(path, 'r') as f:
                file_config = yaml.safe_load(f) or {}
        except Exception as e:
            # We log to stdout/stderr since the logger might not be ready yet
            print(f"[Warning] Failed to load {config_path}: {e}")

    # 2. Load Environment Variables (Secrets & Overrides)
    # We manually map only the keys that make sense to override via ENV
    env_config = {
        "environment": os.getenv("ENV"),
        "k8s": {
            "version": os.getenv("K8S_VERSION"),
        },
    }

    # Cleanup: We remove None/Empty keys from ENV dictionaries
    def clean_none(d: Union[Dict, None]):
        if not isinstance(d, dict): return d
        return {k: clean_none(v) for k, v in d.items() if v is not None and v != {}}

    env_config = clean_none(env_config)

    # 3. Merge Logic

    # --- Kubernetes ---
    k8s_defaults = {
        "version": "1.29",
        "pod_network_cidr": "10.244.0.0/16",
    }
    k8s_file = file_config.get("k8s", {})
    k8s_env = env_config.get("k8s", {})

    # Nested Flux management
    flux_defaults = {"enabled": False}
    flux_file = k8s_file.get("flux", {})
    flux_final = {**flux_defaults, **flux_file}
    flux_obj = FluxSettings(**{k: v for k, v in flux_final.items() if k in FluxSettings.__annotations__})

    # We remove 'flux' from the k8s dict before the final merge to handle it as an object
    if "flux" in k8s_file: del k8s_file["flux"]

    k8s_final = {**k8s_defaults, **k8s_file, **k8s_env}

    k8s_args = {k: v for k, v in k8s_final.items() if k in K8sSettings.__annotations__}
    k8s_args["flux"] = flux_obj  # We inject the FluxSettings object

    k8s_obj = K8sSettings(**k8s_args)

    # --- App Root ---
    app_env_val = env_config.get("environment") or file_config.get("environment", "dev")

    return AppSettings(
        k8s=k8s_obj,
        environment=app_env_val
    )