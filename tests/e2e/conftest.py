import os
import socket
import subprocess
import sys
from asyncio import sleep, to_thread
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROOT = PROJECT_ROOT / "src" / "task_manager"
TEST_DATABASE_NAME_PARTS = {"test", "testing", "pytest"}
E2E_STARTUP_TIMEOUT_SECONDS = 90


@pytest.fixture(scope="session")
def e2e_environment() -> None:
    if os.getenv("TASK_MANAGER_RUN_E2E") != "1":
        pytest.skip("Set TASK_MANAGER_RUN_E2E=1 to run external E2E tests")

    database_name = os.getenv("TASK_MANAGER_E2E_DB_NAME") or os.getenv("TASK_CONFIG_DB_NAME")
    if database_name is None:
        pytest.fail(
            "TASK_CONFIG_DB_NAME or TASK_MANAGER_E2E_DB_NAME must identify a test database",
            pytrace=False,
        )
    database_name_parts = set(database_name.lower().replace("-", "_").split("_"))
    if TEST_DATABASE_NAME_PARTS.isdisjoint(database_name_parts):
        pytest.fail(
            "Refusing to run E2E tests against a database whose name does not contain "
            "a separate 'test', 'testing', or 'pytest' part",
            pytrace=False,
        )

    os.environ["TASK_CONFIG_DB_NAME"] = database_name
    _validate_required_environment()


@pytest.fixture(scope="session")
def migrated_e2e_database(e2e_environment: None) -> None:
    alembic = Path(sys.executable).with_name("alembic")
    result = subprocess.run(
        (str(alembic), "upgrade", "head"),
        cwd=PROJECT_ROOT,
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            f"E2E database migration failed with code {result.returncode}",
            pytrace=False,
        )


@pytest_asyncio.fixture(scope="session")
async def e2e_servers(
    migrated_e2e_database: None,
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncGenerator[tuple[str, str]]:
    log_directory = tmp_path_factory.mktemp("granian-e2e")
    environment = _server_environment()
    processes: list[tuple[subprocess.Popen[bytes], BinaryIO]] = []
    urls: list[str] = []

    try:
        for name in ("primary", "secondary"):
            port = _available_port()
            log_path = log_directory / f"{name}.log"
            log_file = log_path.open("wb")
            process = _start_server(port, environment, log_file)
            processes.append((process, log_file))
            url = f"http://127.0.0.1:{port}"
            await _wait_until_ready(process, url, log_path)
            urls.append(url)

        yield urls[0], urls[1]
    finally:
        for process, _ in reversed(processes):
            await _stop_server(process)
        for _, log_file in processes:
            log_file.close()


@pytest_asyncio.fixture
async def e2e_client(e2e_servers: tuple[str, str]) -> AsyncGenerator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        base_url=e2e_servers[0],
        timeout=httpx.Timeout(30, connect=5),
    ) as client:
        yield client


def _validate_required_environment() -> None:
    required_names = (
        "TASK_CONFIG_DB_USER",
        "TASK_CONFIG_DB_PASSWORD",
        "TASK_CONFIG_AUTH_JWT_SECRET",
        "TASK_CONFIG_AUTH_PASSWORD_SALT",
        "TASK_CONFIG_AGENT_BASE_URL",
        "TASK_CONFIG_AGENT_BASE_API_KEY",
        "TASK_CONFIG_KEY_VALUE_STORE_URL",
    )
    missing_names = [name for name in required_names if not os.getenv(name)]
    has_base_model = bool(os.getenv("TASK_CONFIG_AGENT_BASE_MODEL_NAME"))
    has_split_models = bool(
        os.getenv("TASK_CONFIG_AGENT_PLANNER_MODEL_NAME")
        and os.getenv("TASK_CONFIG_AGENT_SUBAGENT_MODEL_NAME")
    )
    if not has_base_model and not has_split_models:
        missing_names.append(
            "TASK_CONFIG_AGENT_BASE_MODEL_NAME or both planner/subagent model names"
        )
    if missing_names:
        pytest.fail(
            "Missing E2E configuration: " + ", ".join(missing_names),
            pytrace=False,
        )


def _server_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(APPLICATION_ROOT)
    environment["TASK_CONFIG_DB_POOL_SIZE"] = "2"
    environment["TASK_CONFIG_DB_MAX_OVERFLOW"] = "0"
    environment["TASK_CONFIG_COORDINATION_KEY_PREFIX"] = f"task-manager:e2e:agent-run:{uuid4().hex}"
    environment["TASK_CONFIG_AUTH_PROTECTION_KEY_PREFIX"] = (
        f"task-manager:e2e:auth-protection:{uuid4().hex}"
    )
    environment["TASK_CONFIG_AUTH_PROTECTION_REGISTRATION_ATTEMPT_LIMIT"] = "100"
    environment["TASK_CONFIG_AUTH_PROTECTION_LOGIN_ATTEMPT_LIMIT"] = "100"
    environment["TASK_CONFIG_AUTH_PROTECTION_SUCCESSFUL_REGISTRATION_LIMIT"] = "100"
    for name in tuple(environment):
        if name.startswith("LANGFUSE_"):
            del environment[name]
    return environment


def _start_server(
    port: int,
    environment: dict[str, str],
    log_file: BinaryIO,
) -> subprocess.Popen[bytes]:
    granian = Path(sys.executable).with_name("granian")
    return subprocess.Popen(
        (
            str(granian),
            "--interface",
            "asgi",
            "--workers",
            "1",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--working-dir",
            str(APPLICATION_ROOT),
            "--log-level",
            "warning",
            "main:app",
        ),
        cwd=PROJECT_ROOT,
        env=environment,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )


def _available_port() -> int:
    with socket.socket() as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        return int(server_socket.getsockname()[1])


async def _wait_until_ready(
    process: subprocess.Popen[bytes],
    base_url: str,
    log_path: Path,
) -> None:
    async with httpx.AsyncClient(timeout=2) as client:
        for _ in range(E2E_STARTUP_TIMEOUT_SECONDS * 2):
            if process.poll() is not None:
                pytest.fail(_startup_failure(process, log_path), pytrace=False)
            try:
                response = await client.get(f"{base_url}/health/ready")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await sleep(0.5)

    pytest.fail(
        f"Granian did not become ready at {base_url}.\n{_log_tail(log_path)}",
        pytrace=False,
    )


def _startup_failure(process: subprocess.Popen[bytes], log_path: Path) -> str:
    return f"Granian exited during startup with code {process.returncode}.\n{_log_tail(log_path)}"


def _log_tail(log_path: Path) -> str:
    if not log_path.exists():
        return "No server log was produced."
    lines = log_path.read_text(errors="replace").splitlines()
    return "\n".join(lines[-80:])


async def _stop_server(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        await to_thread(process.wait, 20)
    except subprocess.TimeoutExpired:
        process.kill()
        await to_thread(process.wait, 5)
