from pathlib import Path

from agents.prompts.summarization import TASK_MANAGER_SUMMARY_PROMPT
from agents.prompts.tool_routing import TOOL_ROUTER_PROMPT


_PROMPT_PATH = Path(__file__).with_name("task_manager.md")


def load_task_manager_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


__all__ = [
    "TASK_MANAGER_SUMMARY_PROMPT",
    "TOOL_ROUTER_PROMPT",
    "load_task_manager_prompt",
]
