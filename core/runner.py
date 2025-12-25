# core/runner.py
import sys
from typing import Callable, Dict, Any
from nornir import InitNornir
from nornir.core.task import AggregatedResult, Task, Result
from rich.panel import Panel
from utils.logger import logger


def execute_nornir_workflow(
        workflow_func: Callable[[Task], Result],
        workflow_name: str,
        filter_parameters: Dict[str, Any] = None,
        config_file: str = "config.yaml"
):
    """
    Generic function to execute a Nornir workflow.
    It handles initialization, host filtering, execution, and the final report.

    Args:
        workflow_func: The workflow function to execute (e.g., configure_arc_workflow)
        workflow_name: The name displayed in the logs
        filter_parameters: Dictionary to filter hosts (e.g., {"name": "localhost"})
        config_file: Path to the Nornir config file
    """

    # 1. Graphic Header
    logger.console.print(Panel.fit(
        f"[bold white]{workflow_name}[/bold white]",
        border_style="blue"
    ))

    # 2. Nornir Initialization
    try:
        nr = InitNornir(config_file=config_file)
    except Exception as e:
        logger.console.print(f"[bold red]❌ Critical Error initializing Nornir:[/bold red] {e}")
        sys.exit(1)

    # 3. Host Filtering
    # If no filters are passed, use the entire inventory
    if filter_parameters:
        targets = nr.filter(**filter_parameters)
    else:
        targets = nr

    host_count = len(targets.inventory.hosts)
    logger.console.print(f"[bold cyan]Target Hosts:[/bold cyan] {host_count}")

    if host_count == 0:
        logger.console.print("[yellow]No hosts found matching filter. Exiting.[/yellow]")
        sys.exit(0)

    # 4. Workflow Execution
    logger.console.print(f"\n[bold]🚀 Starting {workflow_name}...[/bold]\n")

    result: AggregatedResult = targets.run(
        task=workflow_func,
        name=workflow_name
    )

    # 5. Final Summary
    _print_summary(result)


def _print_summary(agg_result: AggregatedResult):
    """Internal helper to print the final execution summary."""
    logger.console.print("\n[bold]📊 Execution Summary[/bold]")
    logger.console.print("─" * 30)

    failed_hosts = []
    success_hosts = []

    for host, multi_result in agg_result.items():
        # multi_result is a list of Results. If any task failed,
        # Nornir marks the entire host execution as failed.
        if multi_result.failed:
            failed_hosts.append(host)
        else:
            success_hosts.append(host)

    # Print Successes
    if success_hosts:
        logger.console.print(f"[bold green]✅ Success ({len(success_hosts)}):[/bold green] {', '.join(success_hosts)}")

    # Print Failures
    if failed_hosts:
        logger.console.print(f"[bold red]❌ Failed ({len(failed_hosts)}):[/bold red] {', '.join(failed_hosts)}")
        sys.exit(1)  # Exit code 1 to indicate failure in CI/CD pipelines
    else:
        logger.console.print("\n[bold green]✨ Workflow completed successfully.[/bold green]")
        sys.exit(0)