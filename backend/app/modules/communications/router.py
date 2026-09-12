from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db.session import get_session
from app.modules.communications.schemas import (
    CommunicationCreate,
    CommunicationDeliveryReport,
    CommunicationDetail,
    CommunicationPreview,
    CommunicationPublishResult,
    CommunicationRead,
    CommunicationSummary,
    CommunicationTargetRead,
    CommunicationTargetsReplace,
    CommunicationTemplateCreate,
    CommunicationTemplateRead,
    CommunicationTemplateUpdate,
    CommunicationUpdate,
    TargetOption,
)
from app.modules.communications.security import (
    CommunicationsAccessDep,
    CommunicationsDeliveryDep,
    CommunicationsManageDep,
    CommunicationsPublishDep,
    CommunicationsTemplatesDep,
    CommunicationsViewDep,
)
from app.modules.communications.service import (
    archive_message,
    communication_summary,
    create_message,
    create_template,
    delivery_report,
    list_messages,
    list_templates,
    message_detail,
    preview_message,
    publish_message,
    replace_targets,
    target_options,
    update_message,
    update_template,
)

router = APIRouter(
    prefix="/communications",
    tags=["communications-center"],
)
SessionDep = Annotated[Session, Depends(get_session)]


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def communications_dashboard_html():
    path = Path(__file__).with_name("communications_dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/summary", response_model=CommunicationSummary)
def summary(_: CommunicationsAccessDep, session: SessionDep):
    return communication_summary(session)


@router.get(
    "/target-options",
    response_model=list[TargetOption],
)
def target_option_list(
    principal: CommunicationsViewDep,
    session: SessionDep,
    target_type: str = Query(
        pattern="^(INSTITUTION|CAMPUS|SECTION|COURSE|STUDENT|FAMILY)$"
    ),
):
    return target_options(session, principal, target_type)


@router.get(
    "/templates",
    response_model=list[CommunicationTemplateRead],
)
def template_list(_: CommunicationsViewDep, session: SessionDep):
    return list_templates(session)


@router.post(
    "/templates",
    response_model=CommunicationTemplateRead,
    status_code=201,
)
def template_create(
    payload: CommunicationTemplateCreate,
    principal: CommunicationsTemplatesDep,
    session: SessionDep,
):
    return create_template(session, principal, payload)


@router.patch(
    "/templates/{template_id}",
    response_model=CommunicationTemplateRead,
)
def template_update(
    template_id: UUID,
    payload: CommunicationTemplateUpdate,
    principal: CommunicationsTemplatesDep,
    session: SessionDep,
):
    return update_template(
        session,
        principal,
        template_id,
        payload,
    )


@router.get("/messages", response_model=list[CommunicationRead])
def message_list(_: CommunicationsViewDep, session: SessionDep):
    return list_messages(session)


@router.get(
    "/messages/{communication_id}",
    response_model=CommunicationDetail,
)
def message_get(
    communication_id: UUID,
    principal: CommunicationsViewDep,
    session: SessionDep,
):
    return message_detail(session, principal, communication_id)


@router.post(
    "/messages",
    response_model=CommunicationRead,
    status_code=201,
)
def message_create(
    payload: CommunicationCreate,
    principal: CommunicationsManageDep,
    session: SessionDep,
):
    return create_message(session, principal, payload)


@router.patch(
    "/messages/{communication_id}",
    response_model=CommunicationRead,
)
def message_update(
    communication_id: UUID,
    payload: CommunicationUpdate,
    principal: CommunicationsManageDep,
    session: SessionDep,
):
    return update_message(
        session,
        principal,
        communication_id,
        payload,
    )


@router.put(
    "/messages/{communication_id}/targets",
    response_model=list[CommunicationTargetRead],
)
def message_targets_replace(
    communication_id: UUID,
    payload: CommunicationTargetsReplace,
    principal: CommunicationsManageDep,
    session: SessionDep,
):
    return replace_targets(
        session,
        principal,
        communication_id,
        payload,
    )


@router.get(
    "/messages/{communication_id}/preview",
    response_model=CommunicationPreview,
)
def message_preview(
    communication_id: UUID,
    principal: CommunicationsViewDep,
    session: SessionDep,
):
    return preview_message(
        session,
        principal,
        communication_id,
    )


@router.post(
    "/messages/{communication_id}/publish",
    response_model=CommunicationPublishResult,
)
def message_publish(
    communication_id: UUID,
    principal: CommunicationsPublishDep,
    session: SessionDep,
):
    return publish_message(
        session,
        principal,
        communication_id,
    )


@router.post(
    "/messages/{communication_id}/archive",
    response_model=CommunicationRead,
)
def message_archive(
    communication_id: UUID,
    principal: CommunicationsManageDep,
    session: SessionDep,
):
    return archive_message(
        session,
        principal,
        communication_id,
    )


@router.get(
    "/messages/{communication_id}/delivery",
    response_model=CommunicationDeliveryReport,
)
def message_delivery(
    communication_id: UUID,
    principal: CommunicationsDeliveryDep,
    session: SessionDep,
):
    return delivery_report(
        session,
        principal,
        communication_id,
    )
