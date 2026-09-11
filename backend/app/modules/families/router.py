from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.families.models import (
    FamilyHousehold,
    FamilyMember,
    GuardianProfile,
    StudentGuardianRelationship,
)
from app.modules.students.models import StudentProfile

router = APIRouter(tags=["families"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


class GuardianCreate(BaseModel):
    person_id: UUID
    guardian_code: str | None = Field(default=None, max_length=64)


class GuardianRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    institution_id: UUID
    person_id: UUID
    guardian_code: str | None
    status: str


class FamilyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class FamilyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    institution_id: UUID
    name: str
    status: str


class FamilyMemberCreate(BaseModel):
    person_id: UUID
    member_role: str = Field(pattern="^(STUDENT|GUARDIAN|OTHER)$")
    relationship_label: str | None = Field(default=None, max_length=40)


class FamilyMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    family_id: UUID
    person_id: UUID
    member_role: str
    relationship_label: str | None


class GuardianLinkCreate(BaseModel):
    student_profile_id: UUID
    guardian_profile_id: UUID
    relationship_type: str = Field(min_length=1, max_length=40)
    is_legal_guardian: bool = False
    is_primary_contact: bool = False
    lives_with_student: bool = False
    pickup_authorized: bool = False
    emergency_contact: bool = False


class GuardianLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    student_profile_id: UUID
    guardian_profile_id: UUID
    relationship_type: str
    is_legal_guardian: bool
    is_primary_contact: bool
    lives_with_student: bool
    pickup_authorized: bool
    emergency_contact: bool


def visible_person(session: Session, person_id: UUID) -> bool:
    row = session.exec(
        text("SELECT id FROM persons WHERE id = :person_id").bindparams(person_id=person_id)
    ).first()
    return row is not None


@router.get("/guardians", response_model=list[GuardianRead])
def list_guardians(_: PrincipalDep, session: SessionDep):
    return session.exec(select(GuardianProfile).order_by(GuardianProfile.created_at.desc())).all()


@router.post("/guardians", response_model=GuardianRead, status_code=201)
def create_guardian(payload: GuardianCreate, principal: PrincipalDep, session: SessionDep):
    if not visible_person(session, payload.person_id):
        raise HTTPException(status_code=404, detail="Person not found in current tenant")
    guardian = GuardianProfile(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        person_id=payload.person_id,
        guardian_code=payload.guardian_code,
    )
    session.add(guardian)
    session.commit()
    session.refresh(guardian)
    return guardian


@router.get("/families", response_model=list[FamilyRead])
def list_families(_: PrincipalDep, session: SessionDep):
    return session.exec(select(FamilyHousehold).order_by(FamilyHousehold.created_at.desc())).all()


@router.post("/families", response_model=FamilyRead, status_code=201)
def create_family(payload: FamilyCreate, principal: PrincipalDep, session: SessionDep):
    family = FamilyHousehold(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        name=payload.name,
    )
    session.add(family)
    session.commit()
    session.refresh(family)
    return family


@router.post("/families/{family_id}/members", response_model=FamilyMemberRead, status_code=201)
def add_family_member(
    family_id: UUID,
    payload: FamilyMemberCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    family = session.get(FamilyHousehold, family_id)
    if family is None or not visible_person(session, payload.person_id):
        raise HTTPException(status_code=404, detail="Family or person not found")
    member = FamilyMember(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        family_id=family_id,
        **payload.model_dump(),
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


@router.post("/student-guardian-links", response_model=GuardianLinkRead, status_code=201)
def link_student_guardian(
    payload: GuardianLinkCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    if session.get(StudentProfile, payload.student_profile_id) is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if session.get(GuardianProfile, payload.guardian_profile_id) is None:
        raise HTTPException(status_code=404, detail="Guardian not found")
    link = StudentGuardianRelationship(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(link)
    session.commit()
    session.refresh(link)
    return link
