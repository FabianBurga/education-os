from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.frontend_ui.schemas import (
    UiBootstrapRead,
    UiProfileContext,
    UiTenantContext,
    UiUserIdentity,
)


def ui_bootstrap(
    session: Session,
    principal: CurrentPrincipal,
) -> UiBootstrapRead:
    identity = session.exec(
        text(
            """
            SELECT
                ua.id,
                trim(concat_ws(' ', p.given_names, p.family_names)),
                ua.login_email
            FROM user_accounts ua
            JOIN persons p ON p.id = ua.person_id
            WHERE ua.id = CAST(:user_id AS uuid)
              AND ua.is_active = true
            """
        ).bindparams(user_id=str(principal.user_id))
    ).first()
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active user identity required",
        )

    tenant = session.exec(
        text(
            """
            SELECT
                o.id,
                o.name,
                i.id,
                i.name,
                i.type
            FROM institutions i
            JOIN organizations o ON o.id = i.organization_id
            WHERE i.id = CAST(:institution_id AS uuid)
              AND i.organization_id = CAST(:organization_id AS uuid)
            """
        ).bindparams(
            institution_id=str(principal.institution_id),
            organization_id=str(principal.organization_id),
        )
    ).first()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active institution context required",
        )

    role_rows = session.exec(
        text(
            """
            SELECT DISTINCT r.key
            FROM memberships m
            JOIN membership_roles mr ON mr.membership_id = m.id
            JOIN roles r ON r.id = mr.role_id
            WHERE m.user_id = CAST(:user_id AS uuid)
              AND m.institution_id = CAST(:institution_id AS uuid)
              AND m.status = 'ACTIVE'
            ORDER BY r.key
            """
        ).bindparams(
            user_id=str(principal.user_id),
            institution_id=str(principal.institution_id),
        )
    ).all()
    roles = [row[0] for row in role_rows]

    permission_rows = session.exec(
        text(
            """
            SELECT DISTINCT p.key
            FROM memberships m
            JOIN membership_roles mr ON mr.membership_id = m.id
            JOIN role_permissions rp ON rp.role_id = mr.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE m.user_id = CAST(:user_id AS uuid)
              AND m.institution_id = CAST(:institution_id AS uuid)
              AND m.status = 'ACTIVE'
            ORDER BY p.key
            """
        ).bindparams(
            user_id=str(principal.user_id),
            institution_id=str(principal.institution_id),
        )
    ).all()
    permissions = [row[0] for row in permission_rows]

    capability_rows = session.exec(
        text(
            """
            SELECT capability_key, enabled
            FROM institution_capabilities
            WHERE institution_id = CAST(:institution_id AS uuid)
            ORDER BY capability_key
            """
        ).bindparams(institution_id=str(principal.institution_id))
    ).all()
    capabilities = {
        row[0]: bool(row[1])
        for row in capability_rows
    }

    profile_row = session.exec(
        text(
            """
            SELECT
                EXISTS (
                    SELECT 1
                    FROM user_accounts ua
                    JOIN staff_profiles sp ON sp.person_id = ua.person_id
                    WHERE ua.id = CAST(:user_id AS uuid)
                      AND sp.institution_id = CAST(:institution_id AS uuid)
                      AND sp.status = 'ACTIVE'
                ),
                EXISTS (
                    SELECT 1
                    FROM user_accounts ua
                    JOIN student_profiles sp ON sp.person_id = ua.person_id
                    WHERE ua.id = CAST(:user_id AS uuid)
                      AND sp.institution_id = CAST(:institution_id AS uuid)
                      AND sp.status = 'ACTIVE'
                ),
                EXISTS (
                    SELECT 1
                    FROM user_accounts ua
                    JOIN guardian_profiles gp ON gp.person_id = ua.person_id
                    WHERE ua.id = CAST(:user_id AS uuid)
                      AND gp.institution_id = CAST(:institution_id AS uuid)
                      AND gp.status = 'ACTIVE'
                )
            """
        ).bindparams(
            user_id=str(principal.user_id),
            institution_id=str(principal.institution_id),
        )
    ).first()
    if profile_row is None:
        profile_row = (False, False, False)

    return UiBootstrapRead(
        user=UiUserIdentity(
            user_id=identity[0],
            display_name=identity[1],
            login_email=identity[2],
        ),
        tenant=UiTenantContext(
            organization_id=tenant[0],
            organization_name=tenant[1],
            institution_id=tenant[2],
            institution_name=tenant[3],
            institution_type=tenant[4],
        ),
        roles=roles,
        permissions=permissions,
        capabilities=capabilities,
        profiles=UiProfileContext(
            staff=bool(profile_row[0]),
            student=bool(profile_row[1]),
            guardian=bool(profile_row[2]),
        ),
    )
