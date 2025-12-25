import typer
from rich import print as rprint
from rich.panel import Panel

from core.runner import execute_nornir_workflow
from workflows.configure_arc import configure_arc_workflow

app = typer.Typer(
    help="CLI Automation Tool for Azure Arc & Infrastructure Management.",
    add_completion=False,
    no_args_is_help=True
)


@app.callback()
def main_banner():
    """
    This callback runs before any command.
    We use it to display the main application banner.
    """
    rprint(Panel.fit(
        "[bold white]Azure Arc Automation CLI[/bold white]",
        border_style="blue"
    ))


@app.command()
def onboard(
        host: str = typer.Option("localhost", help="The name of the host to target (must be in inventory).")
):
    """
    Runs the Azure Arc Onboarding workflow.
    """
    execute_nornir_workflow(
        workflow_func=configure_arc_workflow,
        workflow_name="Azure Arc Onboarding",
        filter_parameters={"name": host}
    )


if __name__ == "__main__":
    app()
