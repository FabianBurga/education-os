from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.enrollment.models import AcademicPeriod, Enrollment
from app.modules.enrollment.service import (
    available_enrollment_actions,
    create_enrollment_record,
    enrollment_history,
    get_period_in_scope,
    require_enrollment_permission,
    transition_enrollment,
)
from app.modules.students.models import StudentProfile
from app.modules.tenancy.models import Campus, Institution

router = APIRouter(tags=["enrollment"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


class PeriodCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    starts_on: date
    ends_on: date
    status: str = Field(default="PLANNED", pattern="^(PLANNED|ACTIVE|CLOSED)$")

    @model_validator(mode="after")
    def dates_are_valid(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        return self


class PeriodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    institution_id: UUID
    code: str
    name: str
    starts_on: date
    ends_on: date
    status: str


class EnrollmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_profile_id: UUID
    academic_period_id: UUID
    campus_id: UUID
    enrollment_number: str | None = Field(default=None, max_length=64)
    status: str = Field(default="PENDING", pattern="^(PENDING|ACTIVE)$")
    enrolled_on: date | None = None


class EnrollmentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(ACTIVE|WITHDRAWN|COMPLETED|CANCELLED)$")
    expected_updated_at: datetime
    effective_on: date | None = None
    reason_code: str | None = Field(default=None, pattern="^[A-Z][A-Z0-9_]{1,39}$")


class EnrollmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    institution_id: UUID
    student_profile_id: UUID
    academic_period_id: UUID
    academic_period_code: str
    academic_period_name: str
    campus_id: UUID
    enrollment_number: str | None
    status: str
    enrolled_on: date | None
    withdrawn_on: date | None
    updated_at: datetime
    allowed_actions: list[str]


class EnrollmentHistoryRead(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    action: str
    created_at: datetime
    details: dict


class EnrollmentPeriodOption(BaseModel):
    id: UUID
    code: str
    name: str
    starts_on: date
    ends_on: date
    status: str


class EnrollmentCampusOption(BaseModel):
    id: UUID
    name: str


class EnrollmentOptionsRead(BaseModel):
    periods: list[EnrollmentPeriodOption]
    campuses: list[EnrollmentCampusOption]


def _read(enrollment: Enrollment, period: AcademicPeriod) -> EnrollmentRead:
    return EnrollmentRead.model_validate({
        **{field: getattr(enrollment, field) for field in (
            "id", "organization_id", "institution_id", "student_profile_id",
            "academic_period_id", "campus_id", "enrollment_number", "status",
            "enrolled_on", "withdrawn_on", "updated_at",
        )},
        "academic_period_code": period.code,
        "academic_period_name": period.name,
        "allowed_actions": available_enrollment_actions(enrollment),
    })


@router.get("/academic-periods", response_model=list[PeriodRead])
def list_periods(_: PrincipalDep, session: SessionDep):
    return session.exec(select(AcademicPeriod).order_by(AcademicPeriod.starts_on.desc())).all()


@router.post("/academic-periods", response_model=PeriodRead, status_code=201)
def create_period(payload: PeriodCreate, principal: PrincipalDep, session: SessionDep):
    period = AcademicPeriod(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(period)
    session.commit()
    session.refresh(period)
    return period


@router.get("/enrollments", response_model=list[EnrollmentRead])
def list_enrollments(
    principal: PrincipalDep,
    session: SessionDep,
    student_profile_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    require_enrollment_permission(session, principal, "enrollments.read")
    statement = select(Enrollment, AcademicPeriod).join(
        AcademicPeriod, AcademicPeriod.id == Enrollment.academic_period_id,
    ).where(
        Enrollment.organization_id == principal.organization_id,
        Enrollment.institution_id == principal.institution_id,
    )
    if student_profile_id is not None:
        student = session.exec(select(StudentProfile.id).where(
            StudentProfile.id == student_profile_id,
            StudentProfile.organization_id == principal.organization_id,
            StudentProfile.institution_id == principal.institution_id,
        )).first()
        if student is None:
            raise HTTPException(status_code=404, detail="Student not found")
        statement = statement.where(Enrollment.student_profile_id == student_profile_id)
    enrollments = session.exec(statement.order_by(Enrollment.created_at.desc(), Enrollment.id).limit(limit)).all()
    return [_read(item, period) for item, period in enrollments]


@router.get("/enrollments/options", response_model=EnrollmentOptionsRead)
def enrollment_options(principal: PrincipalDep, session: SessionDep):
    require_enrollment_permission(session, principal, "enrollments.read")
    periods = session.exec(select(AcademicPeriod).where(
        AcademicPeriod.organization_id == principal.organization_id,
        AcademicPeriod.institution_id == principal.institution_id,
        AcademicPeriod.status.in_(["PLANNED", "ACTIVE"]),
    ).order_by(AcademicPeriod.starts_on.desc(), AcademicPeriod.id)).all()
    campuses = session.exec(select(Campus).join(
        Institution, Campus.institution_id == Institution.id,
    ).where(
        Campus.institution_id == principal.institution_id,
        Institution.organization_id == principal.organization_id,
    ).order_by(Campus.name, Campus.id)).all()
    return EnrollmentOptionsRead(
        periods=[EnrollmentPeriodOption.model_validate({
            "id": period.id, "code": period.code, "name": period.name,
            "starts_on": period.starts_on, "ends_on": period.ends_on, "status": period.status,
        }) for period in periods],
        campuses=[EnrollmentCampusOption(id=campus.id, name=campus.name) for campus in campuses],
    )


@router.post("/enrollments", response_model=EnrollmentRead, status_code=201)
def create_enrollment(payload: EnrollmentCreate, principal: PrincipalDep, session: SessionDep):
    enrollment = create_enrollment_record(session, principal, student_profile_id=payload.student_profile_id,
        academic_period_id=payload.academic_period_id, campus_id=payload.campus_id,
        enrollment_number=payload.enrollment_number, status_value=payload.status, enrolled_on=payload.enrolled_on)
    session.commit()
    session.refresh(enrollment)
    return _read(enrollment, get_period_in_scope(session, principal, enrollment.academic_period_id))


@router.get("/enrollments/{enrollment_id}", response_model=EnrollmentRead)
def get_enrollment(enrollment_id: UUID, principal: PrincipalDep, session: SessionDep):
    require_enrollment_permission(session, principal, "enrollments.read")
    enrollment = session.exec(select(Enrollment).where(
        Enrollment.id == enrollment_id,
        Enrollment.organization_id == principal.organization_id,
        Enrollment.institution_id == principal.institution_id,
    )).first()
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return _read(enrollment, get_period_in_scope(session, principal, enrollment.academic_period_id))


@router.get("/enrollments/{enrollment_id}/history", response_model=list[EnrollmentHistoryRead])
def get_enrollment_history(enrollment_id: UUID, principal: PrincipalDep, session: SessionDep):
    return [EnrollmentHistoryRead(
        id=item.id, actor_user_id=item.actor_user_id, action=item.action,
        created_at=item.created_at, details=item.metadata_json,
    ) for item in enrollment_history(session, principal, enrollment_id)]


@router.patch("/enrollments/{enrollment_id}/status", response_model=EnrollmentRead)
def update_enrollment_status(
    enrollment_id: UUID,
    payload: EnrollmentStatusUpdate,
    principal: PrincipalDep,
    session: SessionDep,
):
    enrollment = transition_enrollment(
        session, principal, enrollment_id,
        target_status=payload.status,
        expected_updated_at=payload.expected_updated_at,
        effective_on=payload.effective_on,
        reason_code=payload.reason_code,
    )
    session.commit()
    session.refresh(enrollment)
    return _read(enrollment, get_period_in_scope(session, principal, enrollment.academic_period_id))
