from datetime import datetime, timedelta
from json import loads
from typing import Any
from uuid import uuid4

import httpx
import pytest


AGENT_TIMEOUT = httpx.Timeout(180, connect=5)


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_application_processes_are_ready(e2e_servers: tuple[str, str]) -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        for base_url in e2e_servers:
            live_response = await client.get(f"{base_url}/health/live")
            ready_response = await client.get(f"{base_url}/health/ready")

            assert live_response.status_code == 200
            assert live_response.json() == {"status": "ok"}
            assert ready_response.status_code == 200
            assert ready_response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_user_completes_a_task_creation_workflow_through_the_agent(
    e2e_client: httpx.AsyncClient,
) -> None:
    headers = await _register_user(e2e_client)
    chat_id = await _create_chat(e2e_client, headers)
    title = f"E2E planning review {uuid4().hex[:8]}"
    due_at = (datetime.now() + timedelta(days=30)).replace(
        hour=14,
        minute=30,
        second=0,
        microsecond=0,
    )
    prompt = (
        f'Create one task with the exact title "{title}" and a deadline of '
        f"{due_at:%B %d, %Y at %H:%M}."
    )

    events = await _run_agent(e2e_client, chat_id, prompt, headers)
    result = _completed_result(events)

    tasks_response = await e2e_client.get(
        "/api/v1/tasks",
        params={"search_text": title},
        headers=headers,
    )
    assert tasks_response.status_code == 200, tasks_response.text
    tasks = tasks_response.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["title"].casefold() == title.casefold()
    assert tasks[0]["due_at"] == due_at.isoformat()

    messages_response = await e2e_client.get(
        f"/api/v1/chats/{chat_id}/messages",
        headers=headers,
    )
    assert messages_response.status_code == 200, messages_response.text
    messages = messages_response.json()["messages"]
    assert [(message["role"], message["content"]) for message in messages[:2]] == [
        ("user", prompt),
        ("assistant", result["message"]),
    ]


@pytest.mark.asyncio
async def test_agent_completes_every_overdue_task_without_changing_other_tasks(
    e2e_client: httpx.AsyncClient,
) -> None:
    headers = await _register_user(e2e_client)
    chat_id = await _create_chat(e2e_client, headers)
    prefix = f"E2E overdue {uuid4().hex[:8]}"
    now = datetime.now().replace(second=0, microsecond=0)
    first_task = await _create_task(
        e2e_client,
        headers,
        title=f"{prefix} first",
        due_at=now - timedelta(days=2),
    )
    second_task = await _create_task(
        e2e_client,
        headers,
        title=f"{prefix} second",
        due_at=now - timedelta(days=1),
    )
    future_task = await _create_task(
        e2e_client,
        headers,
        title=f"{prefix} future",
        due_at=now + timedelta(days=30),
    )

    events = await _run_agent(
        e2e_client,
        chat_id,
        "Mark every overdue task as completed. Do not change tasks that are not overdue.",
        headers,
    )
    _completed_result(events)

    first_result = await _get_task(e2e_client, headers, first_task["task_id"])
    second_result = await _get_task(e2e_client, headers, second_task["task_id"])
    future_result = await _get_task(e2e_client, headers, future_task["task_id"])
    assert first_result["status"] == "completed"
    assert second_result["status"] == "completed"
    assert future_result["status"] == "active"


@pytest.mark.asyncio
async def test_users_cannot_access_each_others_tasks_or_chats(
    e2e_client: httpx.AsyncClient,
) -> None:
    owner_headers = await _register_user(e2e_client)
    other_headers = await _register_user(e2e_client)
    chat_id = await _create_chat(e2e_client, owner_headers)
    task = await _create_task(
        e2e_client,
        owner_headers,
        title=f"E2E private task {uuid4().hex[:8]}",
        due_at=datetime.now() + timedelta(days=1),
    )

    task_response = await e2e_client.get(
        f"/api/v1/tasks/{task['task_id']}",
        headers=other_headers,
    )
    chat_response = await e2e_client.get(
        f"/api/v1/chats/{chat_id}",
        headers=other_headers,
    )
    agent_response = await e2e_client.post(
        f"/api/v1/chats/{chat_id}/agent",
        json={"message": "Show the tasks in this chat."},
        headers=other_headers,
    )

    assert task_response.status_code == 404
    assert task_response.json()["code"] == "task_not_found"
    assert chat_response.status_code == 404
    assert chat_response.json()["code"] == "chat_not_found"
    assert agent_response.status_code == 404
    assert agent_response.json()["code"] == "chat_not_found"


@pytest.mark.asyncio
async def test_only_one_server_process_can_run_the_same_chat(
    e2e_servers: tuple[str, str],
) -> None:
    primary_url, secondary_url = e2e_servers
    async with (
        httpx.AsyncClient(
            base_url=primary_url,
            timeout=httpx.Timeout(30, connect=5),
        ) as primary_client,
        httpx.AsyncClient(
            base_url=secondary_url,
            timeout=httpx.Timeout(30, connect=5),
        ) as secondary_client,
    ):
        headers = await _register_user(primary_client)
        chat_id = await _create_chat(primary_client, headers)
        first_prompt = "Explain briefly what task priorities are available."

        async with primary_client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/agent",
            json={"message": first_prompt},
            headers=headers,
            timeout=AGENT_TIMEOUT,
        ) as first_response:
            assert first_response.status_code == 200, await first_response.aread()
            conflicting_response = await secondary_client.post(
                f"/api/v1/chats/{chat_id}/agent",
                json={"message": "Create another task while the first request is running."},
                headers=headers,
            )
            first_events = await _read_sse(first_response)

        assert conflicting_response.status_code == 409
        assert conflicting_response.json()["code"] == "agent_run_in_progress"
        _completed_result(first_events)

        next_events = await _run_agent(
            secondary_client,
            chat_id,
            "How many active tasks do I have?",
            headers,
        )
        _completed_result(next_events)


async def _register_user(client: httpx.AsyncClient) -> dict[str, str]:
    identifier = uuid4().hex
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"e2e-{identifier}@example.com",
            "password": f"E2E-password-{identifier}",
            "first_name": "End",
            "last_name": "ToEnd",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _create_chat(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/chats",
        json={"title": f"E2E chat {uuid4().hex[:8]}"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["chat_id"])


async def _create_task(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    title: str,
    due_at: datetime,
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/tasks",
        json={"title": title, "due_at": due_at.replace(microsecond=0).isoformat()},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _get_task(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    task_id: str,
) -> dict[str, Any]:
    response = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _run_agent(
    client: httpx.AsyncClient,
    chat_id: str,
    message: str,
    headers: dict[str, str],
) -> list[tuple[str, dict[str, Any]]]:
    async with client.stream(
        "POST",
        f"/api/v1/chats/{chat_id}/agent",
        json={"message": message},
        headers=headers,
        timeout=AGENT_TIMEOUT,
    ) as response:
        assert response.status_code == 200, await response.aread()
        return await _read_sse(response)


async def _read_sse(response: httpx.Response) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    event_name: str | None = None
    data_lines: list[str] = []

    async for line in response.aiter_lines():
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data_lines.append(line.removeprefix("data: "))
        elif not line and event_name is not None:
            events.append((event_name, loads("\n".join(data_lines))))
            if event_name in {"result", "error"}:
                break
            event_name = None
            data_lines = []

    assert events, "The agent stream did not emit any events"
    return events


def _completed_result(events: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    terminal_name, terminal_payload = events[-1]
    assert terminal_name == "result", terminal_payload
    assert terminal_payload["status"] == "completed", terminal_payload
    assert any(name == "plan" for name, _ in events), events
    return terminal_payload
