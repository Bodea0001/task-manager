from exceptions.base import BaseAppException


class Unavailable(BaseAppException):
    pass


class AgentCoordinationUnavailable(Unavailable):
    def __init__(self):
        message = "Agent coordination is unavailable"
        super().__init__(message)


class AuthProtectionUnavailable(Unavailable):
    def __init__(self):
        message = "Authentication protection is unavailable"
        super().__init__(message)
