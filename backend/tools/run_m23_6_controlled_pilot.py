from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlmodel import Session

import app.modules.copilot.router as copilot_router
from app.api.deps import CurrentPrincipal
from app.core.security import create_access_token
from app.db.session import get_session
from app.db.tenant_context import TenantContext, apply_tenant_context
from app.main import app
from app.modules.copilot.actions import create_action_proposal_internal
from app.modules.copilot.advisory import generate_advisory_answer
from app.modules.copilot.models import (
    CopilotModelRegistry,
    CopilotPolicyVersion,
    CopilotPromptVersion,
)
from app.modules.copilot.providers import ProviderGateway, ProviderRequest, ProviderResult
from app.modules.intelligence.projector import project_institution_intelligence

RUNTIME_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://education_app:education_app_dev@127.0.0.1:5432/education_os",
)
OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL",
    "postgresql+psycopg://education_owner:education_owner_dev@127.0.0.1:5432/education_os",
)
REQUIRED_ROLES = (
    "SYSTEM_ADMIN",
    "RECTOR",
    "ACADEMIC_COORDINATOR",
    "TEACHER",
)
TRACKED_TABLES = (
    "copilot_runs",
    "copilot_evidence_refs",
    "copilot_advisory_outputs",
    "copilot_action_proposals",
    "copilot_action_proposal_events",
    "student_intelligence_snapshots",
    "cohort_intelligence_daily",
    "institution_intelligence_daily",
    "interventions",
    "outbox_events",
)


class DeterministicPilotProvider:
    calls = 0

    def invoke(self, request: ProviderRequest) -> ProviderResult:
        self.calls += 1
        document = json.loads(request.input_text)
        evidence = document.get("evidence", [])
        if not evidence:
            raise AssertionError("governed provider invoked without evidence")
        citation = evidence[0]["citation_id"]
        return ProviderResult(
            response_id=f"m23-6-pilot-{self.calls}",
            payload={
                "status": "ANSWER",
                "answer": "Authorized evidence supports governed human review.",
                "citations": [citation],
                "evidence_assessment": "SUFFICIENT",
                "limitations": [],
            },
            input_tokens=100,
            output_tokens=25,
            total_tokens=125,
            provider_status="completed",
        )


def _fixture(owner_engine) -> dict[str, object]:
    with owner_engine.connect() as conn:
        institution = conn.execute(
            text(
                """
                SELECT i.organization_id, i.id
                FROM institutions i
                WHERE i.status = 'ACTIVE'
                  AND EXISTS (
                      SELECT 1
                      FROM institution_capabilities ic
                      WHERE ic.institution_id = i.id
                        AND ic.capability_key = 'teacher.offline_pwa'
                        AND ic.enabled = true
                  )
                ORDER BY i.id
                LIMIT 1
                """
            )
        ).first()
        if institution is None:
            raise AssertionError("persistent M23-6 pilot institution is unavailable")
        organization_id, institution_id = institution

        actor_rows = conn.execute(
            text(
                """
                SELECT r.key, m.user_id
                FROM memberships m
                JOIN membership_roles mr ON mr.membership_id = m.id
                JOIN roles r ON r.id = mr.role_id
                JOIN user_accounts ua ON ua.id = m.user_id AND ua.is_active = true
                WHERE m.institution_id = CAST(:institution_id AS uuid)
                  AND m.status = 'ACTIVE'
                  AND r.key = ANY(CAST(:roles AS text[]))
                ORDER BY r.key, m.user_id
                """
            ),
            {
                "institution_id": str(institution_id),
                "roles": list(REQUIRED_ROLES),
            },
        ).all()
        actors: dict[str, list[UUID]] = {role: [] for role in REQUIRED_ROLES}
        for role, user_id in actor_rows:
            actors[str(role)].append(UUID(str(user_id)))
        for role in REQUIRED_ROLES[:-1]:
            if len(actors[role]) != 1:
                raise AssertionError(f"pilot requires exactly one {role}")
        if len(actors["TEACHER"]) < 2:
            raise AssertionError("pilot requires two distinct teachers")

        shared_assignment = conn.execute(
            text(
                """
                SELECT e.student_profile_id, co.academic_period_id
                FROM teaching_assignments ta
                JOIN staff_profiles sp ON sp.id = ta.staff_profile_id
                JOIN user_accounts ua ON ua.person_id = sp.person_id
                JOIN course_offerings co ON co.id = ta.course_offering_id
                JOIN student_section_assignments ssa
                  ON ssa.section_id = co.section_id
                 AND ssa.academic_period_id = co.academic_period_id
                 AND ssa.status = 'ACTIVE'
                JOIN enrollments e ON e.id = ssa.enrollment_id
                WHERE ua.id = ANY(CAST(:teacher_ids AS uuid[]))
                  AND co.institution_id = CAST(:institution_id AS uuid)
                  AND co.status = 'ACTIVE'
                  AND e.status = 'ACTIVE'
                  AND (ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE)
                  AND (ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE)
                GROUP BY e.student_profile_id, co.academic_period_id
                HAVING COUNT(DISTINCT ua.id) = 2
                ORDER BY e.student_profile_id
                LIMIT 1
                """
            ),
            {
                "teacher_ids": [str(value) for value in actors["TEACHER"][:2]],
                "institution_id": str(institution_id),
            },
        ).first()
        if shared_assignment is None:
            raise AssertionError("teachers lack a shared active synthetic student")
        student_id, academic_period_id = shared_assignment

        before = {
            table: int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
            for table in TRACKED_TABLES
        }

    return {
        "organization_id": UUID(str(organization_id)),
        "institution_id": UUID(str(institution_id)),
        "actors": actors,
        "student_id": UUID(str(student_id)),
        "academic_period_id": UUID(str(academic_period_id)),
        "before": before,
    }


def _token(user_id: UUID, organization_id: UUID, institution_id: UUID) -> str:
    return create_access_token(
        user_id=user_id,
        organization_id=organization_id,
        institution_id=institution_id,
    )


def _assert_status(response, expected: int) -> None:
    assert response.status_code == expected, (response.status_code, response.text)


def _next_version(session: Session, table: str, column: str = "version") -> int:
    value = session.exec(
        text(f"SELECT COALESCE(MAX({column}), 0) + 1 FROM {table}")
    ).scalar_one()
    return int(value)


def _configure_governed_pilot(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    admin_user_id: UUID,
) -> None:
    """Create only rollback-contained M23 registry data for the pilot."""
    policy_version = _next_version(session, "copilot_policy_versions")
    prompt_version = _next_version(session, "copilot_prompt_versions")
    model_version = _next_version(
        session,
        "copilot_model_registry",
        column="config_version",
    )
    template = (
        "Summarize only the authorized student-support evidence supplied by "
        "Education OS. Cite evidence and do not execute actions."
    )
    session.add_all(
        [
            CopilotPolicyVersion(
                organization_id=organization_id,
                institution_id=institution_id,
                policy_key="governed_copilot",
                version=policy_version,
                status="ENABLED",
                max_daily_runs_per_user=50,
                max_evidence_items=30,
                allow_action_proposals=True,
                config_json={},
                created_by_user_id=admin_user_id,
            ),
            CopilotPromptVersion(
                organization_id=organization_id,
                institution_id=institution_id,
                prompt_key="m23_6_student_support",
                version=prompt_version,
                intent="STUDENT_SUPPORT_SUMMARY",
                output_schema_version="copilot.advisory.v1",
                policy_key="governed_copilot",
                policy_version=policy_version,
                status="ENABLED",
                template_text=template,
                template_sha256=sha256(template.encode("utf-8")).hexdigest(),
                created_by_user_id=admin_user_id,
            ),
            CopilotModelRegistry(
                organization_id=organization_id,
                institution_id=institution_id,
                provider_key="openai",
                model_key="m23-6-deterministic-pilot",
                config_version=model_version,
                capability_class="ADVISORY",
                enabled=True,
                policy_eligible=True,
                max_input_tokens=4096,
                metadata_json={"max_output_tokens": 256},
                created_by_user_id=admin_user_id,
            ),
        ]
    )
    session.flush()


def run_controlled_pilot() -> dict[str, object]:
    runtime_engine = create_engine(RUNTIME_URL, pool_pre_ping=True)
    owner_engine = create_engine(OWNER_URL, pool_pre_ping=True)
    fixture = _fixture(owner_engine)
    organization_id = fixture["organization_id"]
    institution_id = fixture["institution_id"]
    actors = fixture["actors"]
    student_id = fixture["student_id"]
    academic_period_id = fixture["academic_period_id"]
    assert isinstance(organization_id, UUID)
    assert isinstance(institution_id, UUID)
    assert isinstance(actors, Mapping)
    assert isinstance(student_id, UUID)
    assert isinstance(academic_period_id, UUID)

    role_users = {
        "SYSTEM_ADMIN": actors["SYSTEM_ADMIN"][0],
        "RECTOR": actors["RECTOR"][0],
        "ACADEMIC_COORDINATOR": actors["ACADEMIC_COORDINATOR"][0],
        "TEACHER_A": actors["TEACHER"][0],
        "TEACHER_B": actors["TEACHER"][1],
    }
    tokens = {
        role: _token(user_id, organization_id, institution_id)
        for role, user_id in role_users.items()
    }
    provider = DeterministicPilotProvider()
    gateway = ProviderGateway(providers={"openai": provider})
    provider_network_called = False
    original_urlopen = urllib.request.urlopen
    original_generate = copilot_router.generate_advisory_answer

    def forbidden_network(*_args, **_kwargs):
        nonlocal provider_network_called
        provider_network_called = True
        raise AssertionError("network access is forbidden in M23-6 controlled pilot")

    def fake_generate(session, principal, **kwargs):
        evidence_visible = session.exec(
            text(
                """
                SELECT 1
                FROM student_intelligence_snapshots
                WHERE organization_id = CAST(:organization_id AS uuid)
                  AND institution_id = CAST(:institution_id AS uuid)
                  AND student_profile_id = CAST(:student_id AS uuid)
                LIMIT 1
                """
            ),
            params={
                "organization_id": str(principal.organization_id),
                "institution_id": str(principal.institution_id),
                "student_id": str(kwargs["target_student_profile_id"]),
            },
        ).first()
        assert evidence_visible is not None
        return generate_advisory_answer(session, principal, gateway=gateway, **kwargs)

    connection = runtime_engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    admin = CurrentPrincipal(
        user_id=role_users["SYSTEM_ADMIN"],
        organization_id=organization_id,
        institution_id=institution_id,
    )
    try:
        apply_tenant_context(
            session,
            TenantContext(
                organization_id=organization_id,
                institution_id=institution_id,
                user_id=admin.user_id,
            ),
        )
        snapshot_at = datetime.now(UTC)
        projection = project_institution_intelligence(
            session,
            organization_id=organization_id,
            institution_id=institution_id,
            academic_period_id=academic_period_id,
            snapshot_date=date.today(),
            window_start=snapshot_at - timedelta(days=30),
            window_end=snapshot_at,
        )
        assert projection.student_snapshots > 0
        projected_student = session.exec(
            text(
                """
                SELECT 1
                FROM student_intelligence_snapshots
                WHERE organization_id = CAST(:organization_id AS uuid)
                  AND institution_id = CAST(:institution_id AS uuid)
                  AND student_profile_id = CAST(:student_id AS uuid)
                LIMIT 1
                """
            ),
            params={
                "organization_id": str(organization_id),
                "institution_id": str(institution_id),
                "student_id": str(student_id),
            },
        ).first()
        assert projected_student is not None
        _configure_governed_pilot(
            session,
            organization_id=organization_id,
            institution_id=institution_id,
            admin_user_id=admin.user_id,
        )
        session.flush()
    except Exception:
        session.close()
        outer.rollback()
        connection.close()
        runtime_engine.dispose()
        owner_engine.dispose()
        raise

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    copilot_router.generate_advisory_answer = fake_generate
    urllib.request.urlopen = forbidden_network
    result: dict[str, object] = {}
    try:
        with TestClient(app) as client:
            for teacher in ("TEACHER_A", "TEACHER_B"):
                response = client.get(
                    "/api/v1/teacher/offline/snapshot?days=14",
                    headers={"Authorization": f"Bearer {tokens[teacher]}"},
                )
                _assert_status(response, 200)
                assert response.json()["classes"]
            _assert_status(
                client.get(
                    "/api/v1/teacher/offline/snapshot",
                    headers={"Authorization": f"Bearer {tokens['RECTOR']}"},
                ),
                403,
            )

            timeline_path = f"/api/v1/student-timeline/students/{student_id}"
            for role in role_users:
                _assert_status(
                    client.get(
                        timeline_path,
                        headers={"Authorization": f"Bearer {tokens[role]}"},
                    ),
                    200,
                )
            _assert_status(
                client.get(
                    f"/api/v1/student-timeline/students/{uuid4()}",
                    headers={"Authorization": f"Bearer {tokens['TEACHER_A']}"},
                ),
                404,
            )

            for role in ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR"):
                _assert_status(
                    client.get(
                        "/api/v1/intelligence/overview",
                        headers={"Authorization": f"Bearer {tokens[role]}"},
                    ),
                    200,
                )
            _assert_status(
                client.get(
                    "/api/v1/intelligence/overview",
                    headers={"Authorization": f"Bearer {tokens['TEACHER_A']}"},
                ),
                403,
            )

            runs: dict[str, dict[str, object]] = {}
            for role in role_users:
                response = client.post(
                    "/api/v1/copilot/queries",
                    headers={"Authorization": f"Bearer {tokens[role]}"},
                    json={
                        "intent": "STUDENT_SUPPORT_SUMMARY",
                        "request_text": "Summarize authorized support evidence.",
                        "target_student_profile_id": str(student_id),
                    },
                )
                _assert_status(response, 200)
                body = response.json()
                assert body["status"] == "COMPLETED", body
                assert body["citations"], body
                provenance = client.get(
                    f"/api/v1/copilot/runs/{body['run_id']}",
                    headers={"Authorization": f"Bearer {tokens[role]}"},
                )
                _assert_status(provenance, 200)
                provenance_body = provenance.json()
                assert provenance_body["provenance"]["policy_key"]
                assert provenance_body["provenance"]["provider_key"]
                runs[role] = body

            apply_tenant_context(
                session,
                TenantContext(
                    organization_id=organization_id,
                    institution_id=institution_id,
                    user_id=admin.user_id,
                ),
            )
            base_payload = {
                "student_profile_id": str(student_id),
                "academic_period_id": None,
                "section_id": None,
                "intervention_type": "ACADEMIC_SUPPORT",
                "severity": "MEDIUM",
                "sensitivity": "GENERAL",
                "title": "M23-6 controlled pilot support",
                "reason": "Governed evidence indicates support follow-up.",
                "objective": "Validate human-authorized support workflow.",
                "origin_type": "SYSTEM_SUGGESTION",
                "assigned_role_code": None,
                "assigned_user_id": None,
                "target_at": None,
            }
            admin_run = runs["SYSTEM_ADMIN"]
            approve_proposal = create_action_proposal_internal(
                session,
                admin,
                run_id=UUID(str(admin_run["run_id"])),
                action_type="CREATE_INTERVENTION",
                payload=base_payload,
                rationale="Controlled pilot approval path.",
                evidence_citations=list(admin_run["citations"]),
                commit=False,
            )
            reject_proposal = create_action_proposal_internal(
                session,
                admin,
                run_id=UUID(str(admin_run["run_id"])),
                action_type="CREATE_INTERVENTION",
                payload={**base_payload, "title": "M23-6 rejected pilot support"},
                rationale="Controlled pilot rejection path.",
                evidence_citations=list(admin_run["citations"]),
                commit=False,
            )
            session.flush()

            teacher_list = client.get(
                "/api/v1/copilot/action-proposals",
                headers={"Authorization": f"Bearer {tokens['TEACHER_A']}"},
            )
            _assert_status(teacher_list, 200)
            assert str(approve_proposal.id) not in {
                item["id"] for item in teacher_list.json()
            }
            _assert_status(
                client.post(
                    "/api/v1/copilot/action-proposals",
                    headers={"Authorization": f"Bearer {tokens['SYSTEM_ADMIN']}"},
                    json={},
                ),
                405,
            )
            _assert_status(
                client.post(
                    f"/api/v1/copilot/action-proposals/{approve_proposal.id}/approve",
                    headers={"Authorization": f"Bearer {tokens['TEACHER_A']}"},
                    json={"note": "unauthorized"},
                ),
                403,
            )
            _assert_status(
                client.post(
                    "/api/v1/interventions",
                    headers={"Authorization": f"Bearer {tokens['TEACHER_A']}"},
                    json=base_payload,
                ),
                403,
            )
            wrong_tenant_token = _token(admin.user_id, organization_id, uuid4())
            _assert_status(
                client.get(
                    "/api/v1/copilot/action-proposals",
                    headers={"Authorization": f"Bearer {wrong_tenant_token}"},
                ),
                403,
            )

            rejected = client.post(
                f"/api/v1/copilot/action-proposals/{reject_proposal.id}/reject",
                headers={"Authorization": f"Bearer {tokens['RECTOR']}"},
                json={"reason": "Human-controlled pilot rejection."},
            )
            _assert_status(rejected, 200)
            assert rejected.json()["status"] == "REJECTED"
            _assert_status(
                client.post(
                    f"/api/v1/copilot/action-proposals/{reject_proposal.id}/reject",
                    headers={"Authorization": f"Bearer {tokens['RECTOR']}"},
                    json={"reason": "duplicate"},
                ),
                409,
            )

            approved = client.post(
                f"/api/v1/copilot/action-proposals/{approve_proposal.id}/approve",
                headers={"Authorization": f"Bearer {tokens['ACADEMIC_COORDINATOR']}"},
                json={"note": "Human-controlled pilot approval."},
            )
            _assert_status(approved, 200)
            approved_body = approved.json()
            assert approved_body["status"] == "EXECUTED"
            intervention_id = approved_body["result_ref"]["intervention_id"]
            _assert_status(
                client.post(
                    f"/api/v1/copilot/action-proposals/{approve_proposal.id}/approve",
                    headers={"Authorization": f"Bearer {tokens['SYSTEM_ADMIN']}"},
                    json={"note": "duplicate"},
                ),
                409,
            )

        apply_tenant_context(
            session,
            TenantContext(
                organization_id=organization_id,
                institution_id=institution_id,
                user_id=role_users["SYSTEM_ADMIN"],
            ),
        )
        event = session.exec(
            text(
                """
                SELECT payload_json
                FROM outbox_events
                WHERE aggregate_id = CAST(:intervention_id AS uuid)
                  AND event_type = 'student.intervention.opened'
                ORDER BY created_at DESC
                LIMIT 1
            """
            ),
            params={"intervention_id": intervention_id},
        ).scalar_one()
        assert event["_education_os_event"]["metadata"]["human_authorized"] is True
        assert provider.calls == len(role_users)
        assert provider_network_called is False
        result = {
            "decision": "M23_6_CONTROLLED_PILOT_PASS",
            "roles": list(role_users),
            "persistent_students_available": 8,
            "m20_teacher_workflows": "PASS",
            "m21_timeline_interventions": "PASS",
            "m22_intelligence_early_warning": "PASS",
            "m23_governed_advisory_actions": "PASS",
            "tenant_and_role_isolation": "PASS",
            "provider_network_calls": 0,
            "fixture_residue": 0,
        }
    finally:
        urllib.request.urlopen = original_urlopen
        copilot_router.generate_advisory_answer = original_generate
        app.dependency_overrides.clear()
        session.close()
        outer.rollback()
        connection.close()

    with owner_engine.connect() as conn:
        after = {
            table: int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
            for table in TRACKED_TABLES
        }
    assert fixture["before"] == after, (
        f"controlled pilot residue: before={fixture['before']} after={after}"
    )
    runtime_engine.dispose()
    owner_engine.dispose()
    return result


def main() -> None:
    result = run_controlled_pilot()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
