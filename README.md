# Task Manager

Task Manager is a task management service designed for working with an
AI assistant.

The service keeps track of tasks, deadlines, schedules, statuses, priorities,
tags, and user accounts. A user can describe what needs to be done, and an
assistant can turn that into structured task actions: create a task, update it,
mark it as done, find related tasks, or organize tasks for later.

## What It Does

- Helps users remember what needs to be done and when.
- Keeps upcoming, overdue, completed, and cancelled work easy to review.
- Helps users plan time for focused work without creating schedule conflicts.
- Makes it easy to change plans when deadlines, priorities, or details move.
- Connects related work with lightweight context, such as projects, people, or
  topics.
- Helps users find the task they mean, even when they do not remember its exact
  name.
- Keeps a clear record of important changes so users can understand what
  happened.

## How the Assistant Should Work

The assistant should let the user speak naturally and turn the request into
clear task actions.

It should ask a follow-up question when important details are missing, such as
the deadline, planned time, task name, or which task the user means. It should
not ask for technical fields when the meaning is already clear from the user's
message.

The assistant should remember context with tags when it is useful: project,
topic, person, place, responsibility area, or any repeated category. Tags should
help the assistant find related tasks later without forcing the user to manage a
strict folder system.

The assistant should set one of the supported task priorities: `low`, `normal`,
`high`, or `urgent`. If the user does not explicitly name a priority, the
assistant should infer it from urgency, deadline, impact, and wording, and use
`normal` when there is no clear reason to raise or lower it.

The assistant should keep each user's tasks separate, avoid overlapping planned
work for the same user, and explain when a requested schedule conflicts with an
existing task.

## Example Prompts

Create a task:

- "Remind me to submit the report by Friday."
- "Add a task to call Anna tomorrow."
- "I need to prepare slides for the product meeting next Tuesday."
- "Create a task for renewing the server certificate before May 20."

Plan time for work:

- "Schedule invoice review tomorrow from 10:00 to 11:30."
- "Move the design review to Thursday afternoon."
- "Remove the scheduled time from the budget task."
- "Find free time this week for a two-hour planning session."

Update task details:

- "Change the report deadline to next Monday."
- "Rename the task about slides to 'Prepare Q2 roadmap slides'."
- "Add more details to the tax task: check deductions and upload receipts."
- "Make the server certificate task urgent."
- "Cancel the task about buying office chairs."

Complete or reopen tasks:

- "Mark the report task as done."
- "Complete all tasks about the release checklist."
- "Reopen the task about contract review."
- "Show me what I completed this week."

Find tasks:

- "Show my active tasks."
- "Show urgent tasks."
- "What is overdue?"
- "Find tasks about invoices."
- "Show tasks due this week."
- "Show tasks scheduled for tomorrow."
- "How many active tasks do I have?"
- "Show what changed on the report task."

Work with tags and context:

- "Tag the report task as finance."
- "Show everything related to the website redesign."
- "Create a tag for hiring and add the interview task to it."
- "Remove the personal tag from the passport task."
- "Rename the errands tag to personal errands."
- "Show the history of the finance tag."

## Project Status

Implemented product areas:

- Tasks: creation, updates, deadlines, scheduling, priorities, status changes,
  removal, search, counts, free-time lookup, and change history.
- Tags and context: tag creation, renaming, removal, task tagging, contextual
  lookup, and change history.
- Users and access: user accounts, authentication, and per-user data access.

The codebase includes domain models, DTOs, repositories, services, database
migrations, and tests.

Not included yet:

- Production user interface.
- HTTP API.
- Final AI-agent integration.

## Development

Install dependencies:

```bash
uv sync
```

Configure PostgreSQL connection settings through environment variables:

```bash
TASK_CONFIG_DB_USER=task_manager
TASK_CONFIG_DB_PASSWORD=password
TASK_CONFIG_DB_NAME=task_manager
TASK_CONFIG_DB_HOST=localhost
TASK_CONFIG_DB_PORT=5432
```

For non-local use, also set strong authentication secrets:

```bash
TASK_CONFIG_AUTH_JWT_SECRET=change-me-to-a-long-random-secret
TASK_CONFIG_AUTH_PASSWORD_SALT=change-me-to-a-long-random-salt
```

Run tests:

```bash
uv run pytest tests/unit
uv run pytest tests/integration
```

Apply database migrations:

```bash
uv run alembic upgrade head
```

The integration tests require PostgreSQL. Configuration is loaded from
environment variables with the `TASK_CONFIG` prefix, and test runs can use
`.env` and `.test.env` files. Integration tests must run against a dedicated
test database: `TASK_CONFIG_DB_NAME` must contain a separate `test`, `testing`
or `pytest` part, for example `task_manager_test`. The integration test
fixtures truncate application tables before and after each test.
