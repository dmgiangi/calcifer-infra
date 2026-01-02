import functools
import logging
from pathlib import Path

from rich.console import Console

# System logger configuration (non-UI)
LOG_FILE = Path("calcifer.log")
console = Console()

def setup_logger():
    """
    Configures the standard Python logger to write to a file.
    Does not print to console to avoid cluttering the Rich UI.
    """
    logger = logging.getLogger("calcifer")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicates if initialized multiple times
    if logger.hasHandlers():
        return logger

    # Detailed formatting for debugging
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(module)s] - %(message)s'
    )

    # File Handler (writes to calcifer.log)
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    return logger

# Singleton instance
sys_logger = setup_logger()


def log_operation(func):
    """
    Decorator to log the start and end of an operation on a single line.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        op_name = func.__name__.replace("_", " ").title()
        console.print(f"🔹 [bold cyan]Starting operation:[/bold cyan] {op_name}...", end="\r")
        try:
            result = func(*args, **kwargs)
            console.print(f"✅ [bold green]Operation completed:[/bold green] {op_name}   ")
            return result
        except Exception as e:
            console.print(f"❌ [bold red]Operation failed:[/bold red] {op_name} ({e})")
            raise e

    return wrapper
