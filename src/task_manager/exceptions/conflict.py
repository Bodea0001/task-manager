from exceptions.base import BaseAppException


class Conflict(BaseAppException):
    pass


class EmailAlreadyExists(Conflict):
    def __init__(self):
        message = "Email already exists"
        super().__init__(message)


class TagAlreadyExists(Conflict):
    def __init__(self):
        message = "Tag already exists"
        super().__init__(message)
