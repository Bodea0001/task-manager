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
- Supports recurring tasks with daily, selected-weekday, and monthly calendar
  rules.
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
monthly rules, multiple weekdays, monthly calendar positions, optional work
duration, and optional end limits. Without a duration, each occurrence has a
deadline but does not reserve time in the schedule.

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
- "Remind me to review support requests every Monday and Thursday at 09:00."
- "Create a reminder for the last Friday of every month at 16:00."
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
- Recurring tasks: daily, selected-weekday, and monthly calendar rules,
  deadline-only or scheduled occurrences, end limits, safe recalculation,
  skipped dates, stopping, deletion, and paginated listing. Creating or
  expanding recurring work requires a verified account.
- Tags and context: tag creation, renaming, removal, task tagging, contextual
  lookup, and change history.
- Users and access: user accounts, authentication, email-verification state,
  session rotation and logout, profile updates without implicit email changes,
  and per-user data access. Existing accounts remain verified after migration;
  newly registered accounts start unverified.
- Chat sessions: titled per-user conversations with paginated, persistent
  user-visible message history and strict ownership boundaries.
- Assistant agent: natural-language task-management requests, safe service-layer
  tool execution, progress updates, chat-bound memory, verification-dependent
  free usage limits, and Langfuse tracing when configured. Requests that fail
  before the model returns a usable response do not consume the allowance.
- HTTP API: liveness and readiness checks, authentication, current-user profile
  management, chat lifecycle and history, streamed assistant requests, and
  manual task, tag, schedule-inspection, and recurring-task workflows for
  clients that need direct, predictable controls.
- Frontend: responsive direct task management, weekly calendar, recurring-task
  workflows, assistant chat, English and Russian localization, theme settings,
  and installable PWA behavior.

The codebase includes domain models, DTOs, repositories, services, database
migrations, the production frontend, and tests.

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

Run one Redis-compatible key-value store, such as Redis or Valkey, for all
distributed coordination and background delivery:

```bash
TASK_CONFIG_KEY_VALUE_STORE_URL=redis://localhost:6379/0
```

The same store backs agent-run leases, Celery message delivery, and background
job coordination. Namespaced keys keep these responsibilities isolated without
requiring a separate Redis database for each operation.

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

Free assistant allowances default to 3 lifetime requests for an unverified
account and 10 lifetime requests for a verified account. Override these product
limits with `TASK_CONFIG_AGENT_USAGE_UNVERIFIED_RUN_LIMIT` and
`TASK_CONFIG_AGENT_USAGE_VERIFIED_RUN_LIMIT`. A verified allowance includes
requests already used before verification rather than adding a second quota.

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
and `TASK_CONFIG_KEY_VALUE_STORE_URL` settings. Tests use public HTTP APIs,
isolated users, two server processes, and a unique key prefix. They do not emit
Langfuse traces. `TASK_MANAGER_E2E_DB_NAME` can override the configured test
database when stronger isolation is needed.

Apply database migrations:

```bash
uv run alembic upgrade head
```

Trusted administrators can verify an existing account from the application
source directory. The operation is safe to repeat:

```bash
cd src/task_manager
uv run python -m cli users verify-email user@example.com
```

Agent access is quota-limited by default. A trusted administrator can remove
the product quota for a test account without disabling concurrency controls or
usage accounting, and can restore the normal quota later:

```bash
uv run python -m cli users set-agent-access user@example.com unmetered
uv run python -m cli users set-agent-access user@example.com limited
```

Run the HTTP API with Granian:

```bash
uv run granian --interface asgi --working-dir src/task_manager \
  --log-config src/task_manager/granian_logging.json --no-access-log main:app
```

Run the background worker and one scheduler in separate processes:

```bash
cd src/task_manager
uv run celery -A workers.app:celery_app worker \
  --queues recurrence_materialization --loglevel INFO
uv run celery -A workers.app:celery_app beat --loglevel INFO
```

Recurring-task horizons are extended once per day at 02:00 UTC by default.
Override the fixed schedule with
`TASK_CONFIG_CELERY_RECURRENCE_MATERIALIZATION_HOUR`,
`TASK_CONFIG_CELERY_RECURRENCE_MATERIALIZATION_MINUTE`, and
`TASK_CONFIG_CELERY_TIMEZONE`. Run only one Beat scheduler for this schedule;
additional worker processes consume the shared queue and must not start their
own scheduler.

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
when PostgreSQL and the shared key-value store are reachable and the agent is
initialized.

Authenticated clients can send assistant requests with
`POST /api/v1/chats/{chat_id}/agent`. The response is a `text/event-stream`
containing plan progress, heartbeat, final result, or controlled error events.

The integration tests require PostgreSQL and use the configured Redis-compatible
store when it is available.
Configuration is loaded from environment variables with the `TASK_CONFIG`
prefix, and test runs can use `.env` and `.test.env` files. Integration tests
must run against a dedicated test database: `TASK_CONFIG_DB_NAME` must contain a
separate `test`, `testing` or `pytest` part, for example `task_manager_test`.
Key-value store tests isolate their keys with a unique prefix. The integration
test fixtures truncate application tables before and after each test.

## Continuous Integration

GitHub Actions validates backend formatting, linting, types, unit tests, and
integration behavior against isolated PostgreSQL and Redis services. It also
checks frontend linting and tests, then creates a production build and verifies
its bundle-size budgets.

E2E tests are intentionally excluded from required CI checks because some
scenarios depend on an external model provider and natural-language model
behavior. Run them manually with the opt-in command documented above when the
required services and model access are available.
