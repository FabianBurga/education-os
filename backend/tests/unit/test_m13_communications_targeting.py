from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_m13_targeting_and_legacy_delivery_projection() -> None:
    schemas = (
        ROOT / "app" / "modules" / "communications" / "schemas.py"
    ).read_text(encoding="utf-8")
    service = (
        ROOT / "app" / "modules" / "communications" / "service.py"
    ).read_text(encoding="utf-8")

    for target_type in (
        "INSTITUTION",
        "CAMPUS",
        "SECTION",
        "COURSE",
        "STUDENT",
        "FAMILY",
    ):
        assert f'"{target_type}"' in schemas
        assert f'"{target_type}"' in service

    assert "GuardianStudentPortalAccess" not in service
    assert "guardian_student_portal_access" in service
    assert "FamilyNotice(" in service
    assert 'status="PUBLISHED"' in service
    assert "CommunicationRecipient(" in service
    assert "enqueue_event(" in service
    assert '"COMMUNICATION_PUBLISHED"' in service


def test_m13_delivery_report_uses_existing_family_receipts() -> None:
    service = (
        ROOT / "app" / "modules" / "communications" / "service.py"
    ).read_text(encoding="utf-8")
    assert "family_notice_receipts" in service
    assert "acknowledged_at" in service
    assert "read_at" in service
