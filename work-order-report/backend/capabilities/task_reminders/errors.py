"""Task Reminder application errors for entrypoint-specific translation."""


class TaskReminderError(Exception):
    pass


class TaskReminderValidationError(TaskReminderError):
    pass


class TaskReminderNotFoundError(TaskReminderError):
    pass


class TaskReminderConflictError(TaskReminderError):
    pass


class TaskReminderExecutionError(TaskReminderError):
    pass

