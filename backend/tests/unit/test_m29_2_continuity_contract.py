import os
from pathlib import Path
from uuid import UUID

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://education_app:education_app_dev@127.0.0.1:5432/education_os")

from app.api.deps import CurrentPrincipal
from app.security.trusted_context import (
    batch_operation_key,
    canonical_batch_target_digest,
)

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "backend" / "alembic" / "versions" / "0048_m29_batch_ack_reads.py"


def _principal() -> CurrentPrincipal:
    return CurrentPrincipal(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        organization_id=UUID("00000000-0000-0000-0000-000000000002"),
        institution_id=UUID("00000000-0000-0000-0000-000000000003"),
    )


def test_batch_target_digest_is_order_independent_and_tenant_bound():
    principal = _principal()
    first = UUID("00000000-0000-0000-0000-000000000010")
    second = UUID("00000000-0000-0000-0000-000000000011")
    digest_a = canonical_batch_target_digest(
        purpose="M21_ACK_BATCH_READ",
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        target_ids=[first, second],
    )
    digest_b = canonical_batch_target_digest(
        purpose="M21_ACK_BATCH_READ",
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        target_ids=[second, first],
    )
    digest_other_tenant = canonical_batch_target_digest(
        purpose="M21_ACK_BATCH_READ",
        organization_id=UUID("00000000-0000-0000-0000-000000000099"),
        institution_id=principal.institution_id,
        target_ids=[first, second],
    )
    assert digest_a == digest_b
    assert digest_a != digest_other_tenant


def test_batch_operation_key_converges_for_equivalent_retries():
    principal = _principal()
    target_ids = [
        UUID("00000000-0000-0000-0000-000000000010"),
        UUID("00000000-0000-0000-0000-000000000011"),
    ]
    assert batch_operation_key(
        principal=principal,
        purpose="M21_ACK_BATCH_READ",
        target_ids=target_ids,
    ) == batch_operation_key(
        principal=principal,
        purpose="M21_ACK_BATCH_READ",
        target_ids=list(reversed(target_ids)),
    )


def test_batch_contract_has_no_new_permission_event_or_persistence_authority():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'M21_ACK_BATCH_READ' in source
    assert 'M27_ACK_BATCH_READ' in source
    assert 'target_set_digest' in source
    assert 'GRANT EXECUTE ON FUNCTION public.m21_read_acknowledgement_evidence_batch' in source
    assert 'GRANT EXECUTE ON FUNCTION public.m27_read_acknowledgement_evidence_batch' in source
    assert 'GRANT EXECUTE ON FUNCTION public.sec_tc1_issue_batch_capability' in source
    assert 'revoke_roles = "PUBLIC, education_context_issuer" if signature != _BATCH_FUNCTIONS[0]' in source
    assert 'COMMUNICATION_PUBLISHED' not in source
    assert 'CREATE TABLE' not in source
    assert 'teacher.continuity.view' not in source


def test_batch_functions_omit_sensitive_family_payload_and_hidden_targets():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'guardian_profile_id' not in source.split('CREATE FUNCTION public.m21_read_acknowledgement_evidence_batch', 1)[1].split('CREATE FUNCTION public.m27_read_acknowledgement_evidence_batch', 1)[0].split('RETURNS TABLE', 1)[1].split(') LANGUAGE', 1)[0]
    assert 'delivery_report' not in source
    assert 'RETURN QUERY' in source
    assert 'FROM authorized a LEFT JOIN effective e' in source


def test_continuity_orchestration_uses_source_reads_and_stable_retry_keys():
    service = (ROOT / "backend" / "app" / "modules" / "continuity" / "service.py").read_text(encoding="utf-8")
    assert "list_authorized_followup_targets" in service
    assert "list_authorized_obligation_targets" in service
    assert "read_followup_acknowledgement_batch" in service
    assert "read_obligation_acknowledgement_batch" in service
    assert "batch_operation_key" in service
    assert "uuid4" not in service
    assert "acknowledgement_evidence_links" not in service
    assert "sec_tc1_capabilities" not in service


def test_continuity_route_is_read_only_and_bounded():
    router = (ROOT / "backend" / "app" / "modules" / "continuity" / "router.py").read_text(encoding="utf-8")
    assert '@router.get("/worklist"' in router
    assert "le=25" in router
    assert "@router.post" not in router
    assert "@router.put" not in router
    assert "@router.delete" not in router


def test_continuity_deep_links_target_existing_authoritative_routes():
    service = (ROOT / "backend" / "app" / "modules" / "continuity" / "service.py").read_text(encoding="utf-8")
    assert '"/m21/interventions/{row[\'intervention_id\']}"' in service
    assert '"/accountability/cases/{row[\'case_id\']}"' in service
    assert "/followups/" not in service
