from exceptions.base import BaseAppException


class AuthError(BaseAppException):
    pass


class InvalidCredentials(AuthError):
    def __init__(self):
        message = "Invalid credentials"
        super().__init__(message)


class InvalidToken(AuthError):
    def __init__(self):
        message = "Invalid token"
        super().__init__(message)
