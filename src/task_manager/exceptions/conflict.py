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


class AgentRunInProgress(Conflict):
    def __init__(self):
        message = "An agent request is already running for this chat"
        super().__init__(message)


class AgentRequestNotRetryable(Conflict):
    def __init__(self):
        message = "The latest agent request is not available for retry"
        super().__init__(message)
