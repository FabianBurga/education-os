from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db.session import get_session
from app.modules.finance.schemas import (
    BillingConceptCreate,
    BillingConceptRead,
    BillingConceptUpdate,
    ChargeCreate,
    ChargeRead,
    FinanceCapabilityRead,
    FinanceCapabilityUpdate,
    FinanceStudentOption,
    FinanceSummary,
    PaymentCreate,
    PaymentRead,
    StudentStatement,
    VoidRequest,
)
from app.modules.finance.security import (
    FinanceCapabilityManageDep,
    FinanceChargesDep,
    FinanceConceptsDep,
    FinanceConsoleDep,
    FinancePaymentsDep,
    FinanceReversalsDep,
    FinanceStatementsDep,
    FinanceSummaryDep,
)
from app.modules.finance.service import (
    capability_status,
    create_charge,
    create_concept,
    finance_summary,
    list_charges,
    list_concepts,
    list_payments,
    list_students,
    post_payment,
    student_statement,
    update_capability,
    update_concept,
    void_charge,
    void_payment,
)

router = APIRouter(
    prefix="/finance",
    tags=["finance-billing"],
)
SessionDep = Annotated[Session, Depends(get_session)]


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def finance_dashboard_html():
    path = Path(__file__).with_name("finance_dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/capability", response_model=FinanceCapabilityRead)
def capability_get(
    principal: FinanceConsoleDep,
    session: SessionDep,
):
    return capability_status(session, principal)


@router.put("/capability", response_model=FinanceCapabilityRead)
def capability_update(
    payload: FinanceCapabilityUpdate,
    principal: FinanceCapabilityManageDep,
    session: SessionDep,
):
    return update_capability(session, principal, payload)


@router.get("/summary", response_model=FinanceSummary)
def summary(_: FinanceSummaryDep, session: SessionDep):
    return finance_summary(session)


@router.get("/students", response_model=list[FinanceStudentOption])
def students(_: FinanceStatementsDep, session: SessionDep):
    return list_students(session)


@router.get("/concepts", response_model=list[BillingConceptRead])
def concepts(_: FinanceSummaryDep, session: SessionDep):
    return list_concepts(session)


@router.post(
    "/concepts",
    response_model=BillingConceptRead,
    status_code=201,
)
def concept_create(
    payload: BillingConceptCreate,
    principal: FinanceConceptsDep,
    session: SessionDep,
):
    return create_concept(session, principal, payload)


@router.patch(
    "/concepts/{concept_id}",
    response_model=BillingConceptRead,
)
def concept_update(
    concept_id: UUID,
    payload: BillingConceptUpdate,
    principal: FinanceConceptsDep,
    session: SessionDep,
):
    return update_concept(
        session,
        principal,
        concept_id,
        payload,
    )


@router.get("/charges", response_model=list[ChargeRead])
def charges(
    principal: FinanceStatementsDep,
    session: SessionDep,
    student_profile_id: UUID | None = Query(default=None),
):
    return list_charges(
        session,
        principal,
        student_profile_id=student_profile_id,
    )


@router.post(
    "/charges",
    response_model=ChargeRead,
    status_code=201,
)
def charge_create(
    payload: ChargeCreate,
    principal: FinanceChargesDep,
    session: SessionDep,
):
    return create_charge(session, principal, payload)


@router.post(
    "/charges/{charge_id}/void",
    response_model=ChargeRead,
)
def charge_void(
    charge_id: UUID,
    payload: VoidRequest,
    principal: FinanceReversalsDep,
    session: SessionDep,
):
    return void_charge(
        session,
        principal,
        charge_id,
        payload,
    )


@router.get("/payments", response_model=list[PaymentRead])
def payments(
    principal: FinanceStatementsDep,
    session: SessionDep,
    student_profile_id: UUID | None = Query(default=None),
):
    return list_payments(
        session,
        principal,
        student_profile_id=student_profile_id,
    )


@router.post(
    "/payments",
    response_model=PaymentRead,
    status_code=201,
)
def payment_create(
    payload: PaymentCreate,
    principal: FinancePaymentsDep,
    session: SessionDep,
):
    return post_payment(session, principal, payload)


@router.post(
    "/payments/{payment_id}/void",
    response_model=PaymentRead,
)
def payment_void(
    payment_id: UUID,
    payload: VoidRequest,
    principal: FinanceReversalsDep,
    session: SessionDep,
):
    return void_payment(
        session,
        principal,
        payment_id,
        payload,
    )


@router.get(
    "/statements/{student_profile_id}",
    response_model=StudentStatement,
)
def statement(
    student_profile_id: UUID,
    principal: FinanceStatementsDep,
    session: SessionDep,
):
    return student_statement(
        session,
        principal,
        student_profile_id,
    )
