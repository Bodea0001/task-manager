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
