from typing import Literal

from langchain_openai import ChatOpenAI

from config import settings


def create_planner_chat_model() -> ChatOpenAI:
    """Create the model used to decompose requests and select specialized agents."""
    return _create_chat_model(
        model_name=settings.agent.planner_model_name,
        thinking_mode=settings.agent.planner_thinking_mode,
    )


def create_subagent_chat_model() -> ChatOpenAI:
    """Create the tool-capable model used by specialized agents."""
    return _create_chat_model(
        model_name=settings.agent.subagent_model_name,
        thinking_mode=settings.agent.subagent_thinking_mode,
    )


def create_responder_chat_model() -> ChatOpenAI:
    """Create the lightweight model used to synthesize final responses."""
    return _create_chat_model(
        model_name=settings.agent.subagent_model_name,
        thinking_mode=settings.agent.subagent_thinking_mode,
    )


def _create_chat_model(
    model_name: str,
    thinking_mode: Literal["enabled", "disabled"],
) -> ChatOpenAI:
    return ChatOpenAI(
        model=model_name,
        base_url=settings.agent.base_url,
        api_key=settings.agent.base_api_key,
        temperature=0.1,
        timeout=settings.agent.model_timeout_seconds,
        extra_body={"thinking": {"type": thinking_mode}},
    )
