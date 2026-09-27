from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from app.api.access import (
    require_student_identity_management,
    require_student_record_permission,
)
from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.identity.models import Person
from app.modules.students.models import StudentProfile
from app.modules.students.service import (
    create_student_profile,
    get_student_in_scope,
    update_student_profile,
)

router = APIRouter(prefix="/students", tags=["students"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


class StudentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person_id: UUID
    student_code: str | None = Field(default=None, max_length=64)


class StudentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_code: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE|ARCHIVED)$")
    expected_updated_at: datetime


class StudentRecordRead(BaseModel):
    id: UUID
    display_name: str
    student_code: str | None
    status: str
    updated_at: datetime


class StudentRecordPage(BaseModel):
    items: list[StudentRecordRead]
    next_cursor: UUID | None


def _record(session: Session, student: StudentProfile) -> StudentRecordRead:
    person = session.get(Person, student.person_id)
    if person is None or person.organization_id != student.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return StudentRecordRead(
        id=student.id,
        display_name=f"{person.given_names} {person.family_names}".strip(),
        student_code=student.student_code,
        status=student.status,
        updated_at=student.updated_at,
    )


@router.get("/records", response_model=StudentRecordPage)
def list_student_records(
    principal: PrincipalDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
):
    require_student_record_permission(session, principal, "students.read")
    statement = (
        select(StudentProfile, Person.given_names, Person.family_names)
        .join(Person, Person.id == StudentProfile.person_id)
        .where(
            StudentProfile.organization_id == principal.organization_id,
            StudentProfile.institution_id == principal.institution_id,
            Person.organization_id == principal.organization_id,
        )
    )
    if cursor is not None:
        anchor = session.exec(
            select(StudentProfile).where(
                StudentProfile.id == cursor,
                StudentProfile.organization_id == principal.organization_id,
                StudentProfile.institution_id == principal.institution_id,
            )
        ).first()
        if anchor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cursor not found")
        statement = statement.where(
            (StudentProfile.created_at < anchor.created_at)
            | (
                (StudentProfile.created_at == anchor.created_at)
                & (StudentProfile.id < anchor.id)
            )
        )
    rows = session.exec(
        statement.order_by(StudentProfile.created_at.desc(), StudentProfile.id.desc()).limit(limit + 1)
    ).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    return StudentRecordPage(
        items=[
            StudentRecordRead(
                id=student.id,
                display_name=f"{given_names} {family_names}".strip(),
                student_code=student.student_code,
                status=student.status,
                updated_at=student.updated_at,
            )
            for student, given_names, family_names in page
        ],
        next_cursor=page[-1][0].id if has_more and page else None,
    )


@router.get("", response_model=list[StudentRecordRead])
def list_students(
    principal: PrincipalDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
):
    require_student_record_permission(session, principal, "students.read")
    rows = session.exec(
        select(StudentProfile, Person.given_names, Person.family_names)
        .join(Person, Person.id == StudentProfile.person_id)
        .where(
            StudentProfile.organization_id == principal.organization_id,
            StudentProfile.institution_id == principal.institution_id,
            Person.organization_id == principal.organization_id,
        )
        .order_by(StudentProfile.created_at.desc(), StudentProfile.id.desc())
        .limit(limit)
    ).all()
    return [
        StudentRecordRead(
            id=student.id,
            display_name=f"{given_names} {family_names}".strip(),
            student_code=student.student_code,
            status=student.status,
            updated_at=student.updated_at,
        )
        for student, given_names, family_names in rows
    ]


@router.post("", response_model=StudentRecordRead, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate,
    response: Response,
    principal: PrincipalDep,
    session: SessionDep,
):
    require_student_record_permission(session, principal, "students.manage")
    require_student_identity_management(session, principal)
    student, created = create_student_profile(
        session,
        principal,
        person_id=payload.person_id,
        student_code=payload.student_code,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replay"] = "true"
    session.commit()
    session.refresh(student)
    return _record(session, student)


@router.get("/{student_id}", response_model=StudentRecordRead)
def get_student(student_id: UUID, principal: PrincipalDep, session: SessionDep):
    require_student_record_permission(session, principal, "students.read")
    return _record(session, get_student_in_scope(session, principal, student_id))


@router.patch("/{student_id}", response_model=StudentRecordRead)
def update_student(
    student_id: UUID,
    payload: StudentUpdate,
    principal: PrincipalDep,
    session: SessionDep,
):
    changes = payload.model_dump(exclude={"expected_updated_at"}, exclude_unset=True)
    student = update_student_profile(
        session,
        principal,
        student_id,
        changes,
        expected_updated_at=payload.expected_updated_at,
    )
    session.commit()
    session.refresh(student)
    return _record(session, student)
