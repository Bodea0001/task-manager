from exceptions.base import BaseAppException
from exceptions.wrong import Wrongness, WrongTaskInterval, TaskScheduleOverlap
from exceptions.auth import AuthError, InvalidCredentials, InvalidToken
from exceptions.conflict import Conflict, EmailAlreadyExists
from exceptions.not_found import NotFound, TagNotFound, TaskNotFound, UserNotFound

_wrong_exceptions = ()

__all__ = [
    "BaseAppException",
    "AuthError",
    "InvalidCredentials",
    "InvalidToken",
    "Conflict",
    "EmailAlreadyExists",
    "Wrongness",
    "WrongTaskInterval",
    "TaskScheduleOverlap",
    "NotFound",
    "TagNotFound",
    "TaskNotFound",
    "UserNotFound",
]
