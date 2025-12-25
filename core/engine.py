import sys

from nornir import InitNornir
from nornir.core.task import AggregatedResult
from rich.console import Console
from rich.panel import Panel

from core.models import TaskStatus, StandardResult
from core.registry import TASK_REGISTRY, GROUP_EXECUTION_ORDER
from core.settings import load_settings

console = Console()


class MatrixEngine:
    def __init__(self, config_file: str = "config.yaml"):
        self.config_file = config_file
        self.nr = None
        self._initialize()

    def _initialize(self):
        """Initializes Nornir and injects configuration."""
        try:
            app_settings = load_settings()
            self.nr = InitNornir(config_file=self.config_file)
            # Inject settings into global defaults
            self.nr.inventory.defaults.data["app_config"] = app_settings.__dict__
        except Exception as e:
            console.print(f"[bold red]❌ Init Error:[/bold red] {e}")
            sys.exit(1)

    def run(self, goal: str, target_filter: str = None):
        """
        Executes the pipeline for the specified Goal.
        """
        if goal not in TASK_REGISTRY:
            console.print(f"[bold red]⛔ Goal '{goal}' not defined in Registry.[/bold red]")
            return

        console.print(Panel.fit(f"[bold blue]🚀 Starting Goal: {goal}[/bold blue]", border_style="blue"))

        # Iterate over groups in defined order (Local -> CP -> Workers)
        for group_name in GROUP_EXECUTION_ORDER:

            # Retrieve tasks for this intersection (Goal, Group)
            tasks = TASK_REGISTRY[goal].get(group_name, [])
            if not tasks:
                continue

            # Filter inventory for this group
            # (Optional: also apply manual --target filter if passed from CLI)
            group_hosts = self.nr.filter(filter_func=lambda h: group_name in h.groups)

            if target_filter:
                group_hosts = group_hosts.filter(name=target_filter)

            if len(group_hosts.inventory.hosts) == 0:
                continue

            console.print(
                f"\n[bold cyan]Targeting Group:[/bold cyan] {group_name} ({len(group_hosts.inventory.hosts)} hosts)")

            # Sequential execution of tasks defined in the Registry
            for task_func in tasks:
                task_name = task_func.__name__

                # Visual feedback before execution
                console.print(f"  🔸 Running: [bold]{task_name}[/bold]...", end="")

                # ACTUAL EXECUTION
                agg_result = group_hosts.run(task=task_func, name=task_name)

                # Result analysis (UI + Flow Control)
                stop_execution = self._handle_results(agg_result)

                if stop_execution:
                    console.print(
                        f"\n[bold red]⛔ Execution halted due to critical failure in group {group_name}.[/bold red]")
                    sys.exit(1)

    def _handle_results(self, agg_result: AggregatedResult) -> bool:
        """
        Analyzes results, prints status (OK/WARN/FAIL) and decides whether to stop the engine.
        Returns True if execution should stop (Critical Failure).
        """
        has_critical_failure = False

        # agg_result is a dictionary {host_name: MultiResult}
        for host, multi_res in agg_result.items():
            # Take the last result (current task)
            # multi_res[0] because Nornir wraps each run in a list
            task_result = multi_res[0]

            # Extract our standardized payload
            # If the task failed hard (exception), result might be a string or Exception
            payload = task_result.result

            # Fallback if the task did not return a StandardResult (e.g. unexpected error)
            if not isinstance(payload, StandardResult):
                status = TaskStatus.FAILED if task_result.failed else TaskStatus.OK
                msg = str(payload)
            else:
                status = payload.status
                msg = payload.message

            # --- UI RENDERING ---
            if status == TaskStatus.OK:
                console.print(f"\r  ✅ [bold green]{task_result.name}[/bold green]: {msg}")

            elif status == TaskStatus.CHANGED:
                console.print(f"\r  ✨ [bold yellow]{task_result.name}[/bold yellow]: {msg}")

            elif status == TaskStatus.WARNING:
                console.print(f"\r  ⚠️ [bold orange3]{task_result.name}[/bold orange3]: {msg}")

            elif status == TaskStatus.FAILED:
                console.print(f"\r  ❌ [bold red]{task_result.name}[/bold red]: {msg} (Host: {host})")
                has_critical_failure = True

        return has_critical_failure
