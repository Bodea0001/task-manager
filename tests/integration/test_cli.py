import pytest

from cli.main import run
from dto.users import RegisterUser
from domain.value_objects.agent_usage import AgentAccessLevel
from services.agent_usage import AgentUsageService
from services.auth import AuthService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_verify_email_command_enables_verified_account_access(
    auth_service: AuthService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tokens = await auth_service.register(
        RegisterUser(
            email="cli-verified@example.com",
            password="correct-password",
            first_name="CLI",
            last_name="User",
        )
    )

    first_exit_code = await run(["users", "verify-email", "cli-verified@example.com"])
    second_exit_code = await run(["users", "verify-email", "cli-verified@example.com"])
    current_user = await auth_service.get_current_user(tokens.access_token)

    assert first_exit_code == 0
    assert second_exit_code == 0
    assert current_user.email_verified is True
    assert "cli-verified@example.com" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_set_agent_access_command_grants_unmetered_access(
    auth_service: AuthService,
    agent_usage_service: AgentUsageService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tokens = await auth_service.register(
        RegisterUser(
            email="cli-unmetered@example.com",
            password="correct-password",
            first_name="CLI",
            last_name="Access",
        )
    )
    user = await auth_service.get_current_user(tokens.access_token)

    exit_code = await run(
        ["users", "set-agent-access", user.email, AgentAccessLevel.UNMETERED.value]
    )
    allowance = await agent_usage_service.get_allowance(user.user_id)

    assert exit_code == 0
    assert allowance.access_level is AgentAccessLevel.UNMETERED
    assert allowance.limit is None
    assert allowance.remaining is None
    assert AgentAccessLevel.UNMETERED.value in capsys.readouterr().out
