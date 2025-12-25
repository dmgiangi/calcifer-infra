import os
from dataclasses import dataclass, asdict
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

@dataclass
class AzureSettings:
    """Configuration for Azure resources."""
    subscription_id: str
    tenant_id: Optional[str]
    location: str
    resource_group: str

@dataclass
class K8sSettings:
    """Configuration for Kubernetes cluster."""
    version: str

@dataclass
class AppSettings:
    """Main application configuration aggregator."""
    azure: AzureSettings
    k8s: K8sSettings
    environment: str

def load_settings() -> AppSettings:
    """
    Loads configuration from environment variables.
    Raises ValueError if critical variables are missing.
    """
    def get_env_or_raise(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise ValueError(f"{key} is missing in .env file")
        return value

    return AppSettings(
        azure=AzureSettings(
            subscription_id=get_env_or_raise("AZURE_SUBSCRIPTION_ID"),
            tenant_id=os.getenv("AZURE_TENANT_ID"),
            location=get_env_or_raise("AZURE_LOCATION"),
            resource_group=get_env_or_raise("AZURE_RESOURCE_GROUP")
        ),
        k8s=K8sSettings(
            version=get_env_or_raise("K8S_VERSION")
        ),
        environment=get_env_or_raise("ENV")
    )