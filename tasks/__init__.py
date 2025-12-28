from nornir.core.task import Task, Result

from core.models import TaskStatus, StandardResult, SubTaskResult


def fail(task: Task, sub_res: SubTaskResult) -> Result:
    """
    Helper to return a failed Result from a SubTaskResult.
    """
    return Result(
        host=task.host,
        failed=True,
        result=StandardResult(TaskStatus.FAILED, sub_res.message)
    )

__all__ = [
    "fail"
]