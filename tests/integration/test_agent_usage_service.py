from asyncio import gather
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from dto.agent_usage import SetAgentAccessData
from dto.users import RegisterUser
from domain.value_objects.agent_usage import AgentAccessLevel
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
    assert initial_allowance.limit is not None
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
async def test_unmetered_access_bypasses_product_quota_but_keeps_usage_history(
    auth_service: AuthService,
    agent_usage_service: AgentUsageService,
) -> None:
    email = "quota-unmetered@example.com"
    user_id = await _register_user(auth_service, email)
    limited_allowance = await agent_usage_service.get_allowance(user_id)
    assert limited_allowance.limit is not None

    access = await agent_usage_service.set_access_level(
        SetAgentAccessData(email=email, access_level=AgentAccessLevel.UNMETERED)
    )
    for _ in range(limited_allowance.limit + 1):
        run_id = uuid4()
        await agent_usage_service.reserve(run_id, user_id)
        await agent_usage_service.consume(run_id, user_id)

    allowance = await agent_usage_service.get_allowance(user_id)
    assert access.access_level is AgentAccessLevel.UNMETERED
    assert allowance.access_level is AgentAccessLevel.UNMETERED
    assert allowance.used == limited_allowance.limit + 1
    assert allowance.limit is None
    assert allowance.remaining is None


@pytest.mark.asyncio
async def test_returning_to_limited_access_reapplies_existing_lifetime_usage(
    auth_service: AuthService,
    agent_usage_service: AgentUsageService,
) -> None:
    email = "quota-return-limited@example.com"
    user_id = await _register_user(auth_service, email)
    limited_allowance = await agent_usage_service.get_allowance(user_id)
    assert limited_allowance.limit is not None
    await agent_usage_service.set_access_level(
        SetAgentAccessData(email=email, access_level=AgentAccessLevel.UNMETERED)
    )
    for _ in range(limited_allowance.limit + 1):
        run_id = uuid4()
        await agent_usage_service.reserve(run_id, user_id)
        await agent_usage_service.consume(run_id, user_id)

    await agent_usage_service.set_access_level(
        SetAgentAccessData(email=email, access_level=AgentAccessLevel.LIMITED)
    )

    with pytest.raises(AgentQuotaExhausted):
        await agent_usage_service.reserve(uuid4(), user_id)
    allowance = await agent_usage_service.get_allowance(user_id)
    assert allowance.access_level is AgentAccessLevel.LIMITED
    assert allowance.limit == limited_allowance.limit
    assert allowance.remaining == 0


@pytest.mark.asyncio
async def test_verification_expands_the_same_lifetime_allowance(
    auth_service: AuthService,
    agent_usage_service: AgentUsageService,
    test_engine: AsyncEngine,
) -> None:
    user_id = await _register_user(auth_service, "quota-verification@example.com")
    before_verification = await agent_usage_service.get_allowance(user_id)
    assert before_verification.limit is not None
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
    assert allowance.limit is not None
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
    assert initial_allowance.limit is not None

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
