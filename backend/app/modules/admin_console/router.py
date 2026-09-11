from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.access import require_admin_access
from app.api.deps import CurrentPrincipal
from app.db.session import get_session
from app.modules.admin_console.schemas import (
    AccountAdminCreate,
    AccountAdminRead,
    AdminSummary,
    CampusAdminCreate,
    CampusAdminRead,
    InstitutionAdminRead,
    InstitutionAdminUpdate,
    OnboardingChecklist,
    PermissionAdminRead,
    PersonAdminCreate,
    PersonAdminRead,
    RoleAdminCreate,
    RoleAdminRead,
    StaffAdminCreate,
    StaffAdminRead,
)
from app.modules.admin_console.service import (
    admin_summary,
    assign_permission,
    assign_role,
    create_account,
    create_campus,
    create_person,
    create_role,
    create_staff,
    get_current_institution,
    list_accounts,
    list_campuses,
    list_people,
    list_permissions,
    list_roles,
    list_staff,
    onboarding_checklist,
    update_current_institution,
)

router = APIRouter(prefix="/admin", tags=["administrator-console"])
AdminPrincipalDep = Annotated[CurrentPrincipal, Depends(require_admin_access)]
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def administrator_dashboard_html():
    path = Path(__file__).with_name("admin_dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/summary", response_model=AdminSummary)
def summary(_: AdminPrincipalDep, session: SessionDep):
    return admin_summary(session)


@router.get("/institution", response_model=InstitutionAdminRead)
def institution_get(principal: AdminPrincipalDep, session: SessionDep):
    return get_current_institution(session, principal)


@router.patch("/institution", response_model=InstitutionAdminRead)
def institution_update(
    payload: InstitutionAdminUpdate,
    principal: AdminPrincipalDep,
    session: SessionDep,
):
    return update_current_institution(session, principal, payload)


@router.get("/campuses", response_model=list[CampusAdminRead])
def campuses_get(_: AdminPrincipalDep, session: SessionDep):
    return list_campuses(session)


@router.post("/campuses", response_model=CampusAdminRead, status_code=201)
def campuses_create(
    payload: CampusAdminCreate,
    principal: AdminPrincipalDep,
    session: SessionDep,
):
    return create_campus(session, principal, payload)


@router.get("/people", response_model=list[PersonAdminRead])
def people_get(_: AdminPrincipalDep, session: SessionDep):
    return list_people(session)


@router.post("/people", response_model=PersonAdminRead, status_code=201)
def people_create(
    payload: PersonAdminCreate,
    principal: AdminPrincipalDep,
    session: SessionDep,
):
    return create_person(session, principal, payload)


@router.get("/accounts", response_model=list[AccountAdminRead])
def accounts_get(principal: AdminPrincipalDep, session: SessionDep):
    return list_accounts(session, principal)


@router.post("/accounts", response_model=AccountAdminRead, status_code=201)
def accounts_create(
    payload: AccountAdminCreate,
    principal: AdminPrincipalDep,
    session: SessionDep,
):
    return create_account(session, principal, payload)


@router.get("/staff", response_model=list[StaffAdminRead])
def staff_get(_: AdminPrincipalDep, session: SessionDep):
    return list_staff(session)


@router.post("/staff", response_model=StaffAdminRead, status_code=201)
def staff_create(
    payload: StaffAdminCreate,
    principal: AdminPrincipalDep,
    session: SessionDep,
):
    return create_staff(session, principal, payload)


@router.get("/roles", response_model=list[RoleAdminRead])
def roles_get(principal: AdminPrincipalDep, session: SessionDep):
    return list_roles(session, principal)


@router.post("/roles", response_model=RoleAdminRead, status_code=201)
def roles_create(
    payload: RoleAdminCreate,
    principal: AdminPrincipalDep,
    session: SessionDep,
):
    return create_role(session, principal, payload)


@router.get("/permissions", response_model=list[PermissionAdminRead])
def permissions_get(_: AdminPrincipalDep, session: SessionDep):
    return list_permissions(session)


@router.post(
    "/memberships/{membership_id}/roles/{role_id}",
    status_code=204,
)
def membership_role_assign(
    membership_id: UUID,
    role_id: UUID,
    principal: AdminPrincipalDep,
    session: SessionDep,
):
    assign_role(session, principal, membership_id, role_id)


@router.post(
    "/roles/{role_id}/permissions/{permission_id}",
    status_code=204,
)
def role_permission_assign(
    role_id: UUID,
    permission_id: UUID,
    principal: AdminPrincipalDep,
    session: SessionDep,
):
    assign_permission(session, principal, role_id, permission_id)


@router.get("/onboarding-checklist", response_model=OnboardingChecklist)
def checklist(_: AdminPrincipalDep, session: SessionDep):
    return onboarding_checklist(session)
