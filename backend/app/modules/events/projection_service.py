from __future__ import annotations

import json
from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel import Session

PROJECTION_KEY = "institution_activity_v1"


def _bounded_limit(limit: int) -> int:
    return max(1, min(limit, 5000))


def _decode_outbox_payload(
    payload_text: str,
) -> tuple[int, UUID | None, UUID | None, UUID | None, dict, dict]:
    raw = json.loads(payload_text or "{}")
    if (
        isinstance(raw, dict)
        and isinstance(raw.get("_education_os_event"), dict)
        and "data" in raw
    ):
        envelope = raw["_education_os_event"]
        version = int(envelope.get("version", 1))
        actor = envelope.get("actor_user_id")
        correlation = envelope.get("correlation_id")
        causation = envelope.get("causation_id")
        metadata = envelope.get("metadata")
        return (
            max(1, version),
            UUID(str(actor)) if actor else None,
            UUID(str(correlation)) if correlation else None,
            UUID(str(causation)) if causation else None,
            raw["data"] if isinstance(raw["data"], dict) else {"value": raw["data"]},
            metadata if isinstance(metadata, dict) else {},
        )

    return (
        1,
        None,
        None,
        None,
        raw if isinstance(raw, dict) else {"value": raw},
        {"legacy_envelope": True},
    )


def ingest_outbox_events(
    session: Session,
    *,
    institution_id: UUID,
    limit: int = 1000,
) -> int:
    """Copy tenant-visible outbox rows into the immutable canonical ledger."""
    rows = session.exec(
        text(
            """
            SELECT
                o.id,
                i.organization_id,
                o.institution_id,
                o.event_type,
                o.aggregate_type,
                o.aggregate_id,
                o.payload_json::text,
                o.created_at
            FROM outbox_events o
            JOIN institutions i ON i.id = o.institution_id
            LEFT JOIN event_ledger l
              ON l.source_outbox_event_id = o.id
            WHERE o.institution_id = CAST(:institution_id AS uuid)
              AND l.id IS NULL
            ORDER BY o.created_at, o.id
            LIMIT :limit
            """
        ),
        params={
            "institution_id": str(institution_id),
            "limit": _bounded_limit(limit),
        },
    ).all()

    inserted = 0
    for row in rows:
        (
            event_version,
            actor_user_id,
            correlation_id,
            causation_id,
            payload,
            metadata,
        ) = _decode_outbox_payload(row[6] or "{}")
        metadata = {
            **metadata,
            "source": "transactional_outbox",
        }

        result = session.exec(
            text(
                """
                INSERT INTO event_ledger (
                    id,
                    organization_id,
                    institution_id,
                    source_kind,
                    source_outbox_event_id,
                    event_type,
                    event_version,
                    aggregate_type,
                    aggregate_id,
                    actor_user_id,
                    correlation_id,
                    causation_id,
                    payload_json,
                    metadata_json,
                    occurred_at,
                    recorded_at
                )
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:organization_id AS uuid),
                    CAST(:institution_id AS uuid),
                    'TRANSACTIONAL_OUTBOX',
                    CAST(:source_outbox_event_id AS uuid),
                    :event_type,
                    :event_version,
                    :aggregate_type,
                    CAST(:aggregate_id AS uuid),
                    CAST(:actor_user_id AS uuid),
                    CAST(:correlation_id AS uuid),
                    CAST(:causation_id AS uuid),
                    CAST(:payload_json AS jsonb),
                    CAST(:metadata_json AS jsonb),
                    :occurred_at,
                    NOW()
                )
                ON CONFLICT (source_outbox_event_id) DO NOTHING
                RETURNING id
                """
            ),
            params={
                "id": str(row[0]),
                "organization_id": str(row[1]),
                "institution_id": str(row[2]),
                "source_outbox_event_id": str(row[0]),
                "event_type": row[3],
                "event_version": event_version,
                "aggregate_type": row[4],
                "aggregate_id": str(row[5]),
                "actor_user_id": (
                    str(actor_user_id) if actor_user_id else None
                ),
                "correlation_id": (
                    str(correlation_id) if correlation_id else None
                ),
                "causation_id": (
                    str(causation_id) if causation_id else None
                ),
                "payload_json": json.dumps(
                    payload,
                    separators=(",", ":"),
                ),
                "metadata_json": json.dumps(
                    metadata,
                    separators=(",", ":"),
                ),
                "occurred_at": row[7],
            },
        ).first()
        if result is not None:
            inserted += 1
    return inserted


def _checkpoint(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
) -> tuple[UUID, int, int]:
    checkpoint_id = uuid4()
    session.exec(
        text(
            """
            INSERT INTO projection_checkpoints (
                id,
                organization_id,
                institution_id,
                projection_key,
                last_position,
                processed_count,
                updated_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                :projection_key,
                0,
                0,
                NOW()
            )
            ON CONFLICT (institution_id, projection_key) DO NOTHING
            """
        ),
        params={
            "id": str(checkpoint_id),
            "organization_id": str(organization_id),
            "institution_id": str(institution_id),
            "projection_key": PROJECTION_KEY,
        },
    )
    row = session.exec(
        text(
            """
            SELECT id, last_position, processed_count
            FROM projection_checkpoints
            WHERE institution_id = CAST(:institution_id AS uuid)
              AND projection_key = :projection_key
            """
        ),
        params={
            "institution_id": str(institution_id),
            "projection_key": PROJECTION_KEY,
        },
    ).one()
    return row[0], int(row[1]), int(row[2])


def project_event_ledger(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    limit: int = 1000,
) -> int:
    """Advance idempotent read models from the immutable ledger."""
    checkpoint_id, last_position, processed_count = _checkpoint(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
    )

    rows = session.exec(
        text(
            """
            SELECT
                position,
                event_type,
                event_version,
                aggregate_type,
                aggregate_id,
                occurred_at
            FROM event_ledger
            WHERE institution_id = CAST(:institution_id AS uuid)
              AND position > :last_position
            ORDER BY position
            LIMIT :limit
            """
        ),
        params={
            "institution_id": str(institution_id),
            "last_position": last_position,
            "limit": _bounded_limit(limit),
        },
    ).all()
    if not rows:
        return 0

    daily: dict[
        tuple[date, str, int],
        dict[str, object],
    ] = {}
    aggregates: dict[
        tuple[str, UUID],
        dict[str, object],
    ] = {}

    for row in rows:
        position = int(row[0])
        event_type = str(row[1])
        event_version = int(row[2])
        aggregate_type = str(row[3])
        aggregate_id = row[4]
        occurred_at: datetime = row[5]
        event_date = occurred_at.date()

        daily_key = (event_date, event_type, event_version)
        if daily_key not in daily:
            daily[daily_key] = {
                "count": 0,
                "first_event_at": occurred_at,
                "last_event_at": occurred_at,
            }
        daily_entry = daily[daily_key]
        daily_entry["count"] = int(daily_entry["count"]) + 1
        daily_entry["first_event_at"] = min(
            daily_entry["first_event_at"],  # type: ignore[arg-type]
            occurred_at,
        )
        daily_entry["last_event_at"] = max(
            daily_entry["last_event_at"],  # type: ignore[arg-type]
            occurred_at,
        )

        aggregate_key = (aggregate_type, aggregate_id)
        if aggregate_key not in aggregates:
            aggregates[aggregate_key] = {
                "count": 0,
                "first_position": position,
                "last_position": position,
                "first_event_at": occurred_at,
                "last_event_at": occurred_at,
                "last_event_type": event_type,
                "last_event_version": event_version,
            }
        aggregate_entry = aggregates[aggregate_key]
        aggregate_entry["count"] = int(aggregate_entry["count"]) + 1
        if position < int(aggregate_entry["first_position"]):
            aggregate_entry["first_position"] = position
            aggregate_entry["first_event_at"] = occurred_at
        if position >= int(aggregate_entry["last_position"]):
            aggregate_entry["last_position"] = position
            aggregate_entry["last_event_at"] = occurred_at
            aggregate_entry["last_event_type"] = event_type
            aggregate_entry["last_event_version"] = event_version

    for (event_date, event_type, event_version), item in daily.items():
        session.exec(
            text(
                """
                INSERT INTO institution_event_daily (
                    id,
                    organization_id,
                    institution_id,
                    event_date,
                    event_type,
                    event_version,
                    event_count,
                    first_event_at,
                    last_event_at,
                    projection_updated_at
                )
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:organization_id AS uuid),
                    CAST(:institution_id AS uuid),
                    :event_date,
                    :event_type,
                    :event_version,
                    :event_count,
                    :first_event_at,
                    :last_event_at,
                    NOW()
                )
                ON CONFLICT (
                    institution_id,
                    event_date,
                    event_type,
                    event_version
                )
                DO UPDATE SET
                    event_count = institution_event_daily.event_count
                        + EXCLUDED.event_count,
                    first_event_at = LEAST(
                        institution_event_daily.first_event_at,
                        EXCLUDED.first_event_at
                    ),
                    last_event_at = GREATEST(
                        institution_event_daily.last_event_at,
                        EXCLUDED.last_event_at
                    ),
                    projection_updated_at = NOW()
                """
            ),
            params={
                "id": str(uuid4()),
                "organization_id": str(organization_id),
                "institution_id": str(institution_id),
                "event_date": event_date,
                "event_type": event_type,
                "event_version": event_version,
                "event_count": int(item["count"]),
                "first_event_at": item["first_event_at"],
                "last_event_at": item["last_event_at"],
            },
        )

    for (aggregate_type, aggregate_id), item in aggregates.items():
        session.exec(
            text(
                """
                INSERT INTO aggregate_activity_snapshots (
                    id,
                    organization_id,
                    institution_id,
                    aggregate_type,
                    aggregate_id,
                    first_position,
                    last_position,
                    first_event_at,
                    last_event_at,
                    event_count,
                    last_event_type,
                    last_event_version,
                    projection_updated_at
                )
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:organization_id AS uuid),
                    CAST(:institution_id AS uuid),
                    :aggregate_type,
                    CAST(:aggregate_id AS uuid),
                    :first_position,
                    :last_position,
                    :first_event_at,
                    :last_event_at,
                    :event_count,
                    :last_event_type,
                    :last_event_version,
                    NOW()
                )
                ON CONFLICT (
                    institution_id,
                    aggregate_type,
                    aggregate_id
                )
                DO UPDATE SET
                    first_position = LEAST(
                        aggregate_activity_snapshots.first_position,
                        EXCLUDED.first_position
                    ),
                    last_position = GREATEST(
                        aggregate_activity_snapshots.last_position,
                        EXCLUDED.last_position
                    ),
                    first_event_at = LEAST(
                        aggregate_activity_snapshots.first_event_at,
                        EXCLUDED.first_event_at
                    ),
                    last_event_at = GREATEST(
                        aggregate_activity_snapshots.last_event_at,
                        EXCLUDED.last_event_at
                    ),
                    event_count = aggregate_activity_snapshots.event_count
                        + EXCLUDED.event_count,
                    last_event_type = CASE
                        WHEN EXCLUDED.last_position
                            >= aggregate_activity_snapshots.last_position
                        THEN EXCLUDED.last_event_type
                        ELSE aggregate_activity_snapshots.last_event_type
                    END,
                    last_event_version = CASE
                        WHEN EXCLUDED.last_position
                            >= aggregate_activity_snapshots.last_position
                        THEN EXCLUDED.last_event_version
                        ELSE aggregate_activity_snapshots.last_event_version
                    END,
                    projection_updated_at = NOW()
                """
            ),
            params={
                "id": str(uuid4()),
                "organization_id": str(organization_id),
                "institution_id": str(institution_id),
                "aggregate_type": aggregate_type,
                "aggregate_id": str(aggregate_id),
                "first_position": int(item["first_position"]),
                "last_position": int(item["last_position"]),
                "first_event_at": item["first_event_at"],
                "last_event_at": item["last_event_at"],
                "event_count": int(item["count"]),
                "last_event_type": str(item["last_event_type"]),
                "last_event_version": int(item["last_event_version"]),
            },
        )

    new_last_position = int(rows[-1][0])
    session.exec(
        text(
            """
            UPDATE projection_checkpoints
            SET
                last_position = :last_position,
                processed_count = :processed_count,
                updated_at = NOW()
            WHERE id = CAST(:id AS uuid)
            """
        ),
        params={
            "last_position": new_last_position,
            "processed_count": processed_count + len(rows),
            "id": str(checkpoint_id),
        },
    )
    return len(rows)


def run_event_pipeline(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    limit: int = 1000,
) -> dict[str, int]:
    ingested = ingest_outbox_events(
        session,
        institution_id=institution_id,
        limit=limit,
    )
    projected = project_event_ledger(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        limit=limit,
    )
    return {
        "ingested": ingested,
        "projected": projected,
    }


def platform_summary(
    session: Session,
    *,
    institution_id: UUID,
) -> dict[str, object]:
    ledger = session.exec(
        text(
            """
            SELECT COUNT(id), COALESCE(MAX(position), 0)
            FROM event_ledger
            WHERE institution_id = CAST(:institution_id AS uuid)
            """
        ),
        params={"institution_id": str(institution_id)},
    ).one()

    checkpoint = session.exec(
        text(
            """
            SELECT last_position, processed_count, updated_at
            FROM projection_checkpoints
            WHERE institution_id = CAST(:institution_id AS uuid)
              AND projection_key = :projection_key
            """
        ),
        params={
            "institution_id": str(institution_id),
            "projection_key": PROJECTION_KEY,
        },
    ).first()

    daily_count = session.exec(
        text(
            """
            SELECT COUNT(*)
            FROM institution_event_daily
            WHERE institution_id = CAST(:institution_id AS uuid)
            """
        ),
        params={"institution_id": str(institution_id)},
    ).one()[0]

    aggregate_count = session.exec(
        text(
            """
            SELECT COUNT(*)
            FROM aggregate_activity_snapshots
            WHERE institution_id = CAST(:institution_id AS uuid)
            """
        ),
        params={"institution_id": str(institution_id)},
    ).one()[0]

    return {
        "milestone": "M18",
        "platform_version": "0.18.0",
        "ledger": {
            "event_count": int(ledger[0]),
            "latest_position": int(ledger[1]),
        },
        "projection": {
            "key": PROJECTION_KEY,
            "last_position": int(checkpoint[0]) if checkpoint else 0,
            "processed_count": int(checkpoint[1]) if checkpoint else 0,
            "updated_at": (
                checkpoint[2].isoformat() if checkpoint and checkpoint[2] else None
            ),
        },
        "read_models": {
            "daily_rows": int(daily_count),
            "aggregate_rows": int(aggregate_count),
        },
    }


def recent_event_metadata(
    session: Session,
    *,
    institution_id: UUID,
    limit: int = 50,
) -> list[dict[str, object]]:
    rows = session.exec(
        text(
            """
            SELECT
                id,
                position,
                event_type,
                event_version,
                aggregate_type,
                aggregate_id,
                correlation_id,
                causation_id,
                occurred_at,
                recorded_at
            FROM event_ledger
            WHERE institution_id = CAST(:institution_id AS uuid)
            ORDER BY position DESC
            LIMIT :limit
            """
        ),
        params={
            "institution_id": str(institution_id),
            "limit": max(1, min(limit, 200)),
        },
    ).all()
    return [
        {
            "event_id": str(row[0]),
            "position": int(row[1]),
            "event_type": row[2],
            "event_version": int(row[3]),
            "aggregate_type": row[4],
            "aggregate_id": str(row[5]),
            "correlation_id": str(row[6]) if row[6] else None,
            "causation_id": str(row[7]) if row[7] else None,
            "occurred_at": row[8].isoformat(),
            "recorded_at": row[9].isoformat(),
        }
        for row in rows
    ]


def daily_read_model(
    session: Session,
    *,
    institution_id: UUID,
    limit: int = 100,
) -> list[dict[str, object]]:
    rows = session.exec(
        text(
            """
            SELECT
                event_date,
                event_type,
                event_version,
                event_count,
                first_event_at,
                last_event_at
            FROM institution_event_daily
            WHERE institution_id = CAST(:institution_id AS uuid)
            ORDER BY event_date DESC, event_type, event_version
            LIMIT :limit
            """
        ),
        params={
            "institution_id": str(institution_id),
            "limit": max(1, min(limit, 500)),
        },
    ).all()
    return [
        {
            "event_date": row[0].isoformat(),
            "event_type": row[1],
            "event_version": int(row[2]),
            "event_count": int(row[3]),
            "first_event_at": row[4].isoformat(),
            "last_event_at": row[5].isoformat(),
        }
        for row in rows
    ]
