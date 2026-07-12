from exceptions.base import BaseAppException
from exceptions.wrong import Wrongness, WrongTaskInterval, TaskScheduleOverlap
from exceptions.auth import AuthError, InvalidCredentials, InvalidToken
from exceptions.conflict import Conflict, EmailAlreadyExists, TagAlreadyExists
from exceptions.not_found import (
    NotFound,
    ChatNotFound,
    TagNotFound,
    TaskNotFound,
    UserNotFound,
    RecurrenceTemplateNotFound,
    RecurrenceRuleNotFound,
    RecurrenceOccurrenceNotFound,
)


__all__ = [
    "BaseAppException",
    "AuthError",
    "InvalidCredentials",
    "InvalidToken",
    "Conflict",
    "EmailAlreadyExists",
    "TagAlreadyExists",
    "Wrongness",
    "WrongTaskInterval",
    "TaskScheduleOverlap",
    "NotFound",
    "ChatNotFound",
    "TagNotFound",
    "TaskNotFound",
    "UserNotFound",
    "RecurrenceTemplateNotFound",
    "RecurrenceRuleNotFound",
    "RecurrenceOccurrenceNotFound",
]
