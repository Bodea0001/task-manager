from exceptions.base import BaseAppException


class NotFound(BaseAppException):
    pass


class TaskNotFound(NotFound):
    def __init__(self):
        message = "Task not found"
        super().__init__(message)
