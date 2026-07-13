from dataclasses import dataclass

DEFAULT_CHAT_TITLE = "New chat"
CHAT_TITLE_MAX_LENGTH = 250


@dataclass(frozen=True, slots=True)
class CreateChatData:
    title: str = DEFAULT_CHAT_TITLE

    def __post_init__(self) -> None:
        _normalize_and_validate_title(self, self.title)


@dataclass(frozen=True, slots=True)
class UpdateChatData:
    title: str

    def __post_init__(self) -> None:
        _normalize_and_validate_title(self, self.title)


@dataclass(frozen=True, slots=True)
class AddChatMessage:
    content: str

    def __post_init__(self) -> None:
        normalized_content = self.content.strip()
        if not normalized_content:
            raise ValueError("message content cannot be empty")
        object.__setattr__(self, "content", normalized_content)


@dataclass(frozen=True, slots=True)
class ListChats:
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if self.offset < 0:
            raise ValueError("offset cannot be negative")


@dataclass(frozen=True, slots=True)
class ListChatMessages:
    limit: int = 100
    offset: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if self.offset < 0:
            raise ValueError("offset cannot be negative")


def _normalize_and_validate_title(instance: object, title: str) -> None:
    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("chat title cannot be empty")
    if len(normalized_title) > CHAT_TITLE_MAX_LENGTH:
        raise ValueError(f"chat title cannot be longer than {CHAT_TITLE_MAX_LENGTH} characters")
    object.__setattr__(instance, "title", normalized_title)
