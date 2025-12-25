import typer
from typing import Optional
from rich import print as rprint
from rich.panel import Panel

# Import only the Engine, not single workflows
from core.engine import MatrixEngine

app = typer.Typer(
    help="Calcifer Infrastructure Manager - K8s & Arc Automation",
    add_completion=False,
    no_args_is_help=True
)


@app.callback()
def main_banner():
    """
    Common entry point. Displays the banner before any command.
    """
    rprint(Panel.fit(
        "[bold white]Calcifer Infrastructure CLI[/bold white]",
        border_style="blue",
        subtitle="v2.0 - Matrix Engine"
    ))


@app.command()
def verify(
        target: str = typer.Option(
            None, "--target", "-t",
            help="Filter hosts by name. If not provided, runs on all relevant groups."
        )
):
    """
    [Read-Only] Runs pre-flight checks (dependencies, auth, connectivity).
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
    Installs dependencies, configures K8s, connects to Arc.
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
    [Destructive] Deprovisions and removes the cluster/Arc connection.
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