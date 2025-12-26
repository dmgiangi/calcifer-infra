from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    OK = "OK"  # Task completed successfully or was idempotent (no change)
    CHANGED = "CHANGED"  # Task performed an action successfully
    WARNING = "WARNING"  # Task succeeded but with non-critical issues
    FAILED = "FAILED"  # Task failed, blocking execution
    SKIPPED = "SKIPPED"  # Task was skipped due to the environment


@dataclass
class StandardResult:
    """
    Standard payload to be included in Nornir's Result.result.
    """
    status: TaskStatus
    message: str
    data: Optional[Any] = None  # To pass data between tasks (context sharing)


@dataclass
class SubTaskResult:
    """Lightweight result object for internal sub-steps."""
    success: bool
    message: str
    exception: Optional[Exception] = None
    data: Optional[Any] = None # To pass data to the context (e.g., current_sub_id)