from exceptions.base import BaseAppException


class NotFound(BaseAppException):
    pass


class TaskNotFound(NotFound):
    def __init__(self):
        message = "Task not found"
        super().__init__(message)


class TagNotFound(NotFound):
    def __init__(self):
        message = "Tag not found"
        super().__init__(message)


class UserNotFound(NotFound):
    def __init__(self):
        message = "User not found"
        super().__init__(message)
