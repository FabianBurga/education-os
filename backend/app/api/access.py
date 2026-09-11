from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session


@dataclass(frozen=True, slots=True)
class GuardianPrincipal:
    user_id: UUID
    organization_id: UUID
    institution_id: UUID
    person_id: UUID
    guardian_profile_id: UUID


def _person_id_for_user(session: Session, user_id: UUID) -> UUID:
    row = session.exec(
        text(
            """
            SELECT person_id
            FROM user_accounts
            WHERE id = CAST(:user_id AS uuid) AND is_active = true
            """
        ).bindparams(user_id=str(user_id))
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active user account not found in signed context",
        )
    return row[0]


def require_staff_access(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> CurrentPrincipal:
    person_id = _person_id_for_user(session, principal.user_id)
    row = session.exec(
        text(
            """
            SELECT id
            FROM staff_profiles
            WHERE person_id = CAST(:person_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND status = 'ACTIVE'
            """
        ).bindparams(
            person_id=str(person_id),
            institution_id=str(principal.institution_id),
        )
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active staff profile required",
        )
    return principal


def get_guardian_principal(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> GuardianPrincipal:
    person_id = _person_id_for_user(session, principal.user_id)
    row = session.exec(
        text(
            """
            SELECT id
            FROM guardian_profiles
            WHERE person_id = CAST(:person_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND status = 'ACTIVE'
            """
        ).bindparams(
            person_id=str(person_id),
            institution_id=str(principal.institution_id),
        )
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active guardian profile required",
        )

    return GuardianPrincipal(
        user_id=principal.user_id,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        person_id=person_id,
        guardian_profile_id=row[0],
    )


GuardianPrincipalDep = Annotated[GuardianPrincipal, Depends(get_guardian_principal)]
