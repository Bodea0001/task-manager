from exceptions.base import BaseAppException


class Wrongness(BaseAppException):
    pass


class WrongTaskInterval(Wrongness):
    def __init__(self):
        message = "Wrong task interval"
        super().__init__(message)


class TaskScheduleOverlap(Wrongness):
    def __init__(self):
        message = "Task schedule overlaps another task"
        super().__init__(message)
