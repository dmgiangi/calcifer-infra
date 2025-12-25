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
    tenant_id: Optional[str] = None
    location: str = "westeurope"
    resource_group: str = "calcifer-rg"

@dataclass
class K8sSettings:
    """Configuration for Kubernetes cluster."""
    version: str = "1.29"

@dataclass
class AppSettings:
    """Main application configuration aggregator."""
    azure: AzureSettings
    k8s: K8sSettings
    environment: str = "dev"

def load_settings() -> AppSettings:
    """
    Loads configuration from environment variables.
    Raises ValueError if critical variables are missing.
    """
    sub_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    if not sub_id:
        raise ValueError("AZURE_SUBSCRIPTION_ID is missing in .env file")

    return AppSettings(
        azure=AzureSettings(
            subscription_id=sub_id,
            tenant_id=os.getenv("AZURE_TENANT_ID"),
            location=os.getenv("AZURE_LOCATION", "westeurope"),
            resource_group=os.getenv("AZURE_RESOURCE_GROUP", "calcifer-rg")
        ),
        k8s=K8sSettings(
            version=os.getenv("K8S_VERSION", "1.29")
        ),
        environment=os.getenv("ENV", "dev")
    )