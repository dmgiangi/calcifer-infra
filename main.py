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
        verbose: bool = typer.Option(
            False, "--verbose", "-v",
            help="Enable detailed logging of sub-steps to console."
        )
):
    """
    Calcifer Infrastructure CLI.
    Common entry point for all commands.
    """
    # 1. Set global state based on flag
    global_config.VERBOSE = verbose

    # 2. Show banner (only if not asking for help or completion)
    if ctx.invoked_subcommand:
        subtitle = "v2.0 - Matrix Engine"
        if verbose:
            subtitle += " (Verbose Mode)"

        rprint(Panel.fit(
            "[bold white]Calcifer Infrastructure CLI[/bold white]",
            border_style="blue",
            subtitle=subtitle
        ))


# ... verify, init, destroy commands remain the SAME ...
# Typer handles --verbose being global.

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
