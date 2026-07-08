from enum import StrEnum
from importlib import import_module
from collections.abc import Callable, Sequence
from typing import TypeVar

from langchain_core.tools import BaseTool


class ToolProfile(StrEnum):
    """Tool groups used to keep each model call focused on relevant actions."""

    TASK_READ = "task_read"
    TASK_WRITE = "task_write"
    TAGS = "tags"
    SCHEDULE = "schedule"
    RECURRENCE = "recurrence"
    FULL = "full"


_PROFILE_EXPANSIONS: dict[ToolProfile, frozenset[ToolProfile]] = {
    ToolProfile.TASK_READ: frozenset(
        {
            ToolProfile.TASK_READ,
            ToolProfile.TASK_WRITE,
            ToolProfile.TAGS,
            ToolProfile.SCHEDULE,
            ToolProfile.RECURRENCE,
            ToolProfile.FULL,
        }
    ),
    ToolProfile.TASK_WRITE: frozenset(
        {
            ToolProfile.TASK_WRITE,
            ToolProfile.TAGS,
            ToolProfile.SCHEDULE,
            ToolProfile.RECURRENCE,
            ToolProfile.FULL,
        }
    ),
    ToolProfile.TAGS: frozenset({ToolProfile.TAGS, ToolProfile.FULL}),
    ToolProfile.SCHEDULE: frozenset(
        {ToolProfile.SCHEDULE, ToolProfile.RECURRENCE, ToolProfile.FULL}
    ),
    ToolProfile.RECURRENCE: frozenset({ToolProfile.RECURRENCE, ToolProfile.FULL}),
    ToolProfile.FULL: frozenset({ToolProfile.FULL}),
}
_TOOL_MODULES = (
    "agents.tools.system",
    "agents.tools.tasks",
    "agents.tools.tags",
)

ToolT = TypeVar("ToolT", bound=BaseTool)

_tools_by_profile: dict[ToolProfile, list[BaseTool]] = {profile: [] for profile in ToolProfile}
_read_tools_by_profile: dict[ToolProfile, list[BaseTool]] = {profile: [] for profile in ToolProfile}
_registered_tool_names: set[str] = set()
_tool_modules_loaded = False


def register_tool(read_only: bool, profiles: Sequence[ToolProfile]) -> Callable[[ToolT], ToolT]:
    """Register a LangChain tool for the selected agent tool profiles."""
    if not profiles:
        raise ValueError("At least one tool profile must be provided.")

    expanded_profiles = _expand_profiles(profiles)

    def decorator(tool: ToolT) -> ToolT:
        if tool.name in _registered_tool_names:
            raise ValueError(f"Tool {tool.name!r} is already registered.")

        _registered_tool_names.add(tool.name)
        for profile in expanded_profiles:
            _tools_by_profile[profile].append(tool)
            if read_only:
                _read_tools_by_profile[profile].append(tool)
        return tool

    return decorator


def get_task_tools(profile: ToolProfile = ToolProfile.FULL) -> list[BaseTool]:
    """Return the registered tools available to the selected profile."""
    _ensure_tool_modules_loaded()
    return _tools_by_profile[profile].copy()


def get_read_tools(profile: ToolProfile = ToolProfile.FULL) -> list[BaseTool]:
    """Return non-mutating tools"""
    _ensure_tool_modules_loaded()
    return _read_tools_by_profile[profile].copy()


def _expand_profiles(profiles: Sequence[ToolProfile]) -> frozenset[ToolProfile]:
    expanded: set[ToolProfile] = set()
    for profile in profiles:
        expanded.update(_PROFILE_EXPANSIONS[profile])
    return frozenset(expanded)


def _ensure_tool_modules_loaded() -> None:
    global _tool_modules_loaded
    if _tool_modules_loaded:
        return

    _tool_modules_loaded = True
    for module_name in _TOOL_MODULES:
        import_module(module_name)
