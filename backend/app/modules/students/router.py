from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.students.models import StudentProfile

router = APIRouter(prefix="/students", tags=["students"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


class StudentCreate(BaseModel):
    person_id: UUID
    student_code: str | None = Field(default=None, max_length=64)


class StudentUpdate(BaseModel):
    student_code: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE|ARCHIVED)$")


class StudentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    institution_id: UUID
    person_id: UUID
    student_code: str | None
    status: str


def visible_person(session: Session, person_id: UUID) -> bool:
    row = session.exec(
        text("SELECT id FROM persons WHERE id = :person_id").bindparams(person_id=person_id)
    ).first()
    return row is not None


@router.get("", response_model=list[StudentRead])
def list_students(_: PrincipalDep, session: SessionDep):
    return session.exec(select(StudentProfile).order_by(StudentProfile.created_at.desc())).all()


@router.post("", response_model=StudentRead, status_code=201)
def create_student(payload: StudentCreate, principal: PrincipalDep, session: SessionDep):
    if not visible_person(session, payload.person_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found in current tenant",
        )
    student = StudentProfile(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        person_id=payload.person_id,
        student_code=payload.student_code,
    )
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


@router.get("/{student_id}", response_model=StudentRead)
def get_student(student_id: UUID, _: PrincipalDep, session: SessionDep):
    student = session.get(StudentProfile, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.patch("/{student_id}", response_model=StudentRead)
def update_student(
    student_id: UUID,
    payload: StudentUpdate,
    _: PrincipalDep,
    session: SessionDep,
):
    student = session.get(StudentProfile, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(student, key, value)
    session.add(student)
    session.commit()
    session.refresh(student)
    return student
