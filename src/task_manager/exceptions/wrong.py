from exceptions.base import BaseAppException


class Wrongness(BaseAppException):
    pass


class WrongTaskDeadline(Wrongness):
    def __init__(self):
        message = "Wrong task deadline"
        super().__init__(message)
