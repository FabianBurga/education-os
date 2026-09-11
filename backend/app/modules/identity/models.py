from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Person(SQLModel, table=True):
    __tablename__ = "persons"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    given_names: str = Field(max_length=160)
    family_names: str = Field(max_length=160)
    primary_email: str | None = Field(default=None, max_length=320)
    created_at: datetime = Field(default_factory=utcnow)


class UserAccount(SQLModel, table=True):
    __tablename__ = "user_accounts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    person_id: UUID = Field(foreign_key="persons.id", unique=True, index=True)
    login_email: str = Field(max_length=320, unique=True, index=True)
    password_hash: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class Membership(SQLModel, table=True):
    __tablename__ = "memberships"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user_accounts.id", index=True)
    institution_id: UUID = Field(foreign_key="institutions.id", index=True)
    status: str = Field(default="ACTIVE", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class Role(SQLModel, table=True):
    __tablename__ = "roles"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    institution_id: UUID = Field(foreign_key="institutions.id", index=True)
    key: str = Field(max_length=100)
    name: str = Field(max_length=160)


class Permission(SQLModel, table=True):
    __tablename__ = "permissions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    key: str = Field(max_length=160, unique=True, index=True)
    description: str = Field(max_length=500)


class RolePermission(SQLModel, table=True):
    __tablename__ = "role_permissions"

    role_id: UUID = Field(foreign_key="roles.id", primary_key=True)
    permission_id: UUID = Field(foreign_key="permissions.id", primary_key=True)


class MembershipRole(SQLModel, table=True):
    __tablename__ = "membership_roles"

    membership_id: UUID = Field(foreign_key="memberships.id", primary_key=True)
    role_id: UUID = Field(foreign_key="roles.id", primary_key=True)
