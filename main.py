from pathlib import Path

import typer
from pyinfra.api import State, connect, Inventory
from rich import print as rprint
from rich.panel import Panel

import inventory
from core.state import config as global_config
from deploy import deploy_init, deploy_arc

app = typer.Typer(
    help="Calcifer Infrastructure Manager - K8s & Arc Automation",
    add_completion=True,
    no_args_is_help=True
)


@app.callback()
def main(
        ctx: typer.Context,
        quiet: bool = typer.Option(
            False, "--quiet", "-q",
            help="Disable detailed sub-step logging (Silent Mode)."
        ),
        config_file: Path = typer.Option(
            "cluster_config.yaml", "--config", "-c",
            help="Path to the configuration YAML file.",
            exists=True, dir_okay=False, readable=True
        )
):
    """
    Calcifer Infrastructure CLI.
    Common entry point for all commands.
    """
    global_config.VERBOSE = not quiet
    global_config.CONFIG_FILE = str(config_file)

    if ctx.invoked_subcommand:
        subtitle = "v3.0 - Pyinfra Engine"
        if quiet:
            subtitle += " (Quiet Mode)"
        else:
            subtitle += " (Verbose Mode)"

        rprint(Panel.fit(
            "[bold white]Calcifer Infrastructure CLI[/bold white]",
            border_style="blue",
            subtitle=subtitle
        ))


def run_deploy(deploy_func, target_group=None):
    """
    Helper to run a pyinfra deploy.
    """
    # 1. Setup Inventory
    hosts = []
    if target_group == "local":
        hosts = inventory.local_machine
    elif target_group == "cp":
        hosts = inventory.k8s_control_plane
    elif target_group == "workers":
        hosts = inventory.k8s_worker
    else:
        # All hosts
        hosts = inventory.local_machine + inventory.k8s_control_plane + inventory.k8s_worker

    if not hosts:
        rprint("[bold red]❌ No hosts found for the specified target group.[/bold red]")
        return

    pyinfra_inventory = Inventory(hosts)
    state = State(pyinfra_inventory)

    # 2. Connect
    rprint(f"🔸 [bold]Connecting to {len(hosts)} hosts...[/bold]")
    connect(state)

    # 3. Run Deploy
    rprint(f"🔸 [bold]Executing deploy: {deploy_func.__name__}...[/bold]")
    deploy_func(state=state)

    # 4. Show results summary?
    # Pyinfra handles output by default if configured.


@app.command()
def init(
        target: str = typer.Option(
            None, "--target", "-t",
            help="Target group (local, cp, workers) or specific host."
        )
):
    """
    [Idempotent] Provisions the infrastructure.
    """
    run_deploy(deploy_init, target_group=target)


@app.command(name="connect-arc")
def connect_arc(
        target: str = typer.Option(
            None, "--target", "-t",
            help="Target group (local, cp, workers) or specific host."
        )
):
    """
    [Azure] Connects the initialized cluster to Azure Arc.
    """
    run_deploy(deploy_arc, target_group=target)


if __name__ == "__main__":
    app()