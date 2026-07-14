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
- Shows open time inside the periods the user is willing to consider.
- Shows which existing tasks would get in the way before adding work to a
  specific time window.
- Finds the nearest open time when the user knows how long the work should take.
- Supports recurring tasks for work that repeats on a daily, weekly, or monthly
  cadence.
- Lets users review recurring tasks.
- Lets users adjust, stop, or remove recurring tasks when plans change.
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

For repeated work, the assistant should use recurring tasks instead of creating
many independent tasks one by one. Recurring tasks support daily, weekly, and
monthly schedules, planned time windows, and optional end limits.

When a user wants to change when a recurring task happens or when it ends, the
assistant can update the recurring task. When a user wants to change how often
it repeats, such as changing "daily" to "weekly" or "every week" to "every two
weeks", the assistant should replace the recurring task with a new one that
matches the requested cadence.

When a user asks about recurring work, the assistant can list the user's
recurring tasks and page through them when there are many of them. It can also
narrow the list by context when the user mentions a project, topic, or area.

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
- "What time is still free tomorrow morning and Friday afternoon?"
- "Can I schedule a deep work session tomorrow from 14:00 to 16:00?"
- "Find the next open 90-minute slot for writing the proposal."

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

Create recurring work:

- "Remind me to submit a timesheet every Friday from 16:00 to 16:15."
- "Create a daily standup prep task at 09:00 for 15 minutes."
- "Add a weekly task to review invoices every Monday from 10:00 to 11:00."
- "Create a monthly task to pay rent on the first day of each month."
- "Schedule a recurring workout every two days from 07:00 to 08:00."
- "Create a weekly product metrics review with high priority."
- "Add a monthly server maintenance task and stop after 6 occurrences."
- "Remind me to water the office plants every Wednesday until September 30."

Review recurring work:

- "Show my recurring tasks."
- "List all recurring tasks."
- "Show the next 10 recurring tasks."
- "Show the recurring tasks I created most recently."
- "Show recurring tasks with their schedules."
- "List monthly recurring tasks so I can review them."
- "Show recurring tasks related to finance."
- "List weekly recurring tasks for the hiring project."

Update recurring work:

- "Move the weekly invoice review to Mondays from 11:00 to 12:00."
- "Stop the recurring standup prep task starting next Friday."
- "End the rent reminder after the next 3 occurrences."
- "Delete the old recurring weekly metrics task."
- "Change the daily backup check to weekly instead."
- "Skip tomorrow's standup prep."
- "Mark the weekly invoice review as finance-related."
- "Remove the hiring context from the recurring interview prep task."

For requests like "Change the daily backup check to weekly instead", the
assistant should replace the old daily recurring task with a new weekly one,
because repeat frequency and interval are not edited in place.

## Project Status

Implemented product areas:

- Tasks: creation, updates, deadlines, scheduling, priorities, status changes,
  removal, search, counts, free-time lookup across chosen periods, schedule
  availability checks, nearest open time lookup, and change history.
- Recurring tasks: daily/weekly/monthly recurring work, schedule changes,
  skipped dates, stopping, deletion, and paginated listing.
- Tags and context: tag creation, renaming, removal, task tagging, contextual
  lookup, and change history.
- Users and access: user accounts, authentication, and per-user data access.
- Chat sessions: titled per-user conversations with paginated, persistent
  user-visible message history and strict ownership boundaries.
- Assistant agent: natural-language task-management requests, safe service-layer
  tool execution, progress updates, chat-bound memory, and Langfuse tracing when
  configured.
- HTTP API: liveness and readiness checks, authentication, current-user profile
  management, chat lifecycle and history, streamed assistant requests, and
  manual task, tag, schedule-inspection, and recurring-task workflows for
  clients that need direct, predictable controls.

The codebase includes domain models, DTOs, repositories, services, database
migrations, and tests.

Not included yet:

- Production user interface.

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

Configure strong authentication secrets:

```bash
TASK_CONFIG_AUTH_JWT_SECRET=change-me-to-a-long-random-secret
TASK_CONFIG_AUTH_PASSWORD_SALT=change-me-to-a-long-random-salt
```

Run Redis and configure the database used to coordinate concurrent agent runs:

```bash
TASK_CONFIG_COORDINATION_REDIS_URL=redis://localhost:6379/1
```

Configure the assistant model before running agent code:

```bash
TASK_CONFIG_AGENT_PLANNER_MODEL_NAME=your-planning-model
TASK_CONFIG_AGENT_SUBAGENT_MODEL_NAME=your-tool-capable-model
TASK_CONFIG_AGENT_BASE_URL=https://api.deepseek.com
TASK_CONFIG_AGENT_BASE_API_KEY=your-model-api-key
```

The planner model should be capable of reliable request decomposition. The
subagent model can be lighter, but must support tool calls. Planner reasoning is
enabled by default, while subagent reasoning is disabled for tool compatibility;
override these defaults with `TASK_CONFIG_AGENT_PLANNER_THINKING_MODE` and
`TASK_CONFIG_AGENT_SUBAGENT_THINKING_MODE` when the provider requires different
settings.

For local experiments, the model settings can point to any OpenAI-compatible
tool-capable endpoint, such as a local Ollama server.

To enable Langfuse traces, configure Langfuse credentials:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

Run tests:

```bash
uv run pytest tests/unit
uv run pytest tests/integration
```

Critical E2E tests are opt-in because they start two Granian processes and call
the configured model provider. They use `TASK_CONFIG_DB_NAME`, which must name a
test database, then run:

```bash
TASK_MANAGER_RUN_E2E=1 uv run pytest tests/e2e
```

The E2E environment also requires the normal database, authentication, model,
and `TASK_CONFIG_COORDINATION_REDIS_URL` settings. Tests use public HTTP APIs,
isolated users, two server processes, and a unique Redis key prefix. They do not
emit Langfuse traces. `TASK_MANAGER_E2E_DB_NAME` can override the configured
test database when stronger isolation is needed.

Apply database migrations:

```bash
uv run alembic upgrade head
```

Run the HTTP API with Granian:

```bash
uv run granian --interface asgi --working-dir src/task_manager \
  --log-config src/task_manager/granian_logging.json --no-access-log main:app
```

The application API is available under `/api/v1` by default. Interactive API
documentation is available at `/docs` and `/redoc`, with the OpenAPI document at
`/openapi.json`.

When a browser frontend runs on a separate origin, allow it explicitly:

```bash
TASK_CONFIG_HTTP_CORS_ALLOWED_ORIGINS='["http://localhost:5173"]'
TASK_CONFIG_HTTP_TRUSTED_HOSTS='["localhost", "127.0.0.1"]'
```

API documentation can be disabled with `TASK_CONFIG_HTTP_DOCS_ENABLED=false`.

Application and Granian logs are written as structured JSON to standard output.
Granian access logs are disabled in the command above because the application
already emits one correlated completion event for every HTTP request.

Use `/health/live` for process liveness. `/health/ready` reports readiness only
when PostgreSQL and coordination Redis are reachable and the agent is
initialized.

Authenticated clients can send assistant requests with
`POST /api/v1/chats/{chat_id}/agent`. The response is a `text/event-stream`
containing plan progress, heartbeat, final result, or controlled error events.

The integration tests require PostgreSQL and use Redis when it is available.
Configuration is loaded from environment variables with the `TASK_CONFIG`
prefix, and test runs can use `.env` and `.test.env` files. Integration tests
must run against a dedicated test database: `TASK_CONFIG_DB_NAME` must contain a
separate `test`, `testing` or `pytest` part, for example `task_manager_test`.
Redis tests isolate their keys with a unique prefix. The integration test
fixtures truncate application tables before and after each test.
