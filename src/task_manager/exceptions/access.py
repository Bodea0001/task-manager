from exceptions.base import BaseAppException


class Forbidden(BaseAppException):
    pass


class EmailVerificationRequired(Forbidden):
    def __init__(self) -> None:
        super().__init__("Email verification is required for this operation")


class AgentQuotaExhausted(Forbidden):
    def __init__(self, *, used: int, limit: int) -> None:
        self.used = used
        self.limit = limit
        super().__init__("Agent request quota is exhausted")


class RequestRateLimitExceeded(BaseAppException):
    def __init__(self, *, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Too many requests")


class RegistrationLimitExceeded(BaseAppException):
    def __init__(self) -> None:
        super().__init__("Registration limit exceeded")


class InvalidClientAddress(BaseAppException):
    def __init__(self) -> None:
        super().__init__("Client address is invalid")
