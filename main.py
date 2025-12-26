import os
import subprocess
from pathlib import Path

import typer
from nornir import InitNornir
from rich import print as rprint
from rich.panel import Panel

from core.engine import MatrixEngine
from core.state import config as global_config

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
    # 1. Update Global State
    global_config.VERBOSE = not quiet
    global_config.CONFIG_FILE = str(config_file)

    # 2. Handle Sudo Password
    # 3. Show Banner (unless help/completion)
    if ctx.invoked_subcommand:
        subtitle = "v2.0 - Matrix Engine"

        if quiet:
            subtitle += " (Quiet Mode)"
        else:
            subtitle += " (Verbose Mode)"

        rprint(Panel.fit(
            "[bold white]Calcifer Infrastructure CLI[/bold white]",
            border_style="blue",
            subtitle=subtitle
        ))


@app.command()
def trust():
    """
    [Security] Scans remote hosts and updates local known_hosts.
    Required because auth_strict_key is now enabled.
    """
    rprint(Panel.fit("[bold blue]🛡️  SSH Trust Manager[/bold blue]", border_style="blue"))

    # 1. Load Inventory (Lightweight init)
    try:
        # Use the standard Nornir config file (which points to hosts.yaml/groups.yaml)
        nr = InitNornir(config_file="inventory_config.yaml")
    except Exception as e:
        rprint(f"[bold red]❌ Config Error:[/bold red] {e}")
        raise typer.Exit(1)

    known_hosts_path = os.path.expanduser("~/.ssh/known_hosts")

    # 2. Iterate over hosts
    for name, host in nr.inventory.hosts.items():
        # We skip localhost or local connections
        if host.hostname in ["127.0.0.1", "localhost"] or host.platform == "linux_local":
            continue

        target = host.hostname
        port = host.port or 22

        rprint(f"🔸 Scanning [bold cyan]{name}[/bold cyan] ({target}:{port})...", end="")

        # 3. Check if already known (ssh-keygen -F)
        check_cmd = ["ssh-keygen", "-F", target]
        is_known = subprocess.run(check_cmd, capture_output=True).returncode == 0

        if is_known:
            rprint(" [green]Already Trusted ✔[/green]")
            continue

        # 4. Scan (ssh-keyscan)
        # -H: Hash names (optional, secure format)
        scan_cmd = ["ssh-keyscan", "-p", str(port), "-H", target]
        scan_res = subprocess.run(scan_cmd, capture_output=True, text=True)

        if scan_res.returncode != 0 or not scan_res.stdout:
            rprint(f" [red]Failed ❌[/red]\n   {scan_res.stderr}")
            continue

        # 5. Append to known_hosts
        try:
            with open(known_hosts_path, "a") as f:
                f.write(scan_res.stdout)
            rprint(" [yellow]Added to known_hosts ✨[/yellow]")
        except Exception as e:
            rprint(f" [red]Write Error ❌[/red]: {e}")

    rprint("\n[bold green]✅ Trust procedure completed.[/bold green]")


@app.command()
def verify(
        target: str = typer.Option(
            None, "--target", "-t",
            help="Filter hosts by name. If not provided, runs on all relevant groups."
        )
):
    """
    [Read-Only] Runs pre-flight checks.
    Goal: CHECK
    """
    engine = MatrixEngine()
    engine.run(goal="CHECK", target_filter=target)


@app.command()
def init(
        target: str = typer.Option(
            None, "--target", "-t",
            help="Specific host to provision."
        )
):
    """
    [Idempotent] Provisions the infrastructure.
    Goal: INIT
    """
    engine = MatrixEngine()
    engine.run(goal="INIT", target_filter=target)


@app.command()
def destroy(
        force: bool = typer.Option(
            False, "--force", "-f",
            prompt="Are you sure you want to destroy the cluster and remove Arc connection?",
            help="Skip confirmation prompt."
        )
):
    """
    [Destructive] Deprovisions and removes the cluster.
    Goal: DESTROY
    """
    if not force:
        rprint("[red]Aborted.[/red]")
        raise typer.Abort()

    rprint("[bold red]🔥 Starting Teardown Sequence...[/bold red]")

    engine = MatrixEngine()
    engine.run(goal="DESTROY")


@app.command(name="connect-arc")
def connect_arc(
        target: str = typer.Option(
            None, "--target", "-t",
            help="Specific host/cluster to connect (uses inventory name)."
        )
):
    """
    [Azure] Connects the initialized cluster to Azure Arc.
    Requires 'init' to be run first (needs inventory/kubeconfig_admin.yaml).
    """
    engine = MatrixEngine()
    engine.run(goal="ARC", target_filter=target)


if __name__ == "__main__":
    app()
