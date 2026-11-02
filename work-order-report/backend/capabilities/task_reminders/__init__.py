"""Outstanding-task reminder capability."""

from functools import lru_cache

from capabilities.task_reminders.repository import TaskReminderRepository
from capabilities.task_reminders.service import TaskReminderService


@lru_cache(maxsize=1)
def get_task_reminder_service() -> TaskReminderService:
    return TaskReminderService(TaskReminderRepository())


__all__ = [
    "TaskReminderRepository",
    "TaskReminderService",
    "get_task_reminder_service",
]

