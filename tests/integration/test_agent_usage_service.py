from asyncio import gather
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from dto.users import RegisterUser
from exceptions import AgentQuotaExhausted
from services.agent_usage import AgentUsageService
from services.auth import AuthService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_unverified_account_can_use_only_its_configured_agent_allowance(
    auth_service: AuthService,
    agent_usage_service: AgentUsageService,
) -> None:
    user_id = await _register_user(auth_service, "quota-unverified@example.com")
    initial_allowance = await agent_usage_service.get_allowance(user_id)
    run_ids = [uuid4() for _ in range(initial_allowance.limit + 1)]

    for run_id in run_ids[: initial_allowance.limit]:
        await agent_usage_service.reserve(run_id, user_id)
        await agent_usage_service.consume(run_id, user_id)

    with pytest.raises(AgentQuotaExhausted) as exc_info:
        await agent_usage_service.reserve(run_ids[-1], user_id)

    allowance = await agent_usage_service.get_allowance(user_id)
    assert (exc_info.value.used, exc_info.value.limit) == (
        initial_allowance.limit,
        initial_allowance.limit,
    )
    assert allowance.used == allowance.limit
    assert allowance.remaining == 0


@pytest.mark.asyncio
async def test_released_agent_reservation_does_not_consume_allowance(
    auth_service: AuthService,
    agent_usage_service: AgentUsageService,
) -> None:
    user_id = await _register_user(auth_service, "quota-release@example.com")
    run_id = uuid4()

    await agent_usage_service.reserve(run_id, user_id)
    await agent_usage_service.release(run_id, user_id)

    allowance = await agent_usage_service.get_allowance(user_id)
    assert allowance.used == 0
    assert allowance.remaining == allowance.limit


@pytest.mark.asyncio
async def test_verification_expands_the_same_lifetime_allowance(
    auth_service: AuthService,
    agent_usage_service: AgentUsageService,
    test_engine: AsyncEngine,
) -> None:
    user_id = await _register_user(auth_service, "quota-verification@example.com")
    before_verification = await agent_usage_service.get_allowance(user_id)
    run_id = uuid4()
    await agent_usage_service.reserve(run_id, user_id)
    await agent_usage_service.consume(run_id, user_id)

    async with test_engine.begin() as connection:
        await connection.execute(
            text("""
                UPDATE user_email_verification
                SET verified_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        )

    allowance = await agent_usage_service.get_allowance(user_id)
    assert allowance.used == 1
    assert allowance.limit >= before_verification.limit
    assert allowance.remaining == allowance.limit - allowance.used


@pytest.mark.asyncio
async def test_parallel_agent_reservations_cannot_exceed_the_limit(
    auth_service: AuthService,
    agent_usage_service: AgentUsageService,
) -> None:
    user_id = await _register_user(auth_service, "quota-concurrency@example.com")
    initial_allowance = await agent_usage_service.get_allowance(user_id)

    results = await gather(
        *(
            agent_usage_service.reserve(uuid4(), user_id)
            for _ in range(initial_allowance.limit + 1)
        ),
        return_exceptions=True,
    )

    reservations = [result for result in results if not isinstance(result, BaseException)]
    rejected = [result for result in results if isinstance(result, AgentQuotaExhausted)]
    allowance = await agent_usage_service.get_allowance(user_id)
    assert len(reservations) == initial_allowance.limit
    assert len(rejected) == 1
    assert allowance.used == allowance.limit
    assert allowance.remaining == 0


async def _register_user(auth_service: AuthService, email: str) -> UUID:
    tokens = await auth_service.register(
        RegisterUser(
            email=email,
            password="correct-password",
            first_name="Quota",
            last_name="User",
        )
    )
    user = await auth_service.get_current_user(tokens.access_token)
    return user.user_id
