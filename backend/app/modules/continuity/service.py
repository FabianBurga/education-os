"""M29-2 presentation orchestration over authorized source domains."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.accountability.acknowledgement_evidence import (
    read_obligation_acknowledgement_batch,
)
from app.modules.accountability.continuity_reads import (
    list_authorized_obligation_targets,
)
from app.modules.interventions.acknowledgement_evidence import (
    read_followup_acknowledgement_batch,
)
from app.modules.interventions.continuity_reads import (
    list_authorized_followup_targets,
)
from app.modules.m21_access import has_permission
from app.security.trusted_context import batch_operation_key

from .schemas import ContinuityItemRead, ContinuityWorklistRead


def _sort_key(item: ContinuityItemRead) -> tuple[int, datetime, str, str]:
    due = item.due_at or datetime.max.replace(tzinfo=None)
    if due.tzinfo is not None:
        due = due.replace(tzinfo=None)
    overdue = 0 if item.due_at is not None and item.due_at < datetime.now(item.due_at.tzinfo) else 1
    return overdue, due, item.source_domain, str(item.source_id)


def get_continuity_worklist(
    session: Session,
    principal: CurrentPrincipal,
    *,
    limit: int = 25,
) -> ContinuityWorklistRead:
    bounded_limit = max(1, min(int(limit), 25))
    followups = list_authorized_followup_targets(
        session, principal, limit=bounded_limit
    )
    obligations = list_authorized_obligation_targets(
        session, principal, limit=bounded_limit
    )

    m21_evidence: dict[UUID, dict[str, object]] = {}
    if followups and has_permission(session, principal, "communications.delivery.view"):
        followup_ids = [row["target_id"] for row in followups]
        rows = read_followup_acknowledgement_batch(
            session,
            principal,
            followup_ids=followup_ids,
            idempotency_key=batch_operation_key(
                principal=principal,
                purpose="M21_ACK_BATCH_READ",
                target_ids=followup_ids,
            ),
        )
        m21_evidence = {row["target_id"]: row for row in rows}

    m27_evidence: dict[UUID, dict[str, object]] = {}
    if obligations and has_permission(session, principal, "communications.delivery.view"):
        obligation_ids = [row["target_id"] for row in obligations]
        rows = read_obligation_acknowledgement_batch(
            session,
            principal,
            obligation_ids=obligation_ids,
            idempotency_key=batch_operation_key(
                principal=principal,
                purpose="M27_ACK_BATCH_READ",
                target_ids=obligation_ids,
            ),
        )
        m27_evidence = {row["target_id"]: row for row in rows}

    items: list[ContinuityItemRead] = []
    for row in followups:
        evidence = m21_evidence.get(row["target_id"], {})
        items.append(
            ContinuityItemRead(
                source_domain="M21",
                source_id=row["target_id"],
                student_profile_id=row["student_profile_id"],
                kind="FOLLOW_UP",
                source_state=row["source_state"],
                due_at=row["due_at"],
                family_acknowledgement_indicator=bool(
                    evidence.get("acknowledgement_evidence_present", False)
                ),
                linked_at=evidence.get("linked_at"),
                deep_link=f"/m21/interventions/{row['intervention_id']}",
            )
        )
    for row in obligations:
        evidence = m27_evidence.get(row["target_id"], {})
        items.append(
            ContinuityItemRead(
                source_domain="M27",
                source_id=row["target_id"],
                student_profile_id=row["student_profile_id"],
                kind="OBLIGATION",
                source_state=row["source_state"],
                due_at=row["due_at"],
                family_acknowledgement_indicator=bool(
                    evidence.get("acknowledgement_evidence_present", False)
                ),
                linked_at=evidence.get("linked_at"),
                deep_link=f"/accountability/cases/{row['case_id']}",
            )
        )

    items.sort(key=_sort_key)
    has_more = len(items) > bounded_limit
    return ContinuityWorklistRead(items=items[:bounded_limit], has_more=has_more)
