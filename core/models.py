from enum import Enum
from dataclasses import dataclass
from typing import Any, Optional

class TaskStatus(str, Enum):
    OK = "OK"             # Task completed successfully or was idempotent (no change)
    CHANGED = "CHANGED"   # Task performed an action successfully
    WARNING = "WARNING"   # Task succeeded but with non-critical issues
    FAILED = "FAILED"     # Task failed, blocking execution

@dataclass
class StandardResult:
    """
    Standard payload to be included in Nornir's Result.result.
    """
    status: TaskStatus
    message: str
    data: Optional[Any] = None  # To pass data between tasks (context sharing)