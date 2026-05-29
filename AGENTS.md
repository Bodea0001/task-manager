# Vision

Task Manager is a Python service that provides task-management functionality for
an AI assistant.

The service owns the domain and persistence layer for user-facing task manager
capabilities. Its goal is to provide a structured action layer for an assistant:
turn natural-language intent into validated domain operations, coordinate
business rules, persist state, expose useful lookup workflows, and preserve
strict user data isolation.

# Mandates

Hard project rules.

- Use Python 3.14 and the existing stack described in `pyproject.toml`.
- Preserve the current layered architecture:
  - `domain/value_objects` contains domain dataclasses and enums.
  - `dto` contains input DTOs and user-facing validation.
  - `services` contains application use cases and business orchestration.
  - `adapters/repositories` contains SQLAlchemy data access.
  - `adapters/unitofwork.py` contains transaction boundaries.
  - `models` contains SQLAlchemy models.
- Do not bypass `SQLAlchemyUnitOfWork` from services. Database operations must
  go through the Unit of Work and repositories.
- Minimize database round-trips. Prefer query shapes and repository methods that
  load or mutate the required data in as few database calls as practical, and
  avoid per-row query loops when adding new functionality.
- Always preserve data isolation by `user_id`. A user must not see or mutate
  another user's domain data, credentials, sessions, or audit history.
- For missing or foreign-owned entities, use the existing domain exceptions
  such as `TaskNotFound`, `TagNotFound`, or `UserNotFound`; do not reveal that
  another user's data exists.
- Every database schema change must include an Alembic migration.
- Do not add an HTTP API, production UI, or final AI-agent integration unless
  explicitly requested.
- Do not store secrets in code. Use settings loaded from the `TASK_CONFIG_`
  environment prefix.
- Do not run integration tests against a production or shared database. The test
  database name must contain a separate `test`, `testing`, or `pytest` part.

# Workflow

How to work in this repository.

- Install dependencies with:

  ```bash
  uv sync
  ```

- Run unit tests for fast domain and DTO feedback:

  ```bash
  uv run pytest tests/unit
  ```

- Run integration tests only against a dedicated PostgreSQL test database:

  ```bash
  uv run pytest tests/integration
  ```

- Before finishing a change, run the relevant tests. For broad changes in
  services, repositories, migrations, or cross-entity business behavior, run
  both unit and integration tests.
- Check formatting and linting with Ruff:

  ```bash
  uv run ruff format .
  uv run ruff check .
  ```

- Run the configured pre-commit hooks when appropriate:

  ```bash
  uv run pre-commit run --all-files
  ```

- Run type checking with basedpyright:

  ```bash
  uv run basedpyright
  ```

- Make commits only when explicitly asked by the user.
- When making commits, use Conventional Commits.
- When changing the database schema:
  - update SQLAlchemy models;
  - add an Alembic migration;
  - verify `uv run alembic upgrade head`;
  - add or update integration tests.
- When adding a new use case:
  - check whether an existing DTO or value object already fits;
  - add validation at the DTO level;
  - implement orchestration in the service layer;
  - keep SQLAlchemy queries in repositories;
  - design repository calls to avoid unnecessary database round-trips;
  - cover domain rules with unit tests and persistence/user isolation with
    integration tests.
- Follow the current import style: modules inside `src/task_manager` are
  imported as `from dto...`, `from services...`, `from domain...`, without the
  `task_manager` package prefix.

# Documentation

Documentation expectations.

- Update `README.md` before making a commit when a product capability, setup
  step, environment variable, migration workflow, or public service scenario
  has changed. Intermediate implementations may change several times; by commit
  time, all new and changed behavior in the commit is considered ready for
  operation and should be documented accordingly.
- Add docstrings to public service methods when their purpose is not obvious
  from the name or when they are intended for agent/tool use cases.
- Do not comment obvious code. Prefer comments only for complex business rules,
  derived state, conflict resolution, audit history, user isolation, and
  transaction behavior.
- Validation errors and exception behavior should be specific and stable because
  tests and a future AI-agent layer may rely on them.
- New tests should describe behavior in domain language and focus on observable
  product behavior, persistence effects, user boundaries, and audit history.
