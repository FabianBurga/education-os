from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InstitutionType(StrEnum):
    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"
    FISCOMISIONAL = "FISCOMISIONAL"
    MUNICIPAL = "MUNICIPAL"


class RecordStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Organization(SQLModel, table=True):
    __tablename__ = "organizations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=200, index=True)
    status: str = Field(default=RecordStatus.ACTIVE.value, max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class Institution(SQLModel, table=True):
    __tablename__ = "institutions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    name: str = Field(max_length=200, index=True)
    type: str = Field(default=InstitutionType.PRIVATE.value, max_length=30)
    status: str = Field(default=RecordStatus.ACTIVE.value, max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class Campus(SQLModel, table=True):
    __tablename__ = "campuses"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    institution_id: UUID = Field(foreign_key="institutions.id", index=True)
    name: str = Field(max_length=200)
    created_at: datetime = Field(default_factory=utcnow)


class InstitutionCapability(SQLModel, table=True):
    __tablename__ = "institution_capabilities"

    institution_id: UUID = Field(foreign_key="institutions.id", primary_key=True)
    capability_key: str = Field(primary_key=True, max_length=100)
    enabled: bool = True
