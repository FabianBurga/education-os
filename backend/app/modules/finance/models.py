from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class BillingConcept(SQLModel, table=True):
    __tablename__ = "billing_concepts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    code: str = Field(max_length=50)
    name: str = Field(max_length=180)
    description: str | None = Field(default=None, max_length=1000)
    default_amount: Decimal = Decimal("0.00")
    currency: str = Field(default="USD", max_length=3)
    status: str = Field(default="ACTIVE", max_length=20)
    created_by_user_id: UUID | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BillingAccount(SQLModel, table=True):
    __tablename__ = "billing_accounts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    student_profile_id: UUID = Field(index=True)
    status: str = Field(default="ACTIVE", max_length=20)
    opened_at: datetime = Field(default_factory=utcnow)
    closed_at: datetime | None = None


class BillingCharge(SQLModel, table=True):
    __tablename__ = "billing_charges"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    billing_account_id: UUID = Field(index=True)
    billing_concept_id: UUID = Field(index=True)
    academic_period_id: UUID | None = Field(default=None, index=True)
    description: str = Field(max_length=500)
    amount: Decimal
    due_on: date
    status: str = Field(default="OPEN", max_length=20)
    created_by_user_id: UUID | None = None
    voided_by_user_id: UUID | None = None
    voided_at: datetime | None = None
    void_reason: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BillingPayment(SQLModel, table=True):
    __tablename__ = "billing_payments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    billing_account_id: UUID = Field(index=True)
    amount: Decimal
    payment_method: str = Field(max_length=30)
    reference: str | None = Field(default=None, max_length=160)
    paid_at: datetime
    status: str = Field(default="POSTED", max_length=20)
    posted_by_user_id: UUID | None = None
    voided_by_user_id: UUID | None = None
    voided_at: datetime | None = None
    void_reason: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=utcnow)


class BillingAllocation(SQLModel, table=True):
    __tablename__ = "billing_allocations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    billing_payment_id: UUID = Field(index=True)
    billing_charge_id: UUID = Field(index=True)
    amount: Decimal
    created_at: datetime = Field(default_factory=utcnow)
