from pathlib import Path

import typer
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
        # --- CHANGED: Replaced verbose with quiet ---
        quiet: bool = typer.Option(
            False, "--quiet", "-q",
            help="Disable detailed sub-step logging (Silent Mode)."
        ),
        sudo_pass: bool = typer.Option(
            False, "--ask-become-pass", "-K",
            help="Prompt for sudo password (become) for privileged tasks."
        ),
        config_file: Path = typer.Option(
            "calcifer_config.yaml", "--config", "-c",
            help="Path to the configuration YAML file.",
            exists=True, dir_okay=False, readable=True
        )
):
    """
    Calcifer Infrastructure CLI.
    Common entry point for all commands.
    """
    # 1. Update Global State
    # Logic Inversion: If quiet is False, Verbose is True
    global_config.VERBOSE = not quiet
    global_config.CONFIG_FILE = str(config_file)

    # 2. Handle Sudo Password
    if sudo_pass:
        password = typer.prompt("Sudo Password", hide_input=True)
        global_config.SUDO_PASSWORD = password

    # 3. Show Banner (unless help/completion)
    if ctx.invoked_subcommand:
        subtitle = "v2.0 - Matrix Engine"

        # Update subtitle logic to reflect the mode
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


if __name__ == "__main__":
    app()
