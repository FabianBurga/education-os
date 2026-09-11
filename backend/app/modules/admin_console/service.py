from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.core.security import hash_password
from app.modules.admin_console.schemas import (
    AccountAdminCreate,
    AccountAdminRead,
    AdminSummary,
    CampusAdminCreate,
    ChecklistItem,
    InstitutionAdminUpdate,
    OnboardingChecklist,
    PermissionAdminRead,
    PersonAdminCreate,
    RoleAdminCreate,
    RoleAdminRead,
    StaffAdminCreate,
    StaffAdminRead,
)
from app.modules.audit.models import AuditLog
from app.modules.families.models import StaffProfile
from app.modules.identity.models import Person, Role
from app.modules.tenancy.models import Campus, Institution


def _count(session: Session, sql: str) -> int:
    row = session.exec(text(sql)).first()
    return int(row[0] if row is not None else 0)


def _audit(
    session: Session,
    principal: CurrentPrincipal,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    metadata: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            institution_id=principal.institution_id,
            actor_user_id=principal.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=metadata or {},
        )
    )


def get_current_institution(
    session: Session,
    principal: CurrentPrincipal,
) -> Institution:
    entity = session.get(Institution, principal.institution_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    return entity


def update_current_institution(
    session: Session,
    principal: CurrentPrincipal,
    payload: InstitutionAdminUpdate,
) -> Institution:
    entity = get_current_institution(session, principal)
    changed = payload.model_dump(exclude_unset=True)
    for key, value in changed.items():
        setattr(entity, key, value)
    session.add(entity)
    _audit(
        session,
        principal,
        "ADMIN_INSTITUTION_UPDATED",
        "Institution",
        entity.id,
        {"fields": sorted(changed)},
    )
    session.commit()
    session.refresh(entity)
    return entity


def list_campuses(session: Session) -> list[Campus]:
    return session.exec(select(Campus).order_by(Campus.name)).all()


def create_campus(
    session: Session,
    principal: CurrentPrincipal,
    payload: CampusAdminCreate,
) -> Campus:
    entity = Campus(
        institution_id=principal.institution_id,
        name=payload.name.strip(),
    )
    session.add(entity)
    _audit(
        session,
        principal,
        "ADMIN_CAMPUS_CREATED",
        "Campus",
        entity.id,
        {"name": entity.name},
    )
    session.commit()
    session.refresh(entity)
    return entity


def list_people(session: Session) -> list[Person]:
    return session.exec(
        select(Person).order_by(Person.family_names, Person.given_names)
    ).all()


def create_person(
    session: Session,
    principal: CurrentPrincipal,
    payload: PersonAdminCreate,
) -> Person:
    entity = Person(
        organization_id=principal.organization_id,
        given_names=payload.given_names.strip(),
        family_names=payload.family_names.strip(),
        primary_email=payload.primary_email,
    )
    session.add(entity)
    _audit(
        session,
        principal,
        "ADMIN_PERSON_CREATED",
        "Person",
        entity.id,
        {"has_email": bool(entity.primary_email)},
    )
    session.commit()
    session.refresh(entity)
    return entity


def _account_row_to_read(row) -> AccountAdminRead:
    return AccountAdminRead(
        user_id=row[0],
        person_id=row[1],
        membership_id=row[2],
        login_email=row[3],
        is_active=bool(row[4]),
        status=row[5],
        roles=list(row[6] or []),
    )


def list_accounts(
    session: Session,
    principal: CurrentPrincipal,
) -> list[AccountAdminRead]:
    rows = session.exec(
        text(
            """
            SELECT ua.id,
                   ua.person_id,
                   m.id,
                   ua.login_email,
                   ua.is_active,
                   m.status,
                   COALESCE(
                     array_agg(r.key ORDER BY r.key)
                       FILTER (WHERE r.key IS NOT NULL),
                     ARRAY[]::varchar[]
                   ) AS roles
            FROM memberships m
            JOIN user_accounts ua ON ua.id = m.user_id
            LEFT JOIN membership_roles mr ON mr.membership_id = m.id
            LEFT JOIN roles r ON r.id = mr.role_id
            WHERE m.institution_id = CAST(:institution_id AS uuid)
            GROUP BY
                ua.id,
                ua.person_id,
                m.id,
                ua.login_email,
                ua.is_active,
                m.status
            ORDER BY ua.login_email
            """
        ).bindparams(institution_id=str(principal.institution_id))
    ).all()
    return [_account_row_to_read(row) for row in rows]


def create_account(
    session: Session,
    principal: CurrentPrincipal,
    payload: AccountAdminCreate,
) -> AccountAdminRead:
    person = session.get(Person, payload.person_id)
    if person is None:
        raise HTTPException(
            status_code=404,
            detail="Person not found in current organization",
        )

    current = session.exec(
        text(
            """
            SELECT ua.id, m.id
            FROM user_accounts ua
            JOIN memberships m ON m.user_id = ua.id
            WHERE ua.person_id = CAST(:person_id AS uuid)
              AND m.institution_id = CAST(:institution_id AS uuid)
            """
        ).bindparams(
            person_id=str(payload.person_id),
            institution_id=str(principal.institution_id),
        )
    ).first()
    if current is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Person already has an account membership in this institution",
        )

    user_id = uuid4()
    membership_id = uuid4()
    hashed = hash_password(payload.temporary_password)

    try:
        session.exec(
            text(
                """
                INSERT INTO user_accounts (
                    id,
                    person_id,
                    login_email,
                    password_hash,
                    is_active,
                    created_at
                )
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:person_id AS uuid),
                    :login_email,
                    :password_hash,
                    true,
                    now()
                )
                """
            ).bindparams(
                id=str(user_id),
                person_id=str(payload.person_id),
                login_email=payload.login_email.lower(),
                password_hash=hashed,
            )
        )
        session.exec(
            text(
                """
                INSERT INTO memberships (
                    id,
                    user_id,
                    institution_id,
                    status,
                    created_at
                )
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:user_id AS uuid),
                    CAST(:institution_id AS uuid),
                    'ACTIVE',
                    now()
                )
                """
            ).bindparams(
                id=str(membership_id),
                user_id=str(user_id),
                institution_id=str(principal.institution_id),
            )
        )
        _audit(
            session,
            principal,
            "ADMIN_ACCOUNT_CREATED",
            "UserAccount",
            user_id,
            {"membership_id": str(membership_id)},
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Account could not be created; "
                "login or person may already be registered"
            ),
        ) from exc

    return AccountAdminRead(
        user_id=user_id,
        person_id=payload.person_id,
        membership_id=membership_id,
        login_email=payload.login_email.lower(),
        is_active=True,
        status="ACTIVE",
        roles=[],
    )


def list_staff(session: Session) -> list[StaffAdminRead]:
    rows = session.exec(
        select(StaffProfile).order_by(StaffProfile.created_at.desc())
    ).all()
    return [
        StaffAdminRead(
            id=row.id,
            person_id=row.person_id,
            staff_code=row.staff_code,
            status=row.status,
        )
        for row in rows
    ]


def create_staff(
    session: Session,
    principal: CurrentPrincipal,
    payload: StaffAdminCreate,
) -> StaffAdminRead:
    if session.get(Person, payload.person_id) is None:
        raise HTTPException(status_code=404, detail="Person not found")

    entity = StaffProfile(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        person_id=payload.person_id,
        staff_code=payload.staff_code,
    )
    session.add(entity)
    _audit(
        session,
        principal,
        "ADMIN_STAFF_CREATED",
        "StaffProfile",
        entity.id,
        {"staff_code": payload.staff_code},
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Staff profile already exists for this person",
        ) from exc

    session.refresh(entity)
    return StaffAdminRead(
        id=entity.id,
        person_id=entity.person_id,
        staff_code=entity.staff_code,
        status=entity.status,
    )


def list_roles(
    session: Session,
    principal: CurrentPrincipal,
) -> list[RoleAdminRead]:
    rows = session.exec(
        text(
            """
            SELECT r.id,
                   r.key,
                   r.name,
                   COALESCE(
                     array_agg(p.key ORDER BY p.key)
                       FILTER (WHERE p.key IS NOT NULL),
                     ARRAY[]::varchar[]
                   )
            FROM roles r
            LEFT JOIN role_permissions rp ON rp.role_id = r.id
            LEFT JOIN permissions p ON p.id = rp.permission_id
            WHERE r.institution_id = CAST(:institution_id AS uuid)
            GROUP BY r.id, r.key, r.name
            ORDER BY r.key
            """
        ).bindparams(institution_id=str(principal.institution_id))
    ).all()
    return [
        RoleAdminRead(
            id=row[0],
            key=row[1],
            name=row[2],
            permissions=list(row[3] or []),
        )
        for row in rows
    ]


def create_role(
    session: Session,
    principal: CurrentPrincipal,
    payload: RoleAdminCreate,
) -> RoleAdminRead:
    entity = Role(
        institution_id=principal.institution_id,
        key=payload.key,
        name=payload.name,
    )
    session.add(entity)
    _audit(
        session,
        principal,
        "ADMIN_ROLE_CREATED",
        "Role",
        entity.id,
        {"key": payload.key},
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role key already exists in this institution",
        ) from exc

    session.refresh(entity)
    return RoleAdminRead(
        id=entity.id,
        key=entity.key,
        name=entity.name,
        permissions=[],
    )


def list_permissions(session: Session) -> list[PermissionAdminRead]:
    rows = session.exec(
        text("SELECT id, key, description FROM permissions ORDER BY key")
    ).all()
    return [
        PermissionAdminRead(id=row[0], key=row[1], description=row[2])
        for row in rows
    ]


def assign_role(
    session: Session,
    principal: CurrentPrincipal,
    membership_id: UUID,
    role_id: UUID,
) -> None:
    membership = session.exec(
        text(
            """
            SELECT id
            FROM memberships
            WHERE id = CAST(:membership_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
            """
        ).bindparams(
            membership_id=str(membership_id),
            institution_id=str(principal.institution_id),
        )
    ).first()
    role = session.exec(
        text(
            """
            SELECT id
            FROM roles
            WHERE id = CAST(:role_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
            """
        ).bindparams(
            role_id=str(role_id),
            institution_id=str(principal.institution_id),
        )
    ).first()
    if membership is None or role is None:
        raise HTTPException(
            status_code=404,
            detail="Membership or role not found",
        )

    session.exec(
        text(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (
                CAST(:membership_id AS uuid),
                CAST(:role_id AS uuid)
            )
            ON CONFLICT DO NOTHING
            """
        ).bindparams(
            membership_id=str(membership_id),
            role_id=str(role_id),
        )
    )
    _audit(
        session,
        principal,
        "ADMIN_ROLE_ASSIGNED",
        "Membership",
        membership_id,
        {"role_id": str(role_id)},
    )
    session.commit()


def assign_permission(
    session: Session,
    principal: CurrentPrincipal,
    role_id: UUID,
    permission_id: UUID,
) -> None:
    role = session.exec(
        text(
            """
            SELECT id
            FROM roles
            WHERE id = CAST(:role_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
            """
        ).bindparams(
            role_id=str(role_id),
            institution_id=str(principal.institution_id),
        )
    ).first()
    permission = session.exec(
        text(
            """
            SELECT id
            FROM permissions
            WHERE id = CAST(:permission_id AS uuid)
            """
        ).bindparams(permission_id=str(permission_id))
    ).first()
    if role is None or permission is None:
        raise HTTPException(
            status_code=404,
            detail="Role or permission not found",
        )

    session.exec(
        text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES (
                CAST(:role_id AS uuid),
                CAST(:permission_id AS uuid)
            )
            ON CONFLICT DO NOTHING
            """
        ).bindparams(
            role_id=str(role_id),
            permission_id=str(permission_id),
        )
    )
    _audit(
        session,
        principal,
        "ADMIN_PERMISSION_ASSIGNED",
        "Role",
        role_id,
        {"permission_id": str(permission_id)},
    )
    session.commit()


def admin_summary(session: Session) -> AdminSummary:
    return AdminSummary(
        people=_count(session, "SELECT COUNT(*) FROM persons"),
        users=_count(
            session,
            "SELECT COUNT(*) FROM memberships WHERE status='ACTIVE'",
        ),
        active_staff=_count(
            session,
            "SELECT COUNT(*) FROM staff_profiles WHERE status='ACTIVE'",
        ),
        active_students=_count(
            session,
            "SELECT COUNT(*) FROM student_profiles WHERE status='ACTIVE'",
        ),
        active_guardians=_count(
            session,
            "SELECT COUNT(*) FROM guardian_profiles WHERE status='ACTIVE'",
        ),
        campuses=_count(session, "SELECT COUNT(*) FROM campuses"),
        academic_periods=_count(
            session,
            "SELECT COUNT(*) FROM academic_periods",
        ),
        sections=_count(
            session,
            "SELECT COUNT(*) FROM sections WHERE status='ACTIVE'",
        ),
        subjects=_count(
            session,
            "SELECT COUNT(*) FROM subjects WHERE status='ACTIVE'",
        ),
        roles=_count(session, "SELECT COUNT(*) FROM roles"),
    )


def onboarding_checklist(session: Session) -> OnboardingChecklist:
    items = [
        ChecklistItem(
            key="campus",
            label="Campus configurado",
            ready=_count(session, "SELECT COUNT(*) FROM campuses") > 0,
            detail="Se requiere al menos un campus.",
        ),
        ChecklistItem(
            key="period",
            label="Período académico",
            ready=_count(
                session,
                """
                SELECT COUNT(*)
                FROM academic_periods
                WHERE status IN ('PLANNED','ACTIVE')
                """,
            )
            > 0,
            detail="Se requiere un período planificado o activo.",
        ),
        ChecklistItem(
            key="academic_structure",
            label="Estructura académica",
            ready=(
                _count(
                    session,
                    "SELECT COUNT(*) FROM academic_levels WHERE status='ACTIVE'",
                )
                > 0
                and _count(
                    session,
                    "SELECT COUNT(*) FROM grade_levels WHERE status='ACTIVE'",
                )
                > 0
                and _count(
                    session,
                    "SELECT COUNT(*) FROM subjects WHERE status='ACTIVE'",
                )
                > 0
            ),
            detail="Nivel, grado y asignatura deben existir.",
        ),
        ChecklistItem(
            key="staff",
            label="Personal activo",
            ready=_count(
                session,
                "SELECT COUNT(*) FROM staff_profiles WHERE status='ACTIVE'",
            )
            > 0,
            detail="Se requiere al menos un miembro de personal.",
        ),
        ChecklistItem(
            key="students",
            label="Estudiantes activos",
            ready=_count(
                session,
                "SELECT COUNT(*) FROM student_profiles WHERE status='ACTIVE'",
            )
            > 0,
            detail="Se requiere al menos un estudiante.",
        ),
        ChecklistItem(
            key="families",
            label="Representantes",
            ready=_count(
                session,
                "SELECT COUNT(*) FROM guardian_profiles WHERE status='ACTIVE'",
            )
            > 0,
            detail="Se recomienda al menos un representante activo.",
        ),
        ChecklistItem(
            key="sections",
            label="Secciones",
            ready=_count(
                session,
                "SELECT COUNT(*) FROM sections WHERE status='ACTIVE'",
            )
            > 0,
            detail="Se requiere al menos una sección activa.",
        ),
        ChecklistItem(
            key="system_admin",
            label="Administrador del sistema",
            ready=_count(
                session,
                """
                SELECT COUNT(*)
                FROM memberships m
                JOIN membership_roles mr ON mr.membership_id=m.id
                JOIN role_permissions rp ON rp.role_id=mr.role_id
                JOIN permissions p ON p.id=rp.permission_id
                WHERE m.status='ACTIVE'
                  AND p.key='admin.console.access'
                """,
            )
            > 0,
            detail="Debe existir una membresía con acceso administrativo.",
        ),
    ]
    ready_items = sum(1 for item in items if item.ready)
    total_items = len(items)
    completion = (
        round(100.0 * ready_items / total_items, 1)
        if total_items
        else 0.0
    )
    return OnboardingChecklist(
        ready_items=ready_items,
        total_items=total_items,
        completion_percent=completion,
        items=items,
    )
