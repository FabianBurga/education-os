from app.modules.copilot.advisory import _sanitize_for_provider


def test_provider_minimization_strips_identifier_keys_recursively():
    source = {
        "student_profile_id": "student-secret-id",
        "academic_period_id": "period-secret-id",
        "overall_priority": "HIGH",
        "nested": {
            "person_id": "person-secret-id",
            "label": "safe",
        },
        "items": [
            {"institution_id": "inst-secret-id", "value": 3},
        ],
    }

    sanitized = _sanitize_for_provider(source)

    assert sanitized == {
        "overall_priority": "HIGH",
        "nested": {"label": "safe"},
        "items": [{"value": 3}],
    }
