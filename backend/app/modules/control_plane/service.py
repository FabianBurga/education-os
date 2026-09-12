from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.core.config import settings
from app.modules.audit.service import record_audit
from app.modules.control_plane.schemas import (
    CapabilityControlRead,
    CapabilityControlUpdate,
    ControlChangeRead,
    ControlPlaneHealth,
    ControlPlaneSummary,
    PolicyControlRead,
    PolicyControlUpdate,
)
from app.modules.events.service import enqueue_canonical_event

POLICY_KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,119}$")
FORBIDDEN_POLICY_KEY_RE = re.compile(
    r"(password|secret|token|api[_-]?key|credential|private[_-]?key)",
    re.IGNORECASE,
)
MAX_POLICY_BYTES = 16_384
PROJECTION_KEY = "institution_activity_v1"


def _reason(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A control-plane change reason of at least 3 characters is required",
        )
    return normalized


def _validate_policy_key(policy_key: str) -> str:
    normalized = policy_key.strip()
    if not POLICY_KEY_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "policy_key must match ^[a-z][a-z0-9_.-]{2,119}$"
            ),
        )
    return normalized


def _assert_no_secret_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            if FORBIDDEN_POLICY_KEY_RE.search(key_text):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Control Plane policies are not a secrets store; "
                        f"secret-like key rejected at {path}.{key_text}"
                    ),
                )
            _assert_no_secret_keys(nested, f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_no_secret_keys(nested, f"{path}[{index}]")


def _validate_policy_document(policy: dict[str, Any]) -> dict[str, Any]:
    _assert_no_secret_keys(policy)
    encoded = json.dumps(
        policy,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if len(encoded) > MAX_POLICY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Policy document exceeds {MAX_POLICY_BYTES} bytes",
        )
    return policy


def _control_revision(
    session: Session,
    principal: CurrentPrincipal,
) -> int:
    row = session.exec(
        text(
            """
            SELECT revision
            FROM institution_control_state
            WHERE institution_id = CAST(:institution_id AS uuid)
              AND organization_id = CAST(:organization_id AS uuid)
            """
        ),
        params={
            "institution_id": str(principal.institution_id),
            "organization_id": str(principal.organization_id),
        },
    ).first()
    return int(row[0]) if row is not None else 0


def _advance_revision(
    session: Session,
    principal: CurrentPrincipal,
) -> int:
    session.exec(
        text(
            """
            INSERT INTO institution_control_state (
                id,
                organization_id,
                institution_id,
                revision,
                updated_by_user_id,
                created_at,
                updated_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                0,
                CAST(:user_id AS uuid),
                NOW(),
                NOW()
            )
            ON CONFLICT (institution_id) DO NOTHING
            """
        ),
        params={
            "id": str(uuid4()),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "user_id": str(principal.user_id),
        },
    )
    row = session.exec(
        text(
            """
            UPDATE institution_control_state
            SET
                revision = revision + 1,
                updated_by_user_id = CAST(:user_id AS uuid),
                updated_at = NOW()
            WHERE institution_id = CAST(:institution_id AS uuid)
              AND organization_id = CAST(:organization_id AS uuid)
            RETURNING revision
            """
        ),
        params={
            "user_id": str(principal.user_id),
            "institution_id": str(principal.institution_id),
            "organization_id": str(principal.organization_id),
        },
    ).one()
    return int(row[0])


def _record_change(
    session: Session,
    principal: CurrentPrincipal,
    *,
    revision: int,
    change_type: str,
    subject_key: str,
    reason: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    session.exec(
        text(
            """
            INSERT INTO institution_control_changes (
                id,
                organization_id,
                institution_id,
                revision,
                change_type,
                subject_key,
                actor_user_id,
                reason,
                before_json,
                after_json,
                created_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                :revision,
                :change_type,
                :subject_key,
                CAST(:actor_user_id AS uuid),
                :reason,
                CAST(:before_json AS jsonb),
                CAST(:after_json AS jsonb),
                NOW()
            )
            """
        ),
        params={
            "id": str(uuid4()),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "revision": revision,
            "change_type": change_type,
            "subject_key": subject_key,
            "actor_user_id": str(principal.user_id),
            "reason": reason,
            "before_json": json.dumps(before, separators=(",", ":")),
            "after_json": json.dumps(after, separators=(",", ":")),
        },
    )

    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action=f"CONTROL_PLANE_{change_type}_CHANGED",
        entity_type="institution_control",
        entity_id=principal.institution_id,
        metadata={
            "revision": revision,
            "subject_key": subject_key,
            "reason": reason,
        },
    )

    event_type = (
        "institution.capability.changed"
        if change_type == "CAPABILITY"
        else "institution.policy.changed"
    )
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type=event_type,
        event_version=1,
        aggregate_type="institution",
        aggregate_id=principal.institution_id,
        actor_user_id=principal.user_id,
        payload={
            "revision": revision,
            "subject_key": subject_key,
            "before": before,
            "after": after,
        },
        metadata={
            "source": "institution_control_plane",
            "reason": reason,
        },
    )


def list_capabilities(
    session: Session,
    principal: CurrentPrincipal,
) -> list[CapabilityControlRead]:
    rows = session.exec(
        text(
            """
            SELECT
                ic.capability_key,
                ic.enabled,
                latest.revision,
                latest.managed_enabled,
                CASE
                    WHEN latest.revision IS NULL THEN false
                    ELSE latest.managed_enabled IS DISTINCT FROM ic.enabled
                END AS drift
            FROM institution_capabilities ic
            LEFT JOIN LATERAL (
                SELECT
                    c.revision,
                    (c.after_json ->> 'enabled')::boolean AS managed_enabled
                FROM institution_control_changes c
                WHERE c.institution_id = ic.institution_id
                  AND c.change_type = 'CAPABILITY'
                  AND c.subject_key = ic.capability_key
                ORDER BY c.revision DESC
                LIMIT 1
            ) latest ON true
            WHERE ic.institution_id = CAST(:institution_id AS uuid)
            ORDER BY ic.capability_key
            """
        ),
        params={"institution_id": str(principal.institution_id)},
    ).all()

    return [
        CapabilityControlRead(
            capability_key=row[0],
            enabled=bool(row[1]),
            managed_revision=int(row[2]) if row[2] is not None else None,
            managed_enabled=(
                bool(row[3]) if row[3] is not None else None
            ),
            drift=bool(row[4]),
        )
        for row in rows
    ]


def _capability(
    session: Session,
    principal: CurrentPrincipal,
    capability_key: str,
) -> CapabilityControlRead:
    for item in list_capabilities(session, principal):
        if item.capability_key == capability_key:
            return item
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            "Capability is not registered for the current institution; "
            "Control Plane will not create unknown capability keys"
        ),
    )


def update_capability(
    session: Session,
    principal: CurrentPrincipal,
    capability_key: str,
    payload: CapabilityControlUpdate,
) -> CapabilityControlRead:
    current = _capability(session, principal, capability_key)
    reason = _reason(payload.reason)

    if (
        current.enabled == payload.enabled
        and current.managed_enabled == payload.enabled
        and current.managed_revision is not None
    ):
        return current

    before = {
        "enabled": current.enabled,
        "managed_revision": current.managed_revision,
        "managed_enabled": current.managed_enabled,
        "drift": current.drift,
    }

    session.exec(
        text(
            """
            UPDATE institution_capabilities
            SET enabled = :enabled
            WHERE institution_id = CAST(:institution_id AS uuid)
              AND capability_key = :capability_key
            """
        ),
        params={
            "enabled": payload.enabled,
            "institution_id": str(principal.institution_id),
            "capability_key": capability_key,
        },
    )

    revision = _advance_revision(session, principal)
    after = {
        "enabled": payload.enabled,
        "managed_revision": revision,
    }
    _record_change(
        session,
        principal,
        revision=revision,
        change_type="CAPABILITY",
        subject_key=capability_key,
        reason=reason,
        before=before,
        after=after,
    )
    session.commit()
    return _capability(session, principal, capability_key)


def list_policies(
    session: Session,
    principal: CurrentPrincipal,
) -> list[PolicyControlRead]:
    rows = session.exec(
        text(
            """
            SELECT
                p.policy_key,
                p.enabled,
                p.policy_json,
                p.policy_version,
                latest.revision,
                p.updated_at
            FROM institution_policy_controls p
            LEFT JOIN LATERAL (
                SELECT c.revision
                FROM institution_control_changes c
                WHERE c.institution_id = p.institution_id
                  AND c.change_type = 'POLICY'
                  AND c.subject_key = p.policy_key
                ORDER BY c.revision DESC
                LIMIT 1
            ) latest ON true
            WHERE p.institution_id = CAST(:institution_id AS uuid)
            ORDER BY p.policy_key
            """
        ),
        params={"institution_id": str(principal.institution_id)},
    ).all()

    return [
        PolicyControlRead(
            policy_key=row[0],
            enabled=bool(row[1]),
            policy=dict(row[2] or {}),
            policy_version=int(row[3]),
            managed_revision=int(row[4]) if row[4] is not None else None,
            updated_at=row[5],
        )
        for row in rows
    ]


def _policy(
    session: Session,
    principal: CurrentPrincipal,
    policy_key: str,
) -> PolicyControlRead | None:
    for item in list_policies(session, principal):
        if item.policy_key == policy_key:
            return item
    return None


def update_policy(
    session: Session,
    principal: CurrentPrincipal,
    policy_key: str,
    payload: PolicyControlUpdate,
) -> PolicyControlRead:
    normalized_key = _validate_policy_key(policy_key)
    reason = _reason(payload.reason)
    policy = _validate_policy_document(payload.policy)
    current = _policy(session, principal, normalized_key)

    if (
        current is not None
        and current.enabled == payload.enabled
        and current.policy == policy
    ):
        return current

    version = 1 if current is None else current.policy_version + 1
    before: dict[str, Any] = {}
    if current is not None:
        before = {
            "enabled": current.enabled,
            "policy": current.policy,
            "policy_version": current.policy_version,
            "managed_revision": current.managed_revision,
        }

    session.exec(
        text(
            """
            INSERT INTO institution_policy_controls (
                id,
                organization_id,
                institution_id,
                policy_key,
                enabled,
                policy_json,
                policy_version,
                updated_by_user_id,
                created_at,
                updated_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                :policy_key,
                :enabled,
                CAST(:policy_json AS jsonb),
                :policy_version,
                CAST(:updated_by_user_id AS uuid),
                NOW(),
                NOW()
            )
            ON CONFLICT (institution_id, policy_key)
            DO UPDATE SET
                enabled = EXCLUDED.enabled,
                policy_json = EXCLUDED.policy_json,
                policy_version = EXCLUDED.policy_version,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = NOW()
            """
        ),
        params={
            "id": str(uuid4()),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "policy_key": normalized_key,
            "enabled": payload.enabled,
            "policy_json": json.dumps(policy, separators=(",", ":")),
            "policy_version": version,
            "updated_by_user_id": str(principal.user_id),
        },
    )

    revision = _advance_revision(session, principal)
    after = {
        "enabled": payload.enabled,
        "policy": policy,
        "policy_version": version,
        "managed_revision": revision,
    }
    _record_change(
        session,
        principal,
        revision=revision,
        change_type="POLICY",
        subject_key=normalized_key,
        reason=reason,
        before=before,
        after=after,
    )
    session.commit()

    updated = _policy(session, principal, normalized_key)
    if updated is None:
        raise RuntimeError("Policy update committed but policy could not be read")
    return updated


def list_changes(
    session: Session,
    principal: CurrentPrincipal,
    *,
    limit: int,
) -> list[ControlChangeRead]:
    rows = session.exec(
        text(
            """
            SELECT
                revision,
                change_type,
                subject_key,
                actor_user_id,
                reason,
                before_json,
                after_json,
                created_at
            FROM institution_control_changes
            WHERE institution_id = CAST(:institution_id AS uuid)
            ORDER BY revision DESC
            LIMIT :limit
            """
        ),
        params={
            "institution_id": str(principal.institution_id),
            "limit": max(1, min(limit, 200)),
        },
    ).all()

    return [
        ControlChangeRead(
            revision=int(row[0]),
            change_type=row[1],
            subject_key=row[2],
            actor_user_id=row[3],
            reason=row[4],
            before=dict(row[5] or {}),
            after=dict(row[6] or {}),
            created_at=row[7],
        )
        for row in rows
    ]


def control_plane_summary(
    session: Session,
    principal: CurrentPrincipal,
) -> ControlPlaneSummary:
    institution = session.exec(
        text(
            """
            SELECT name, type, status
            FROM institutions
            WHERE id = CAST(:institution_id AS uuid)
              AND organization_id = CAST(:organization_id AS uuid)
            """
        ),
        params={
            "institution_id": str(principal.institution_id),
            "organization_id": str(principal.organization_id),
        },
    ).first()
    if institution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found",
        )

    capabilities = list_capabilities(session, principal)
    policies = list_policies(session, principal)

    database_revision_row = session.exec(
        text("SELECT version_num FROM alembic_version")
    ).first()
    database_revision = (
        str(database_revision_row[0])
        if database_revision_row is not None
        else "UNKNOWN"
    )

    # Keep Control Plane health bounded. Cross-RLS joins between the legacy
    # outbox and M18 Event Ledger can produce very expensive plans. M18 ingests
    # outbox rows in (created_at, id) order, so its latest tenant ledger row is
    # a durable high-water mark for retained or independently purged outbox data.
    session.exec(text("SET LOCAL statement_timeout = '3000ms'"))

    ledger_row = session.exec(
        text(
            """
            SELECT
                l.position,
                l.occurred_at,
                l.source_outbox_event_id
            FROM event_ledger l
            WHERE l.institution_id = CAST(:institution_id AS uuid)
            ORDER BY l.position DESC
            LIMIT 1
            """
        ),
        params={"institution_id": str(principal.institution_id)},
    ).first()

    if ledger_row is None:
        ledger_position = 0
        unledgered_row = session.exec(
            text(
                """
                SELECT COUNT(o.id)
                FROM outbox_events o
                WHERE o.institution_id = CAST(:institution_id AS uuid)
                """
            ),
            params={"institution_id": str(principal.institution_id)},
        ).one()
    else:
        ledger_position = int(ledger_row[0])
        unledgered_row = session.exec(
            text(
                """
                SELECT COUNT(o.id)
                FROM outbox_events o
                WHERE o.institution_id = CAST(:institution_id AS uuid)
                  AND (
                    o.created_at > :last_created_at
                    OR (
                        o.created_at = :last_created_at
                        AND o.id > CAST(:last_source_id AS uuid)
                    )
                  )
                """
            ),
            params={
                "institution_id": str(principal.institution_id),
                "last_created_at": ledger_row[1],
                "last_source_id": str(ledger_row[2]),
            },
        ).one()
    unledgered = int(unledgered_row[0])

    projection_row = session.exec(
        text(
            """
            SELECT pc.last_position
            FROM projection_checkpoints pc
            WHERE pc.institution_id = CAST(:institution_id AS uuid)
              AND pc.projection_key = :projection_key
            LIMIT 1
            """
        ),
        params={
            "institution_id": str(principal.institution_id),
            "projection_key": PROJECTION_KEY,
        },
    ).first()
    projection_position = (
        int(projection_row[0]) if projection_row is not None else 0
    )
    projection_lag = max(0, ledger_position - projection_position)
    drift_count = sum(1 for item in capabilities if item.drift)

    health_status = "HEALTHY"
    if unledgered > 0 or projection_lag > 0 or drift_count > 0:
        health_status = "ATTENTION"

    return ControlPlaneSummary(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        institution_name=institution[0],
        institution_type=institution[1],
        institution_status=institution[2],
        control_revision=_control_revision(session, principal),
        capability_count=len(capabilities),
        capabilities_enabled=sum(
            1 for item in capabilities if item.enabled
        ),
        capabilities_disabled=sum(
            1 for item in capabilities if not item.enabled
        ),
        policies_total=len(policies),
        policies_enabled=sum(1 for item in policies if item.enabled),
        health=ControlPlaneHealth(
            release_id=settings.RELEASE_ID,
            database_revision=database_revision,
            unledgered_outbox_count=unledgered,
            ledger_latest_position=ledger_position,
            projection_position=projection_position,
            projection_lag=projection_lag,
            capability_drift_count=drift_count,
            status=health_status,
        ),
    )
