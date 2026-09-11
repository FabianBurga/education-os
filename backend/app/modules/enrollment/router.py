from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.enrollment.models import AcademicPeriod, Enrollment
from app.modules.students.models import StudentProfile

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
    student_profile_id: UUID
    academic_period_id: UUID
    campus_id: UUID
    enrollment_number: str | None = Field(default=None, max_length=64)
    status: str = Field(default="PENDING", pattern="^(PENDING|ACTIVE)$")
    enrolled_on: date | None = None


class EnrollmentStatusUpdate(BaseModel):
    status: str = Field(pattern="^(PENDING|ACTIVE|WITHDRAWN|COMPLETED|CANCELLED)$")
    withdrawn_on: date | None = None


class EnrollmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    institution_id: UUID
    student_profile_id: UUID
    academic_period_id: UUID
    campus_id: UUID
    enrollment_number: str | None
    status: str
    enrolled_on: date | None
    withdrawn_on: date | None


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
def list_enrollments(_: PrincipalDep, session: SessionDep):
    return session.exec(select(Enrollment).order_by(Enrollment.created_at.desc())).all()


@router.post("/enrollments", response_model=EnrollmentRead, status_code=201)
def create_enrollment(payload: EnrollmentCreate, principal: PrincipalDep, session: SessionDep):
    if session.get(StudentProfile, payload.student_profile_id) is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if session.get(AcademicPeriod, payload.academic_period_id) is None:
        raise HTTPException(status_code=404, detail="Academic period not found")
    campus = session.exec(
        text("SELECT id FROM campuses WHERE id = :campus_id").bindparams(
            campus_id=payload.campus_id
        )
    ).first()
    if campus is None:
        raise HTTPException(status_code=404, detail="Campus not found")
    enrollment = Enrollment(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(enrollment)
    session.commit()
    session.refresh(enrollment)
    return enrollment


@router.get("/enrollments/{enrollment_id}", response_model=EnrollmentRead)
def get_enrollment(enrollment_id: UUID, _: PrincipalDep, session: SessionDep):
    enrollment = session.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return enrollment


@router.patch("/enrollments/{enrollment_id}/status", response_model=EnrollmentRead)
def update_enrollment_status(
    enrollment_id: UUID,
    payload: EnrollmentStatusUpdate,
    _: PrincipalDep,
    session: SessionDep,
):
    enrollment = session.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    enrollment.status = payload.status
    enrollment.withdrawn_on = payload.withdrawn_on
    session.add(enrollment)
    session.commit()
    session.refresh(enrollment)
    return enrollment
