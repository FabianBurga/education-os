from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.grades.schemas import (
    AssessmentCategoryCreate,
    AssessmentCategoryRead,
    AssessmentCreate,
    AssessmentRead,
    GradeEntryRead,
    GradeEntryUpsert,
    GradingPeriodCreate,
    GradingPeriodRead,
    GradingScaleBandCreate,
    GradingScaleBandRead,
    GradingScaleCreate,
    GradingScaleRead,
)
from app.modules.grades.service import (
    add_scale_band,
    create_assessment,
    create_category,
    create_period,
    create_scale,
    list_assessments,
    list_categories,
    list_entries,
    list_periods,
    list_scales,
    upsert_entry,
)

router = APIRouter(prefix="/grades", tags=["grades"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/periods", response_model=list[GradingPeriodRead])
def periods_list(_: PrincipalDep, session: SessionDep):
    return list_periods(session)


@router.post("/periods", response_model=GradingPeriodRead, status_code=201)
def periods_create(
    payload: GradingPeriodCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return create_period(session, principal, payload)


@router.get("/scales", response_model=list[GradingScaleRead])
def scales_list(_: PrincipalDep, session: SessionDep):
    return list_scales(session)


@router.post("/scales", response_model=GradingScaleRead, status_code=201)
def scales_create(
    payload: GradingScaleCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return create_scale(session, principal, payload)


@router.post(
    "/scales/{scale_id}/bands",
    response_model=GradingScaleBandRead,
    status_code=201,
)
def scale_bands_create(
    scale_id: UUID,
    payload: GradingScaleBandCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return add_scale_band(session, principal, scale_id, payload)


@router.get("/categories", response_model=list[AssessmentCategoryRead])
def categories_list(_: PrincipalDep, session: SessionDep):
    return list_categories(session)


@router.post("/categories", response_model=AssessmentCategoryRead, status_code=201)
def categories_create(
    payload: AssessmentCategoryCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return create_category(session, principal, payload)


@router.get("/assessments", response_model=list[AssessmentRead])
def assessments_list(_: PrincipalDep, session: SessionDep):
    return list_assessments(session)


@router.post("/assessments", response_model=AssessmentRead, status_code=201)
def assessments_create(
    payload: AssessmentCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return create_assessment(session, principal, payload)


@router.get(
    "/assessments/{assessment_id}/entries",
    response_model=list[GradeEntryRead],
)
def entries_list(
    assessment_id: UUID,
    _: PrincipalDep,
    session: SessionDep,
):
    return list_entries(session, assessment_id)


@router.put(
    "/assessments/{assessment_id}/entries",
    response_model=GradeEntryRead,
)
def entries_upsert(
    assessment_id: UUID,
    payload: GradeEntryUpsert,
    principal: PrincipalDep,
    session: SessionDep,
):
    return upsert_entry(session, principal, assessment_id, payload)
