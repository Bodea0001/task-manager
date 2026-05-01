# Task Manager

Task Manager is an AI-assisted task management service. The project is intended
to help users manage everyday work through an intelligent agent: create tasks,
inspect the current task list, update task details, mark tasks as completed, and
keep the task state organized without manually navigating every operation.

The core idea is to combine a clear task domain model with an agent-friendly
application layer. A user should be able to describe what they need in natural
language, while the system turns that intent into explicit task operations.

## Planned Capabilities

- Create tasks from natural language requests.
- View active, completed, and overdue tasks.
- Update task titles, descriptions, deadlines and other info.
- Mark tasks as completed or reopen them when needed.

## Current Stack

- Python 3.14
- SQLAlchemy asyncio
- Alembic migrations
- PostgreSQL via asyncpg
- uv for dependency management

## Project Status

The project is in the initialization stage.

## Configuration

Application settings are loaded from environment variables with the
`TASK_CONFIG` prefix. Database settings are grouped under `db`.

Expected database variables:

```bash
TASK_CONFIG_DB_USER=postgres
TASK_CONFIG_DB_PASSWORD=postgres
TASK_CONFIG_DB_NAME=task_manager
TASK_CONFIG_DB_HOST=localhost
TASK_CONFIG_DB_PORT=5432
```

## Development

Install dependencies and run project commands with `uv`:

```bash
uv sync
cd src/task_manager
uv run python main.py
```

The repository is still being shaped, so startup commands and module paths may
change as the package structure is finalized.
