from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.audit.service import record_audit
from app.modules.events.service import enqueue_event
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
    StudentStatementSummary,
    VoidRequest,
)

MONEY_QUANT = Decimal("0.01")
CAPABILITY_KEY = "finance.billing"


def utcnow() -> datetime:
    return datetime.now(UTC)


def money(value) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _default_capability(institution_type: str) -> bool:
    return institution_type in {"PRIVATE", "FISCOMISIONAL"}


def capability_status(
    session: Session,
    principal: CurrentPrincipal,
) -> FinanceCapabilityRead:
    row = session.exec(
        text(
            """
            SELECT i.type, COALESCE(ic.enabled, false)
            FROM institutions i
            LEFT JOIN institution_capabilities ic
              ON ic.institution_id = i.id
             AND ic.capability_key = :capability_key
            WHERE i.id = CAST(:institution_id AS uuid)
              AND i.organization_id = CAST(:organization_id AS uuid)
            """
        ).bindparams(
            capability_key=CAPABILITY_KEY,
            institution_id=str(principal.institution_id),
            organization_id=str(principal.organization_id),
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Institution not found")

    return FinanceCapabilityRead(
        institution_id=principal.institution_id,
        institution_type=row[0],
        enabled=bool(row[1]),
        default_for_type=_default_capability(row[0]),
    )


def update_capability(
    session: Session,
    principal: CurrentPrincipal,
    payload: FinanceCapabilityUpdate,
) -> FinanceCapabilityRead:
    current = capability_status(session, principal)
    session.exec(
        text(
            """
            INSERT INTO institution_capabilities (
                institution_id,
                capability_key,
                enabled
            )
            VALUES (
                CAST(:institution_id AS uuid),
                :capability_key,
                :enabled
            )
            ON CONFLICT (institution_id, capability_key)
            DO UPDATE SET enabled = EXCLUDED.enabled
            """
        ).bindparams(
            institution_id=str(principal.institution_id),
            capability_key=CAPABILITY_KEY,
            enabled=payload.enabled,
        )
    )

    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="FINANCE_CAPABILITY_CHANGED",
        entity_type="institution_capability",
        entity_id=principal.institution_id,
        metadata={
            "capability_key": CAPABILITY_KEY,
            "previous_enabled": current.enabled,
            "enabled": payload.enabled,
        },
    )
    enqueue_event(
        session,
        institution_id=principal.institution_id,
        event_type="FINANCE_CAPABILITY_CHANGED",
        aggregate_type="institution",
        aggregate_id=principal.institution_id,
        payload={
            "capability_key": CAPABILITY_KEY,
            "previous_enabled": current.enabled,
            "enabled": payload.enabled,
        },
    )
    session.commit()
    return capability_status(session, principal)


def finance_summary(session: Session) -> FinanceSummary:
    row = session.exec(
        text(
            """
            WITH paid_by_charge AS (
                SELECT
                    ba.billing_charge_id,
                    COALESCE(SUM(ba.amount), 0) AS paid
                FROM billing_allocations ba
                JOIN billing_payments bp
                  ON bp.id = ba.billing_payment_id
                 AND bp.status = 'POSTED'
                GROUP BY ba.billing_charge_id
            ),
            charge_rollup AS (
                SELECT
                    bc.id,
                    bc.amount,
                    bc.due_on,
                    bc.status,
                    COALESCE(pbc.paid, 0) AS paid,
                    GREATEST(bc.amount - COALESCE(pbc.paid, 0), 0) AS balance
                FROM billing_charges bc
                LEFT JOIN paid_by_charge pbc
                  ON pbc.billing_charge_id = bc.id
                WHERE bc.status <> 'VOID'
            )
            SELECT
                (SELECT COUNT(*) FROM billing_accounts WHERE status = 'ACTIVE'),
                (SELECT COUNT(*) FROM billing_concepts WHERE status = 'ACTIVE'),
                COUNT(*) FILTER (WHERE cr.balance > 0),
                COUNT(*) FILTER (
                    WHERE cr.balance > 0
                      AND cr.due_on < CURRENT_DATE
                ),
                COALESCE(SUM(cr.amount), 0),
                COALESCE(SUM(cr.paid), 0),
                COALESCE(SUM(cr.balance), 0)
            FROM charge_rollup cr
            """
        )
    ).first()

    if row is None:
        return FinanceSummary(
            active_accounts=0,
            active_concepts=0,
            open_charges=0,
            overdue_charges=0,
            total_billed=money(0),
            total_paid=money(0),
            outstanding_balance=money(0),
        )

    return FinanceSummary(
        active_accounts=int(row[0] or 0),
        active_concepts=int(row[1] or 0),
        open_charges=int(row[2] or 0),
        overdue_charges=int(row[3] or 0),
        total_billed=money(row[4]),
        total_paid=money(row[5]),
        outstanding_balance=money(row[6]),
    )


def list_students(session: Session) -> list[FinanceStudentOption]:
    rows = session.exec(
        text(
            """
            SELECT DISTINCT ON (sp.id)
                sp.id,
                trim(concat_ws(' ', p.given_names, p.family_names)),
                gl.name,
                s.name,
                ap.name
            FROM student_profiles sp
            JOIN persons p ON p.id = sp.person_id
            LEFT JOIN enrollments e
              ON e.student_profile_id = sp.id
             AND e.status = 'ACTIVE'
            LEFT JOIN academic_periods ap ON ap.id = e.academic_period_id
            LEFT JOIN student_section_assignments ssa
              ON ssa.enrollment_id = e.id
             AND ssa.status = 'ACTIVE'
            LEFT JOIN sections s ON s.id = ssa.section_id
            LEFT JOIN grade_levels gl ON gl.id = s.grade_level_id
            WHERE sp.status = 'ACTIVE'
            ORDER BY sp.id, e.created_at DESC NULLS LAST
            """
        )
    ).all()
    return [
        FinanceStudentOption(
            student_profile_id=row[0],
            student_name=row[1],
            grade_name=row[2],
            section_name=row[3],
            academic_period_name=row[4],
        )
        for row in rows
    ]


def list_concepts(session: Session) -> list[BillingConceptRead]:
    rows = session.exec(
        text(
            """
            SELECT
                id,
                code,
                name,
                description,
                default_amount,
                currency,
                status,
                created_at,
                updated_at
            FROM billing_concepts
            ORDER BY
                CASE WHEN status = 'ACTIVE' THEN 0 ELSE 1 END,
                name
            """
        )
    ).all()
    return [
        BillingConceptRead(
            id=row[0],
            code=row[1],
            name=row[2],
            description=row[3],
            default_amount=money(row[4]),
            currency=row[5],
            status=row[6],
            created_at=row[7],
            updated_at=row[8],
        )
        for row in rows
    ]


def create_concept(
    session: Session,
    principal: CurrentPrincipal,
    payload: BillingConceptCreate,
) -> BillingConceptRead:
    duplicate = session.exec(
        text(
            """
            SELECT 1
            FROM billing_concepts
            WHERE code = :code
            LIMIT 1
            """
        ).bindparams(code=payload.code)
    ).first()
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Billing concept code already exists")

    concept_id = uuid4()
    now = utcnow()
    session.exec(
        text(
            """
            INSERT INTO billing_concepts (
                id,
                organization_id,
                institution_id,
                code,
                name,
                description,
                default_amount,
                currency,
                status,
                created_by_user_id,
                created_at,
                updated_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                :code,
                :name,
                :description,
                :default_amount,
                'USD',
                'ACTIVE',
                CAST(:created_by_user_id AS uuid),
                :created_at,
                :updated_at
            )
            """
        ).bindparams(
            id=str(concept_id),
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
            code=payload.code,
            name=payload.name,
            description=payload.description,
            default_amount=money(payload.default_amount),
            created_by_user_id=str(principal.user_id),
            created_at=now,
            updated_at=now,
        )
    )

    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="BILLING_CONCEPT_CREATED",
        entity_type="billing_concept",
        entity_id=concept_id,
        metadata={
            "code": payload.code,
            "default_amount": str(money(payload.default_amount)),
            "currency": "USD",
        },
    )
    session.commit()
    return next(item for item in list_concepts(session) if item.id == concept_id)


def update_concept(
    session: Session,
    principal: CurrentPrincipal,
    concept_id: UUID,
    payload: BillingConceptUpdate,
) -> BillingConceptRead:
    existing = session.exec(
        text(
            """
            SELECT id
            FROM billing_concepts
            WHERE id = CAST(:concept_id AS uuid)
            """
        ).bindparams(concept_id=str(concept_id))
    ).first()
    if existing is None:
        raise HTTPException(status_code=404, detail="Billing concept not found")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        return next(item for item in list_concepts(session) if item.id == concept_id)

    updates = []
    params: dict[str, object] = {"concept_id": str(concept_id), "updated_at": utcnow()}
    for field in ("name", "description", "default_amount", "status"):
        if field not in data:
            continue
        updates.append(f"{field} = :{field}")
        value = data[field]
        if field == "default_amount" and value is not None:
            value = money(value)
        params[field] = value

    updates.append("updated_at = :updated_at")
    session.exec(
        text(
            f"""
            UPDATE billing_concepts
            SET {", ".join(updates)}
            WHERE id = CAST(:concept_id AS uuid)
            """
        ).bindparams(**params)
    )

    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="BILLING_CONCEPT_UPDATED",
        entity_type="billing_concept",
        entity_id=concept_id,
        metadata={"fields": sorted(data)},
    )
    session.commit()
    return next(item for item in list_concepts(session) if item.id == concept_id)


def _student_row(
    session: Session,
    principal: CurrentPrincipal,
    student_profile_id: UUID,
):
    row = session.exec(
        text(
            """
            SELECT
                sp.id,
                trim(concat_ws(' ', p.given_names, p.family_names))
            FROM student_profiles sp
            JOIN persons p ON p.id = sp.person_id
            WHERE sp.id = CAST(:student_profile_id AS uuid)
              AND sp.organization_id = CAST(:organization_id AS uuid)
              AND sp.institution_id = CAST(:institution_id AS uuid)
              AND sp.status = 'ACTIVE'
            """
        ).bindparams(
            student_profile_id=str(student_profile_id),
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Active student not found")
    return row


def _ensure_account(
    session: Session,
    principal: CurrentPrincipal,
    student_profile_id: UUID,
) -> UUID:
    row = session.exec(
        text(
            """
            SELECT id, status
            FROM billing_accounts
            WHERE student_profile_id = CAST(:student_profile_id AS uuid)
            """
        ).bindparams(student_profile_id=str(student_profile_id))
    ).first()
    if row is not None:
        if row[1] != "ACTIVE":
            raise HTTPException(status_code=409, detail="Billing account is closed")
        return row[0]

    account_id = uuid4()
    session.exec(
        text(
            """
            INSERT INTO billing_accounts (
                id,
                organization_id,
                institution_id,
                student_profile_id,
                status,
                opened_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                CAST(:student_profile_id AS uuid),
                'ACTIVE',
                :opened_at
            )
            """
        ).bindparams(
            id=str(account_id),
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
            student_profile_id=str(student_profile_id),
            opened_at=utcnow(),
        )
    )
    return account_id


def _concept_row(
    session: Session,
    concept_id: UUID,
):
    row = session.exec(
        text(
            """
            SELECT id, code, name, default_amount, status
            FROM billing_concepts
            WHERE id = CAST(:concept_id AS uuid)
            """
        ).bindparams(concept_id=str(concept_id))
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Billing concept not found")
    if row[4] != "ACTIVE":
        raise HTTPException(status_code=409, detail="Billing concept is archived")
    return row


def _validate_period(
    session: Session,
    principal: CurrentPrincipal,
    academic_period_id: UUID | None,
) -> None:
    if academic_period_id is None:
        return
    row = session.exec(
        text(
            """
            SELECT 1
            FROM academic_periods
            WHERE id = CAST(:academic_period_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
            """
        ).bindparams(
            academic_period_id=str(academic_period_id),
            institution_id=str(principal.institution_id),
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Academic period not found")


def create_charge(
    session: Session,
    principal: CurrentPrincipal,
    payload: ChargeCreate,
) -> ChargeRead:
    _student_row(session, principal, payload.student_profile_id)
    concept = _concept_row(session, payload.billing_concept_id)
    _validate_period(session, principal, payload.academic_period_id)

    account_id = _ensure_account(
        session,
        principal,
        payload.student_profile_id,
    )
    amount = money(payload.amount if payload.amount is not None else concept[3])
    if amount <= 0:
        raise HTTPException(
            status_code=422,
            detail="Charge amount must be greater than zero",
        )

    charge_id = uuid4()
    now = utcnow()
    description = payload.description or concept[2]
    session.exec(
        text(
            """
            INSERT INTO billing_charges (
                id,
                organization_id,
                institution_id,
                billing_account_id,
                billing_concept_id,
                academic_period_id,
                description,
                amount,
                due_on,
                status,
                created_by_user_id,
                created_at,
                updated_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                CAST(:billing_account_id AS uuid),
                CAST(:billing_concept_id AS uuid),
                CAST(:academic_period_id AS uuid),
                :description,
                :amount,
                :due_on,
                'OPEN',
                CAST(:created_by_user_id AS uuid),
                :created_at,
                :updated_at
            )
            """
        ).bindparams(
            id=str(charge_id),
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
            billing_account_id=str(account_id),
            billing_concept_id=str(payload.billing_concept_id),
            academic_period_id=(
                str(payload.academic_period_id)
                if payload.academic_period_id is not None
                else None
            ),
            description=description,
            amount=amount,
            due_on=payload.due_on,
            created_by_user_id=str(principal.user_id),
            created_at=now,
            updated_at=now,
        )
    )

    event_payload = {
        "student_profile_id": str(payload.student_profile_id),
        "concept_code": concept[1],
        "amount": str(amount),
        "currency": "USD",
        "due_on": payload.due_on.isoformat(),
    }
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="BILLING_CHARGE_CREATED",
        entity_type="billing_charge",
        entity_id=charge_id,
        metadata=event_payload,
    )
    enqueue_event(
        session,
        institution_id=principal.institution_id,
        event_type="BILLING_CHARGE_CREATED",
        aggregate_type="billing_charge",
        aggregate_id=charge_id,
        payload=event_payload,
    )
    session.commit()

    charges = list_charges(
        session,
        principal,
        student_profile_id=payload.student_profile_id,
    )
    return next(item for item in charges if item.id == charge_id)


def list_charges(
    session: Session,
    principal: CurrentPrincipal,
    student_profile_id: UUID | None = None,
) -> list[ChargeRead]:
    params = {"institution_id": str(principal.institution_id)}
    student_filter = ""
    if student_profile_id is not None:
        _student_row(session, principal, student_profile_id)
        student_filter = "AND sp.id = CAST(:student_profile_id AS uuid)"
        params["student_profile_id"] = str(student_profile_id)

    rows = session.exec(
        text(
            f"""
            WITH paid_by_charge AS (
                SELECT
                    ba.billing_charge_id,
                    COALESCE(SUM(ba.amount), 0) AS paid
                FROM billing_allocations ba
                JOIN billing_payments bp
                  ON bp.id = ba.billing_payment_id
                 AND bp.status = 'POSTED'
                GROUP BY ba.billing_charge_id
            )
            SELECT
                bc.id,
                sp.id,
                trim(concat_ws(' ', p.given_names, p.family_names)),
                bcon.code,
                bcon.name,
                bc.description,
                bc.amount,
                COALESCE(pbc.paid, 0),
                GREATEST(bc.amount - COALESCE(pbc.paid, 0), 0),
                bc.due_on,
                bc.status,
                ap.name,
                bc.created_at
            FROM billing_charges bc
            JOIN billing_accounts acct ON acct.id = bc.billing_account_id
            JOIN student_profiles sp ON sp.id = acct.student_profile_id
            JOIN persons p ON p.id = sp.person_id
            JOIN billing_concepts bcon ON bcon.id = bc.billing_concept_id
            LEFT JOIN academic_periods ap ON ap.id = bc.academic_period_id
            LEFT JOIN paid_by_charge pbc ON pbc.billing_charge_id = bc.id
            WHERE bc.institution_id = CAST(:institution_id AS uuid)
              {student_filter}
            ORDER BY bc.due_on DESC, bc.created_at DESC
            """
        ).bindparams(**params)
    ).all()

    return [
        ChargeRead(
            id=row[0],
            student_profile_id=row[1],
            student_name=row[2],
            concept_code=row[3],
            concept_name=row[4],
            description=row[5],
            amount=money(row[6]),
            allocated_amount=money(row[7]),
            balance=money(row[8]),
            due_on=row[9],
            status=row[10],
            academic_period_name=row[11],
            created_at=row[12],
        )
        for row in rows
    ]


def _recalculate_charge_status(
    session: Session,
    charge_id: UUID,
) -> None:
    row = session.exec(
        text(
            """
            SELECT
                bc.amount,
                bc.status,
                COALESCE(SUM(ba.amount) FILTER (WHERE bp.status = 'POSTED'), 0)
            FROM billing_charges bc
            LEFT JOIN billing_allocations ba
              ON ba.billing_charge_id = bc.id
            LEFT JOIN billing_payments bp
              ON bp.id = ba.billing_payment_id
            WHERE bc.id = CAST(:charge_id AS uuid)
            GROUP BY bc.id, bc.amount, bc.status
            """
        ).bindparams(charge_id=str(charge_id))
    ).first()
    if row is None or row[1] == "VOID":
        return

    total = money(row[0])
    paid = money(row[2])
    if paid <= 0:
        status_value = "OPEN"
    elif paid < total:
        status_value = "PARTIAL"
    else:
        status_value = "PAID"

    session.exec(
        text(
            """
            UPDATE billing_charges
            SET status = :status,
                updated_at = :updated_at
            WHERE id = CAST(:charge_id AS uuid)
            """
        ).bindparams(
            status=status_value,
            updated_at=utcnow(),
            charge_id=str(charge_id),
        )
    )


def post_payment(
    session: Session,
    principal: CurrentPrincipal,
    payload: PaymentCreate,
) -> PaymentRead:
    _student_row(session, principal, payload.student_profile_id)
    account_id = _ensure_account(
        session,
        principal,
        payload.student_profile_id,
    )

    payment_amount = money(payload.amount)
    allocation_amount = money(
        sum((item.amount for item in payload.allocations), Decimal("0.00"))
    )
    if allocation_amount != payment_amount:
        raise HTTPException(
            status_code=422,
            detail="Payment amount must equal the total allocation amount",
        )

    charge_ids = [item.billing_charge_id for item in payload.allocations]
    if len(set(charge_ids)) != len(charge_ids):
        raise HTTPException(
            status_code=422,
            detail="Each charge can appear only once in a payment",
        )

    for item in payload.allocations:
        row = session.exec(
            text(
                """
                SELECT
                    bc.billing_account_id,
                    bc.amount,
                    bc.status,
                    COALESCE(
                        (
                            SELECT SUM(ba.amount)
                            FROM billing_allocations ba
                            JOIN billing_payments bp
                              ON bp.id = ba.billing_payment_id
                             AND bp.status = 'POSTED'
                            WHERE ba.billing_charge_id = bc.id
                        ),
                        0
                    ) AS paid
                FROM billing_charges bc
                WHERE bc.id = CAST(:charge_id AS uuid)
                FOR UPDATE
                """
            ).bindparams(charge_id=str(item.billing_charge_id))
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Billing charge not found")
        if row[0] != account_id:
            raise HTTPException(
                status_code=409,
                detail="All allocations must belong to the selected student account",
            )
        if row[2] == "VOID":
            raise HTTPException(
                status_code=409,
                detail="Cannot allocate a payment to a void charge",
            )
        remaining = money(row[1]) - money(row[3])
        allocation = money(item.amount)
        if allocation > remaining:
            raise HTTPException(
                status_code=409,
                detail="Payment allocation exceeds the remaining charge balance",
            )

    payment_id = uuid4()
    now = utcnow()
    session.exec(
        text(
            """
            INSERT INTO billing_payments (
                id,
                organization_id,
                institution_id,
                billing_account_id,
                amount,
                payment_method,
                reference,
                paid_at,
                status,
                posted_by_user_id,
                created_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                CAST(:billing_account_id AS uuid),
                :amount,
                :payment_method,
                :reference,
                :paid_at,
                'POSTED',
                CAST(:posted_by_user_id AS uuid),
                :created_at
            )
            """
        ).bindparams(
            id=str(payment_id),
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
            billing_account_id=str(account_id),
            amount=payment_amount,
            payment_method=payload.payment_method,
            reference=payload.reference,
            paid_at=payload.paid_at,
            posted_by_user_id=str(principal.user_id),
            created_at=now,
        )
    )

    for item in payload.allocations:
        session.exec(
            text(
                """
                INSERT INTO billing_allocations (
                    id,
                    organization_id,
                    institution_id,
                    billing_payment_id,
                    billing_charge_id,
                    amount,
                    created_at
                )
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:organization_id AS uuid),
                    CAST(:institution_id AS uuid),
                    CAST(:billing_payment_id AS uuid),
                    CAST(:billing_charge_id AS uuid),
                    :amount,
                    :created_at
                )
                """
            ).bindparams(
                id=str(uuid4()),
                organization_id=str(principal.organization_id),
                institution_id=str(principal.institution_id),
                billing_payment_id=str(payment_id),
                billing_charge_id=str(item.billing_charge_id),
                amount=money(item.amount),
                created_at=now,
            )
        )

    for charge_id in charge_ids:
        _recalculate_charge_status(session, charge_id)

    event_payload = {
        "student_profile_id": str(payload.student_profile_id),
        "amount": str(payment_amount),
        "currency": "USD",
        "payment_method": payload.payment_method,
        "allocation_count": len(payload.allocations),
    }
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="BILLING_PAYMENT_POSTED",
        entity_type="billing_payment",
        entity_id=payment_id,
        metadata=event_payload,
    )
    enqueue_event(
        session,
        institution_id=principal.institution_id,
        event_type="BILLING_PAYMENT_POSTED",
        aggregate_type="billing_payment",
        aggregate_id=payment_id,
        payload=event_payload,
    )
    session.commit()

    payments = list_payments(
        session,
        principal,
        student_profile_id=payload.student_profile_id,
    )
    return next(item for item in payments if item.id == payment_id)


def list_payments(
    session: Session,
    principal: CurrentPrincipal,
    student_profile_id: UUID | None = None,
) -> list[PaymentRead]:
    params = {"institution_id": str(principal.institution_id)}
    student_filter = ""
    if student_profile_id is not None:
        _student_row(session, principal, student_profile_id)
        student_filter = "AND sp.id = CAST(:student_profile_id AS uuid)"
        params["student_profile_id"] = str(student_profile_id)

    rows = session.exec(
        text(
            f"""
            SELECT
                bp.id,
                sp.id,
                trim(concat_ws(' ', p.given_names, p.family_names)),
                bp.amount,
                bp.payment_method,
                bp.reference,
                bp.paid_at,
                bp.status,
                COUNT(ba.id),
                bp.created_at
            FROM billing_payments bp
            JOIN billing_accounts acct ON acct.id = bp.billing_account_id
            JOIN student_profiles sp ON sp.id = acct.student_profile_id
            JOIN persons p ON p.id = sp.person_id
            LEFT JOIN billing_allocations ba
              ON ba.billing_payment_id = bp.id
            WHERE bp.institution_id = CAST(:institution_id AS uuid)
              {student_filter}
            GROUP BY
                bp.id,
                sp.id,
                p.given_names,
                p.family_names
            ORDER BY bp.paid_at DESC, bp.created_at DESC
            """
        ).bindparams(**params)
    ).all()

    return [
        PaymentRead(
            id=row[0],
            student_profile_id=row[1],
            student_name=row[2],
            amount=money(row[3]),
            payment_method=row[4],
            reference=row[5],
            paid_at=row[6],
            status=row[7],
            allocation_count=int(row[8] or 0),
            created_at=row[9],
        )
        for row in rows
    ]


def student_statement(
    session: Session,
    principal: CurrentPrincipal,
    student_profile_id: UUID,
) -> StudentStatement:
    student = _student_row(session, principal, student_profile_id)
    account = session.exec(
        text(
            """
            SELECT id
            FROM billing_accounts
            WHERE student_profile_id = CAST(:student_profile_id AS uuid)
            """
        ).bindparams(student_profile_id=str(student_profile_id))
    ).first()

    charges = list_charges(
        session,
        principal,
        student_profile_id=student_profile_id,
    )
    payments = list_payments(
        session,
        principal,
        student_profile_id=student_profile_id,
    )
    total_billed = money(
        sum(
            (
                item.amount
                for item in charges
                if item.status != "VOID"
            ),
            Decimal("0.00"),
        )
    )
    total_paid = money(
        sum(
            (
                item.allocated_amount
                for item in charges
                if item.status != "VOID"
            ),
            Decimal("0.00"),
        )
    )
    outstanding = money(total_billed - total_paid)

    return StudentStatement(
        summary=StudentStatementSummary(
            student_profile_id=student_profile_id,
            student_name=student[1],
            account_id=account[0] if account is not None else None,
            total_billed=total_billed,
            total_paid=total_paid,
            outstanding_balance=outstanding,
        ),
        charges=charges,
        payments=payments,
    )


def void_payment(
    session: Session,
    principal: CurrentPrincipal,
    payment_id: UUID,
    payload: VoidRequest,
) -> PaymentRead:
    row = session.exec(
        text(
            """
            SELECT
                bp.status,
                acct.student_profile_id,
                bp.amount
            FROM billing_payments bp
            JOIN billing_accounts acct ON acct.id = bp.billing_account_id
            WHERE bp.id = CAST(:payment_id AS uuid)
            FOR UPDATE
            """
        ).bindparams(payment_id=str(payment_id))
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Billing payment not found")
    if row[0] == "VOID":
        raise HTTPException(status_code=409, detail="Payment is already void")

    charge_rows = session.exec(
        text(
            """
            SELECT billing_charge_id
            FROM billing_allocations
            WHERE billing_payment_id = CAST(:payment_id AS uuid)
            """
        ).bindparams(payment_id=str(payment_id))
    ).all()
    charge_ids = [item[0] for item in charge_rows]

    now = utcnow()
    session.exec(
        text(
            """
            UPDATE billing_payments
            SET
                status = 'VOID',
                voided_by_user_id = CAST(:voided_by_user_id AS uuid),
                voided_at = :voided_at,
                void_reason = :void_reason
            WHERE id = CAST(:payment_id AS uuid)
            """
        ).bindparams(
            voided_by_user_id=str(principal.user_id),
            voided_at=now,
            void_reason=payload.reason,
            payment_id=str(payment_id),
        )
    )

    for charge_id in charge_ids:
        _recalculate_charge_status(session, charge_id)

    event_payload = {
        "amount": str(money(row[2])),
        "student_profile_id": str(row[1]),
        "reason": payload.reason,
    }
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="BILLING_PAYMENT_VOIDED",
        entity_type="billing_payment",
        entity_id=payment_id,
        metadata=event_payload,
    )
    enqueue_event(
        session,
        institution_id=principal.institution_id,
        event_type="BILLING_PAYMENT_VOIDED",
        aggregate_type="billing_payment",
        aggregate_id=payment_id,
        payload=event_payload,
    )
    session.commit()

    payments = list_payments(
        session,
        principal,
        student_profile_id=row[1],
    )
    return next(item for item in payments if item.id == payment_id)


def void_charge(
    session: Session,
    principal: CurrentPrincipal,
    charge_id: UUID,
    payload: VoidRequest,
) -> ChargeRead:
    row = session.exec(
        text(
            """
            SELECT
                bc.status,
                acct.student_profile_id,
                bc.amount,
                COALESCE(
                    (
                        SELECT SUM(ba.amount)
                        FROM billing_allocations ba
                        JOIN billing_payments bp
                          ON bp.id = ba.billing_payment_id
                         AND bp.status = 'POSTED'
                        WHERE ba.billing_charge_id = bc.id
                    ),
                    0
                )
            FROM billing_charges bc
            JOIN billing_accounts acct ON acct.id = bc.billing_account_id
            WHERE bc.id = CAST(:charge_id AS uuid)
            FOR UPDATE
            """
        ).bindparams(charge_id=str(charge_id))
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Billing charge not found")
    if row[0] == "VOID":
        raise HTTPException(status_code=409, detail="Charge is already void")
    if money(row[3]) > 0:
        raise HTTPException(
            status_code=409,
            detail="A charge with posted payment allocations cannot be voided",
        )

    now = utcnow()
    session.exec(
        text(
            """
            UPDATE billing_charges
            SET
                status = 'VOID',
                voided_by_user_id = CAST(:voided_by_user_id AS uuid),
                voided_at = :voided_at,
                void_reason = :void_reason,
                updated_at = :updated_at
            WHERE id = CAST(:charge_id AS uuid)
            """
        ).bindparams(
            voided_by_user_id=str(principal.user_id),
            voided_at=now,
            void_reason=payload.reason,
            updated_at=now,
            charge_id=str(charge_id),
        )
    )

    event_payload = {
        "amount": str(money(row[2])),
        "student_profile_id": str(row[1]),
        "reason": payload.reason,
    }
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="BILLING_CHARGE_VOIDED",
        entity_type="billing_charge",
        entity_id=charge_id,
        metadata=event_payload,
    )
    enqueue_event(
        session,
        institution_id=principal.institution_id,
        event_type="BILLING_CHARGE_VOIDED",
        aggregate_type="billing_charge",
        aggregate_id=charge_id,
        payload=event_payload,
    )
    session.commit()

    charges = list_charges(
        session,
        principal,
        student_profile_id=row[1],
    )
    return next(item for item in charges if item.id == charge_id)
