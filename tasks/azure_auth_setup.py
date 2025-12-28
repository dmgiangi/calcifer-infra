from pyinfra import host
from pyinfra.operations import server


def ensure_azure_login():
    """
    Ensures Azure Login & Prerequisites.
    """
    config = host.data.app_config.azure
    target_sub = config.subscription_id

    # Check session
    server.shell(
        name="Verify Azure Session",
        commands=["az account show"],
    )

    # Set subscription
    server.shell(
        name=f"Set Azure Subscription to {target_sub}",
        commands=[f"az account set --subscription {target_sub}"],
    )

    # Check Extensions
    server.shell(
        name="Install connectedk8s extension",
        commands=["az extension add --name connectedk8s --yes"],
    )

    # Register Providers
    providers = [
        "Microsoft.Kubernetes",
        "Microsoft.KubernetesConfiguration",
        "Microsoft.ExtendedLocation"
    ]
    for prov in providers:
        server.shell(
            name=f"Register provider {prov}",
            commands=[f"az provider register --namespace {prov} --wait"],
        )
