# Task Manager

Task Manager is a task management service designed for working with an
AI assistant.

The service helps keep track of tasks, deadlines, statuses, and related context.
The user describes what needs to be done, and the assistant can turn that into
structured task actions: create a task, update it, mark it as done, find related
tasks, or organize tasks for later.

## What It Does

- Creates tasks with a title, description, start time, end time, and status.
- Shows active, completed, cancelled, and overdue tasks.
- Updates task details when plans change.
- Completes, reopens, cancels, and deletes tasks.
- Finds tasks by status, date range, text, and tags.
- Creates tasks with tags when the context is already known.
- Adds and removes tags from existing tasks.
- Counts tasks that match selected filters.

## Tags

Tags are mostly meant for the AI assistant, not for constant manual management.

The assistant can use tags to remember task context: project, topic, person,
area of responsibility, or any other recurring category. Later, those tags help
the assistant quickly find related tasks without asking the user to maintain a
strict folder or label system.

Users can still create, rename, view, and delete tags when needed.

## Search

Tasks can be searched by text from their title and description.

This is useful when the user remembers only part of the task, a topic, or a
wording fragment, but does not remember the exact deadline, status, or tag.

## Project Status

The core task and tag workflows are implemented.

The project currently includes domain models, DTOs, repositories, services,
database migrations, and tests. A production user interface, HTTP API, or final
AI-agent integration is not included yet.

## Development

Install dependencies:

```bash
uv sync
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
`.env` and `.test.env` files.
