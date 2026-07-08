from typing import Literal

from langchain_openai import ChatOpenAI

from config import settings

_THINKING_TYPE = Literal["enabled", "disabled"]


def create_base_chat_model(thinking_mode: bool | None = None) -> ChatOpenAI:
    """Create the configured OpenAI-compatible chat model used by agent calls."""

    thinking_type = _get_thinking_type(thinking_mode)

    return ChatOpenAI(
        model=settings.agent.base_model_name,
        base_url=settings.agent.base_url,
        api_key=settings.agent.base_api_key,
        temperature=0.1,
        timeout=settings.agent.model_timeout_seconds,
        extra_body={"thinking": {"type": thinking_type}},
    )


def _get_thinking_type(thinking_mode: bool | None = None) -> _THINKING_TYPE:
    if thinking_mode is None:
        thinking_type = settings.agent.thinking_mode
    elif thinking_mode:
        thinking_type = "enabled"
    else:
        thinking_type = "disabled"

    return thinking_type
