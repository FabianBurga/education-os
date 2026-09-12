from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Money = Decimal
PaymentMethod = Literal["CASH", "BANK_TRANSFER", "CARD", "OTHER"]


class FinanceCapabilityRead(BaseModel):
    institution_id: UUID
    institution_type: str
    capability_key: str = "finance.billing"
    enabled: bool
    default_for_type: bool


class FinanceCapabilityUpdate(BaseModel):
    enabled: bool


class FinanceSummary(BaseModel):
    active_accounts: int
    active_concepts: int
    open_charges: int
    overdue_charges: int
    total_billed: Money
    total_paid: Money
    outstanding_balance: Money


class BillingConceptCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=1000)
    default_amount: Money = Field(default=Decimal("0.00"), ge=0)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class BillingConceptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=1000)
    default_amount: Money | None = Field(default=None, ge=0)
    status: Literal["ACTIVE", "ARCHIVED"] | None = None


class BillingConceptRead(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    default_amount: Money
    currency: str
    status: str
    created_at: datetime
    updated_at: datetime


class FinanceStudentOption(BaseModel):
    student_profile_id: UUID
    student_name: str
    grade_name: str | None
    section_name: str | None
    academic_period_name: str | None


class ChargeCreate(BaseModel):
    student_profile_id: UUID
    billing_concept_id: UUID
    academic_period_id: UUID | None = None
    description: str | None = Field(default=None, max_length=500)
    amount: Money | None = Field(default=None, gt=0)
    due_on: date


class ChargeRead(BaseModel):
    id: UUID
    student_profile_id: UUID
    student_name: str
    concept_code: str
    concept_name: str
    description: str
    amount: Money
    allocated_amount: Money
    balance: Money
    due_on: date
    status: str
    academic_period_name: str | None
    created_at: datetime


class PaymentAllocationCreate(BaseModel):
    billing_charge_id: UUID
    amount: Money = Field(gt=0)


class PaymentCreate(BaseModel):
    student_profile_id: UUID
    amount: Money = Field(gt=0)
    payment_method: PaymentMethod
    reference: str | None = Field(default=None, max_length=160)
    paid_at: datetime
    allocations: list[PaymentAllocationCreate] = Field(min_length=1, max_length=50)


class PaymentRead(BaseModel):
    id: UUID
    student_profile_id: UUID
    student_name: str
    amount: Money
    payment_method: str
    reference: str | None
    paid_at: datetime
    status: str
    allocation_count: int
    created_at: datetime


class VoidRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class StudentStatementSummary(BaseModel):
    student_profile_id: UUID
    student_name: str
    account_id: UUID | None
    total_billed: Money
    total_paid: Money
    outstanding_balance: Money


class StudentStatement(BaseModel):
    summary: StudentStatementSummary
    charges: list[ChargeRead]
    payments: list[PaymentRead]
