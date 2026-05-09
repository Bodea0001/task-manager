# Task Manager

Task Manager is a task management service designed for working with an
AI assistant.

The service keeps track of tasks, deadlines, schedules, statuses, tags, and user
accounts. A user can describe what needs to be done, and an assistant can turn
that into structured task actions: create a task, update it, mark it as done,
find related tasks, or organize tasks for later.

## What It Does

- Creates tasks with a title, description, due date, schedule, and status.
- Shows active, completed, cancelled, and overdue tasks.
- Updates task details when plans change.
- Completes, reopens, cancels, and deletes tasks.
- Finds tasks by status, due date, scheduled time, text, and tags.
- Creates tasks with tags when the context is already known.
- Adds and removes tags from existing tasks.
- Counts tasks that match selected filters.
- Shows free time between scheduled tasks.
- Keeps each user's tasks and tags separate from other users.

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
- "Cancel the task about buying office chairs."

Complete or reopen tasks:

- "Mark the report task as done."
- "Complete all tasks about the release checklist."
- "Reopen the task about contract review."
- "Show me what I completed this week."

Find tasks:

- "Show my active tasks."
- "What is overdue?"
- "Find tasks about invoices."
- "Show tasks due this week."
- "Show tasks scheduled for tomorrow."
- "How many active tasks do I have?"

Work with tags and context:

- "Tag the report task as finance."
- "Show everything related to the website redesign."
- "Create a tag for hiring and add the interview task to it."
- "Remove the personal tag from the passport task."
- "Rename the errands tag to personal errands."

## Project Status

The core task, tag, user, authentication, schedule, and search workflows are
implemented.

The project currently includes domain models, DTOs, repositories, services,
database migrations, and tests. A production user interface, HTTP API, or final
AI-agent integration is not included yet.

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
