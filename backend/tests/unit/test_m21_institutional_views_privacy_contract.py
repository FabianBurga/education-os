from pathlib import Path

from app.modules.interventions.schemas import (
    InstitutionalInterventionItem,
    InstitutionalInterventionQueue,
    InterventionActionRead,
    InterventionFollowUpRead,
    InterventionRead,
)


def test_m21_db_institutional_queue_contract():
    item_fields = InstitutionalInterventionItem.model_fields
    queue_fields = InstitutionalInterventionQueue.model_fields
    assert "reason" not in item_fields
    assert "objective" not in item_fields
    assert "outcome_summary" not in item_fields
    assert "protected_detail" in item_fields
    assert "status_counts" in queue_fields
    assert "overdue_count" in queue_fields
    assert "unassigned_count" in queue_fields


def test_m21_db_detail_schemas_support_redaction():
    assert InterventionRead.model_fields["reason"].is_required() is False
    assert "protected_detail" in InterventionRead.model_fields
    assert InterventionFollowUpRead.model_fields["note"].is_required() is False
    assert "protected_detail" in InterventionFollowUpRead.model_fields
    assert "protected_detail" in InterventionActionRead.model_fields


def test_m21_db_privacy_module_redacts_free_text():
    source = (
        Path(__file__).resolve().parents[2]
        / "app" / "modules" / "interventions" / "institutional_views.py"
    ).read_text(encoding="utf-8")
    assert '"reason": None if protected else entity.reason' in source
    assert '"objective": None if protected else entity.objective' in source
    assert '"description": None if protected else action.description' in source
    assert '"note": None if protected else followup.note' in source


def test_m21_db_queue_is_management_only():
    source = (
        Path(__file__).resolve().parents[2]
        / "app" / "modules" / "interventions" / "institutional_views.py"
    ).read_text(encoding="utf-8")
    assert '"SYSTEM_ADMIN"' in source
    assert '"RECTOR"' in source
    assert '"ACADEMIC_COORDINATOR"' in source
    assert "HTTP_403_FORBIDDEN" in source


def test_m21_db_static_route_precedes_uuid_route():
    source = (
        Path(__file__).resolve().parents[2]
        / "app" / "modules" / "interventions" / "router.py"
    ).read_text(encoding="utf-8")
    assert source.index('"/institutional/queue"') < source.index(
        '@router.get("/{intervention_id}"'
    )


def test_m21_db_get_intervention_uses_privacy_sanitizer():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "interventions"
        / "service.py"
    ).read_text(encoding="utf-8")

    start = source.index("def get_intervention(\n")
    end = source.index("\n\ndef list_student_interventions(", start)
    block = source[start:end]

    assert "intervention_read_for_principal(" in block
    assert "return entity" not in block
