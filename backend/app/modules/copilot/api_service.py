from __future__ import annotations

from uuid import UUID

from sqlmodel import Session, text

from app.api.deps import CurrentPrincipal
from app.modules.copilot.api_schemas import (
    CopilotRunProvenance,
    CopilotRunResponse,
)


def get_visible_copilot_run(
    session: Session,
    principal: CurrentPrincipal,
    *,
    run_id: UUID,
) -> CopilotRunResponse | None:
    row = session.exec(
        text(
            """
            SELECT
                cr.id,
                cr.intent,
                cr.status,
                cr.failure_code,
                cr.policy_key,
                cr.policy_version,
                cr.prompt_key,
                cr.prompt_version,
                cr.provider_key,
                cr.model_key,
                cr.model_config_version,
                cr.usage_json,
                cr.cost_json,
                cr.created_at,
                cr.completed_at,
                cao.answer_text,
                cao.citations_json,
                cao.evidence_assessment,
                cao.limitations_json
            FROM copilot_runs cr
            LEFT JOIN copilot_advisory_outputs cao
              ON cao.run_id = cr.id
             AND cao.organization_id = cr.organization_id
             AND cao.institution_id = cr.institution_id
            WHERE cr.id = CAST(:run_id AS uuid)
              AND cr.organization_id = CAST(:organization_id AS uuid)
              AND cr.institution_id = CAST(:institution_id AS uuid)
            LIMIT 1
            """
        ),
        params={
            "run_id": str(run_id),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()

    if row is None:
        return None

    citations = row[16] if isinstance(row[16], list) else []
    limitations = row[18] if isinstance(row[18], list) else []
    usage = row[11] if isinstance(row[11], dict) else {}
    cost = row[12] if isinstance(row[12], dict) else {}

    return CopilotRunResponse(
        run_id=row[0],
        intent=str(row[1]),
        status=str(row[2]),
        failure_code=None if row[3] is None else str(row[3]),
        answer=None if row[15] is None else str(row[15]),
        citations=[str(value) for value in citations],
        evidence_assessment=(
            None if row[17] is None else str(row[17])
        ),
        limitations=[str(value) for value in limitations],
        provenance=CopilotRunProvenance(
            policy_key=None if row[4] is None else str(row[4]),
            policy_version=row[5],
            prompt_key=None if row[6] is None else str(row[6]),
            prompt_version=row[7],
            provider_key=None if row[8] is None else str(row[8]),
            model_key=None if row[9] is None else str(row[9]),
            model_config_version=row[10],
        ),
        usage=usage,
        cost=cost,
        created_at=row[13],
        completed_at=row[14],
    )
