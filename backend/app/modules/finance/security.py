from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session

CAPABILITY_KEY = "finance.billing"


def _staff_permission_exists(
    session: Session,
    principal: CurrentPrincipal,
    permission_key: str,
) -> bool:
    row = session.exec(
        text(
            """
            SELECT 1
            FROM user_accounts ua
            JOIN staff_profiles sp
              ON sp.person_id = ua.person_id
             AND sp.institution_id = CAST(:institution_id AS uuid)
             AND sp.status = 'ACTIVE'
            JOIN memberships m
              ON m.user_id = ua.id
             AND m.institution_id = CAST(:institution_id AS uuid)
             AND m.status = 'ACTIVE'
            JOIN membership_roles mr ON mr.membership_id = m.id
            JOIN role_permissions rp ON rp.role_id = mr.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE ua.id = CAST(:user_id AS uuid)
              AND ua.is_active = true
              AND p.key = :permission_key
            LIMIT 1
            """
        ).bindparams(
            user_id=str(principal.user_id),
            institution_id=str(principal.institution_id),
            permission_key=permission_key,
        )
    ).first()
    return row is not None


def finance_capability_enabled(
    session: Session,
    principal: CurrentPrincipal,
) -> bool:
    row = session.exec(
        text(
            """
            SELECT enabled
            FROM institution_capabilities
            WHERE institution_id = CAST(:institution_id AS uuid)
              AND capability_key = :capability_key
            """
        ).bindparams(
            institution_id=str(principal.institution_id),
            capability_key=CAPABILITY_KEY,
        )
    ).first()
    return bool(row is not None and row[0])


def _require(
    session: Session,
    principal: CurrentPrincipal,
    permission_key: str,
    detail: str,
    *,
    require_capability: bool = True,
) -> CurrentPrincipal:
    if not _staff_permission_exists(
        session,
        principal,
        permission_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )
    if require_capability and not finance_capability_enabled(
        session,
        principal,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Finance / Billing capability is disabled for this institution",
        )
    return principal


def require_finance_console(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require(
        session,
        principal,
        "finance.console.access",
        "Finance Console permission required",
        require_capability=False,
    )


def require_finance_summary(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require(
        session,
        principal,
        "finance.summary.view",
        "Finance summary permission required",
    )


def require_finance_concepts(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require(
        session,
        principal,
        "finance.concepts.manage",
        "Finance concept-management permission required",
    )


def require_finance_charges(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require(
        session,
        principal,
        "finance.charges.manage",
        "Finance charge-management permission required",
    )


def require_finance_payments(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require(
        session,
        principal,
        "finance.payments.manage",
        "Finance payment-management permission required",
    )


def require_finance_statements(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require(
        session,
        principal,
        "finance.statements.view",
        "Finance statement-view permission required",
    )


def require_finance_reversals(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require(
        session,
        principal,
        "finance.reversals.manage",
        "Finance reversal-management permission required",
    )


def require_finance_capability_manage(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    return _require(
        session,
        principal,
        "finance.capability.manage",
        "Finance capability-management permission required",
        require_capability=False,
    )


FinanceConsoleDep = Annotated[
    CurrentPrincipal,
    Depends(require_finance_console),
]
FinanceSummaryDep = Annotated[
    CurrentPrincipal,
    Depends(require_finance_summary),
]
FinanceConceptsDep = Annotated[
    CurrentPrincipal,
    Depends(require_finance_concepts),
]
FinanceChargesDep = Annotated[
    CurrentPrincipal,
    Depends(require_finance_charges),
]
FinancePaymentsDep = Annotated[
    CurrentPrincipal,
    Depends(require_finance_payments),
]
FinanceStatementsDep = Annotated[
    CurrentPrincipal,
    Depends(require_finance_statements),
]
FinanceReversalsDep = Annotated[
    CurrentPrincipal,
    Depends(require_finance_reversals),
]
FinanceCapabilityManageDep = Annotated[
    CurrentPrincipal,
    Depends(require_finance_capability_manage),
]
