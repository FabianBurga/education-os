from app.modules.intelligence.models import (
    CohortIntelligenceDaily,
    InstitutionIntelligenceDaily,
    StudentIntelligenceSnapshot,
)


def test_m22_analytical_model_table_names():
    assert (
        StudentIntelligenceSnapshot.__tablename__
        == "student_intelligence_snapshots"
    )
    assert CohortIntelligenceDaily.__tablename__ == "cohort_intelligence_daily"
    assert (
        InstitutionIntelligenceDaily.__tablename__
        == "institution_intelligence_daily"
    )


def test_m22_models_expose_policy_provenance_fields():
    for model in (
        StudentIntelligenceSnapshot,
        CohortIntelligenceDaily,
        InstitutionIntelligenceDaily,
    ):
        fields = set(model.model_fields)
        assert {
            "rule_set_version",
            "projection_version",
            "policy_source",
            "policy_key",
            "policy_version",
            "control_revision",
        } <= fields


def test_m22_student_snapshot_keeps_dimension_priorities_separate():
    fields = set(StudentIntelligenceSnapshot.model_fields)
    assert {
        "overall_priority",
        "attendance_priority",
        "academic_priority",
        "intervention_priority",
        "evidence_count",
        "window_start",
        "window_end",
    } <= fields
