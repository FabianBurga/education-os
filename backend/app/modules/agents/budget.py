"""Append-only hard budget admission for governed provider execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.agents.models import AgentBudgetEvent, AgentRun
from app.modules.agents.provider_routing import RoutingDecision
from app.modules.agents.providers import ProviderFailureCode, ProviderGatewayError


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    per_run_microusd: int
    tenant_day_microusd: int
    tenant_month_microusd: int


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    reservation_key: str
    amount_microusd: int
    replayed: bool


def utc_budget_periods(now: datetime | None = None) -> tuple[datetime, datetime]:
    value = (now or datetime.now(UTC)).astimezone(UTC)
    day = value.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    return day, month


def _lock_key(institution_id: UUID, scope: str, period: datetime) -> str:
    return f"m25-budget:{institution_id}:{scope}:{period.isoformat()}"


def _take_period_lock(session: Session, institution_id: UUID, scope: str, period: datetime) -> None:
    """Transaction-scoped PostgreSQL advisory lock; released on commit/rollback."""
    session.exec(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        params={"key": _lock_key(institution_id, scope, period)},
    )


def _exposure(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    scope: str,
    period: datetime,
) -> int:
    rows = session.exec(
        select(AgentBudgetEvent.event_type, AgentBudgetEvent.amount_microusd).where(
            AgentBudgetEvent.organization_id == organization_id,
            AgentBudgetEvent.institution_id == institution_id,
            AgentBudgetEvent.budget_scope == scope,
            AgentBudgetEvent.period_start == period,
        )
    ).all()
    return sum(amount if event == "RESERVED" else -amount if event == "RELEASED" else 0 for event, amount in rows)


def _event_key(reservation_key: str, scope: str, event_type: str) -> str:
    return f"{reservation_key}:{scope}:{event_type}"


def budget_allows(*, current_exposure_microusd: int, requested_microusd: int, limit_microusd: int) -> bool:
    return (
        current_exposure_microusd >= 0
        and requested_microusd >= 0
        and limit_microusd >= 0
        and current_exposure_microusd + requested_microusd <= limit_microusd
    )


def _append_event(
    session: Session,
    principal: CurrentPrincipal,
    run: AgentRun,
    decision: RoutingDecision,
    *,
    scope: str,
    period: datetime,
    event_type: str,
    amount_microusd: int,
    reservation_key: str,
    provider_call_id: UUID | None = None,
) -> None:
    session.add(
        AgentBudgetEvent(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            agent_run_id=run.id,
            provider_call_id=provider_call_id,
            agent_key=run.agent_key,
            provider_key=decision.provider_key,
            model_key=decision.model_key,
            event_type=event_type,
            budget_scope=scope,
            period_start=period,
            amount_microusd=amount_microusd,
            idempotency_key=_event_key(reservation_key, scope, event_type),
            correlation_id=run.correlation_id,
        )
    )


def reserve_budget(
    session: Session,
    principal: CurrentPrincipal,
    *,
    run: AgentRun,
    decision: RoutingDecision,
    limits: BudgetLimits,
    reservation_key: str,
    now: datetime | None = None,
) -> BudgetReservation:
    """Atomically admit a reservation; caller commits or rolls back the transaction."""
    amount = decision.max_estimated_cost_microusd
    if amount < 0 or amount > limits.per_run_microusd:
        raise ProviderGatewayError(ProviderFailureCode.BUDGET_EXCEEDED)
    existing = session.exec(
        select(AgentBudgetEvent.id).where(
            AgentBudgetEvent.institution_id == principal.institution_id,
            AgentBudgetEvent.idempotency_key == _event_key(reservation_key, "RUN", "RESERVED"),
        )
    ).first()
    if existing is not None:
        return BudgetReservation(reservation_key=reservation_key, amount_microusd=amount, replayed=True)
    day, month = utc_budget_periods(now)
    for scope, period, limit in (("TENANT_DAY", day, limits.tenant_day_microusd), ("TENANT_MONTH", month, limits.tenant_month_microusd)):
        _take_period_lock(session, principal.institution_id, scope, period)
        if not budget_allows(
            current_exposure_microusd=_exposure(
                session, organization_id=principal.organization_id,
                institution_id=principal.institution_id, scope=scope, period=period,
            ),
            requested_microusd=amount,
            limit_microusd=limit,
        ):
            raise ProviderGatewayError(ProviderFailureCode.BUDGET_EXCEEDED)
    run_period = datetime(1970, 1, 1, tzinfo=UTC)
    for scope, period in (("RUN", run_period), ("TENANT_DAY", day), ("TENANT_MONTH", month)):
        _append_event(session, principal, run, decision, scope=scope, period=period, event_type="RESERVED", amount_microusd=amount, reservation_key=reservation_key)
    session.flush()
    return BudgetReservation(reservation_key=reservation_key, amount_microusd=amount, replayed=False)


def finalize_budget(
    session: Session,
    principal: CurrentPrincipal,
    *,
    run: AgentRun,
    decision: RoutingDecision,
    reservation: BudgetReservation,
    actual_cost_microusd: int,
    provider_call_id: UUID | None,
    now: datetime | None = None,
) -> None:
    if actual_cost_microusd < 0 or actual_cost_microusd > reservation.amount_microusd:
        raise ProviderGatewayError(ProviderFailureCode.BUDGET_EXCEEDED)
    existing = session.exec(
        select(AgentBudgetEvent.id).where(
            AgentBudgetEvent.institution_id == principal.institution_id,
            AgentBudgetEvent.idempotency_key == _event_key(reservation.reservation_key, "RUN", "CONSUMED"),
        )
    ).first()
    if existing is not None:
        return
    day, month = utc_budget_periods(now)
    release = reservation.amount_microusd - actual_cost_microusd
    run_period = datetime(1970, 1, 1, tzinfo=UTC)
    for scope, period in (("RUN", run_period), ("TENANT_DAY", day), ("TENANT_MONTH", month)):
        _append_event(session, principal, run, decision, scope=scope, period=period, event_type="CONSUMED", amount_microusd=actual_cost_microusd, reservation_key=reservation.reservation_key, provider_call_id=provider_call_id)
        if release:
            _append_event(session, principal, run, decision, scope=scope, period=period, event_type="RELEASED", amount_microusd=release, reservation_key=reservation.reservation_key, provider_call_id=provider_call_id)
    session.flush()


def release_budget(
    session: Session,
    principal: CurrentPrincipal,
    *,
    run: AgentRun,
    decision: RoutingDecision,
    reservation: BudgetReservation,
    now: datetime | None = None,
) -> None:
    finalize_budget(session, principal, run=run, decision=decision, reservation=reservation, actual_cost_microusd=0, provider_call_id=None, now=now)


def reservation_key_for(*, run_id: UUID, evidence_manifest_sha256: str, model_config_id: UUID) -> str:
    material = f"{run_id}:{evidence_manifest_sha256}:{model_config_id}"
    return sha256(material.encode("utf-8")).hexdigest()
