TOOL_ROUTER_PROMPT = """Choose the smallest tool profile for a task-manager request.

Profiles:
- task_read: choose for read-only lookup, search, counting, listing, or history.
- task_write: choose for task content, status, priority, or tag assignment changes
  that do not require schedule-specific tools.
- tags: choose for tag catalog management or explicit tag metadata changes.
- schedule: choose when the request depends on interpreting, changing,
  separating, or removing temporal constraints on tasks. Users may use words like
  deadline, date, time, window, and schedule loosely.
- recurrence: choose for repeating work, recurrence templates, recurrence rules,
  occurrences, or skipped occurrences.
- full: choose only when one profile cannot cover clearly required capabilities.

If the current request cannot be classified without recent conversation context,
return needs_context.

Return exactly one of these exact values and no other text:
task_read
task_write
tags
schedule
recurrence
full
needs_context

Prefer the smallest sufficient profile."""
