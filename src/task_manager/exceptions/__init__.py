from exceptions.base import BaseAppException
from exceptions.access import (
    AgentQuotaExhausted,
    EmailVerificationRequired,
    Forbidden,
    InvalidClientAddress,
    RegistrationLimitExceeded,
    RequestRateLimitExceeded,
)
from exceptions.wrong import Wrongness, WrongTaskInterval, TaskScheduleOverlap
from exceptions.auth import AuthError, InvalidCredentials, InvalidRequestOrigin, InvalidToken
from exceptions.unavailable import (
    AgentCoordinationUnavailable,
    AuthProtectionUnavailable,
    Unavailable,
)
from exceptions.conflict import (
    Conflict,
    AgentRequestNotRetryable,
    AgentRunInProgress,
    EmailAlreadyExists,
    TagAlreadyExists,
)
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
    "Forbidden",
    "EmailVerificationRequired",
    "AgentQuotaExhausted",
    "RequestRateLimitExceeded",
    "RegistrationLimitExceeded",
    "InvalidClientAddress",
    "AuthError",
    "InvalidCredentials",
    "InvalidRequestOrigin",
    "InvalidToken",
    "Unavailable",
    "AgentCoordinationUnavailable",
    "AuthProtectionUnavailable",
    "Conflict",
    "AgentRequestNotRetryable",
    "AgentRunInProgress",
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
