from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.accountability.metrics_schemas import (
    MetricExplanation,
    MetricResult,
    MetricSummary,
    OutcomeSummary,
)
from app.modules.accountability.metrics_service import (
    get_accountability_metric,
    get_accountability_metrics_summary,
    get_accountability_outcome_summary,
    get_metric_definition,
)

router = APIRouter(prefix="/accountability", tags=["accountability-metrics"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


def _window(start: datetime | None, end: datetime | None, kind: str) -> tuple[datetime, datetime]:
    current = datetime.now(UTC)
    if kind not in {"day", "week", "month", "custom"}:
        raise ValueError("unsupported aggregation window")
    return start or current - timedelta(
        days=1 if kind == "day" else 7 if kind == "week" else 30
    ), end or current


@router.get("/metrics", response_model=MetricSummary)
def metrics(
    principal: PrincipalDep,
    session: SessionDep,
    metric: list[str] | None = Query(default=None),
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    window: Literal["day", "week", "month", "custom"] = "custom",
    cohort_id: UUID | None = None,
) -> MetricSummary:
    start, end = _window(window_start, window_end, window)
    return get_accountability_metrics_summary(
        session,
        principal,
        metric_ids=tuple(metric) if metric else None,
        start=start,
        end=end,
        cohort_id=cohort_id,
    )


@router.get("/metrics/{metric_id}/definition", response_model=MetricExplanation)
def definition(metric_id: str) -> MetricExplanation:
    return get_metric_definition(metric_id.upper())


@router.get("/metrics/{metric_id}", response_model=MetricResult)
def metric(
    metric_id: str,
    principal: PrincipalDep,
    session: SessionDep,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    window: Literal["day", "week", "month", "custom"] = "custom",
    cohort_id: UUID | None = None,
) -> MetricResult:
    start, end = _window(window_start, window_end, window)
    return get_accountability_metric(
        session, principal, metric_id, start=start, end=end, cohort_id=cohort_id
    )


@router.get("/outcomes", response_model=OutcomeSummary)
def outcomes(
    principal: PrincipalDep,
    session: SessionDep,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    window: Literal["day", "week", "month", "custom"] = "custom",
    cohort_id: UUID | None = None,
) -> OutcomeSummary:
    start, end = _window(window_start, window_end, window)
    return get_accountability_outcome_summary(
        session, principal, start=start, end=end, cohort_id=cohort_id
    )
