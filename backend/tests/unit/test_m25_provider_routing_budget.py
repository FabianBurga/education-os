import os
from uuid import UUID, uuid4

import psycopg
import pytest

from app.api.deps import CurrentPrincipal
from app.modules.agents.budget import BudgetLimits, budget_allows, utc_budget_periods
from app.modules.agents.models import AgentModelRegistry
from app.modules.agents.provider_routing import (
    PROVIDER_OPTIONAL_POLICY,
    RoutingRequirements,
    select_deterministic_route,
)
from app.modules.agents.providers import (
    FakeProvider,
    ProviderAdapterRegistry,
    ProviderFailureCode,
    ProviderGatewayError,
    ProviderRequest,
)

ORG = UUID("dada4d4e-8854-5d09-8c21-c4516c06f5bb")
INST = UUID("ebda65b9-b77f-51d0-8263-f290fd0d24c0")
PRINCIPAL = CurrentPrincipal(user_id=uuid4(), organization_id=ORG, institution_id=INST)


def _model(*, priority: int = 1, status: str = "ENABLED", provider: str = "fake", cost: int = 100, context: int = 512) -> AgentModelRegistry:
    return AgentModelRegistry(
        organization_id=ORG, institution_id=INST, provider_key=provider, model_key=f"{provider}-{priority}",
        version=1, status=status, capability_class="EXPLANATION", routing_priority=priority,
        context_limit=context, max_input_tokens=256, max_output_tokens=128,
        max_estimated_cost_microusd=cost, timeout_seconds=5, max_attempts=1, max_fallbacks=0,
    )


def _requirements(*, cost: int = 100, input_tokens: int = 50, output_tokens: int = 50) -> RoutingRequirements:
    return RoutingRequirements("EXPLANATION", input_tokens, output_tokens, cost)


def test_router_is_deterministic_and_filters_disabled_wrong_tenant_and_limits():
    disabled = _model(priority=0, status="DISABLED")
    wrong_tenant = _model(priority=0)
    wrong_tenant.institution_id = uuid4()
    selected = _model(priority=2)
    too_small = _model(priority=1, context=80)
    decision = select_deterministic_route(
        principal=PRINCIPAL, provider_policy=PROVIDER_OPTIONAL_POLICY,
        requirements=_requirements(), candidates=[disabled, wrong_tenant, selected, too_small],
    )
    assert decision.model_config_id == selected.id
    assert decision.provider_key == "fake"


def test_router_requires_closed_provider_policy_and_cost_ceiling():
    with pytest.raises(ProviderGatewayError) as error:
        select_deterministic_route(principal=PRINCIPAL, provider_policy="DETERMINISTIC_ONLY", requirements=_requirements(), candidates=[_model()])
    assert error.value.code == ProviderFailureCode.POLICY_BLOCK
    with pytest.raises(ProviderGatewayError):
        select_deterministic_route(principal=PRINCIPAL, provider_policy=PROVIDER_OPTIONAL_POLICY, requirements=_requirements(cost=99), candidates=[_model(cost=100)])


def test_budget_periods_are_utc_day_and_month_boundaries():
    day, month = utc_budget_periods()
    assert day.tzinfo is not None and day.hour == 0
    assert month.day == 1 and month.hour == 0
    assert BudgetLimits(100, 200, 300).tenant_month_microusd == 300


def test_crossing_limit_admits_exactly_one_reservation():
    assert budget_allows(current_exposure_microusd=0, requested_microusd=60, limit_microusd=100)
    assert not budget_allows(current_exposure_microusd=60, requested_microusd=60, limit_microusd=100)


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("SUCCESS", None), ("MALFORMED_RESPONSE", None), ("FABRICATED_CITATION", None),
        ("TIMEOUT", ProviderFailureCode.TIMEOUT), ("RATE_LIMIT", ProviderFailureCode.RATE_LIMIT),
        ("UNAVAILABLE", ProviderFailureCode.UNAVAILABLE), ("AUTH_ERROR", ProviderFailureCode.AUTH),
        ("CONTEXT_TOO_LARGE", ProviderFailureCode.CONTEXT_TOO_LARGE),
    ],
)
def test_fake_provider_is_deterministic_and_never_networks(outcome, expected):
    fake = FakeProvider(outcome=outcome)
    request = ProviderRequest("a" * 64, "b" * 64, {}, 128)
    if expected is None:
        assert isinstance(fake.invoke(request).payload, dict)
    else:
        with pytest.raises(ProviderGatewayError) as error:
            fake.invoke(request)
        assert error.value.code == expected
    assert fake.calls == 1


def test_closed_provider_registry_blocks_known_but_unimplemented_adapters():
    registry = ProviderAdapterRegistry(fake=FakeProvider())
    assert registry.resolve("fake")
    for provider in ("openai", "anthropic", "local", "unknown"):
        with pytest.raises(ProviderGatewayError) as error:
            registry.resolve(provider)
        assert error.value.code == ProviderFailureCode.POLICY_BLOCK


def test_budget_source_uses_advisory_transaction_lock_and_append_only_events():
    from pathlib import Path

    source = (Path(__file__).parents[2] / "app" / "modules" / "agents" / "budget.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in source
    assert "RESERVED" in source and "CONSUMED" in source and "RELEASED" in source
    assert "session.add(\n        AgentBudgetEvent" in source
    assert ".update(" not in source and "delete(" not in source.lower()


def test_postgres_advisory_lock_excludes_concurrent_tenant_period_admission():
    database_url = os.getenv(
        "DATABASE_URL_PG",
        "postgresql://education_app:education_app_dev@127.0.0.1:5432/education_os",
    )
    lock_key = "m25-3b-test:tenant-period"
    with psycopg.connect(database_url) as first, psycopg.connect(database_url) as second:
        with first.cursor() as first_cursor, second.cursor() as second_cursor:
            first_cursor.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
            assert first_cursor.fetchone() == (True,)
            second_cursor.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
            assert second_cursor.fetchone() == (False,)
        first.rollback()
        with second.cursor() as second_cursor:
            second_cursor.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
            assert second_cursor.fetchone() == (True,)
