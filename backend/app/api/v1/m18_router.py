from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.access import (
    require_admin_access,
    require_coordination_analytics,
)
from app.api.deps import CurrentPrincipal
from app.db.session import get_session
from app.modules.events.projection_service import (
    daily_read_model,
    platform_summary,
    recent_event_metadata,
    run_event_pipeline,
)

router = APIRouter(prefix="/event-platform", tags=["m18-event-platform"])


@router.get("/summary")
def event_platform_summary(
    principal: CurrentPrincipal = Depends(require_coordination_analytics),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return platform_summary(
        session,
        institution_id=principal.institution_id,
    )


@router.get("/events/recent")
def recent_events(
    limit: int = Query(default=50, ge=1, le=200),
    principal: CurrentPrincipal = Depends(require_coordination_analytics),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    return recent_event_metadata(
        session,
        institution_id=principal.institution_id,
        limit=limit,
    )


@router.get("/read-models/daily")
def read_model_daily(
    limit: int = Query(default=100, ge=1, le=500),
    principal: CurrentPrincipal = Depends(require_coordination_analytics),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    return daily_read_model(
        session,
        institution_id=principal.institution_id,
        limit=limit,
    )


@router.post("/pipeline/run")
def run_pipeline(
    limit: int = Query(default=1000, ge=1, le=5000),
    principal: CurrentPrincipal = Depends(require_admin_access),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    result = run_event_pipeline(
        session,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        limit=limit,
    )
    session.commit()
    return {
        "milestone": "M18",
        "platform_version": "0.18.0",
        **result,
    }
