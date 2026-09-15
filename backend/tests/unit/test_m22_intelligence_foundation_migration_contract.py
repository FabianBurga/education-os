import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "alembic"
    / "versions"
    / "0025_m22_intelligence_foundation.py"
)


def _src() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _tree() -> ast.AST:
    return ast.parse(_src())


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _create_table_names() -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node) != "op.create_table" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            names.add(first.value)
    return names


def _ast_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
                continue
            if (
                isinstance(value, ast.FormattedValue)
                and isinstance(value.value, ast.Name)
            ):
                parts.append("{" + value.value.id + "}")
                continue
            return None
        return "".join(parts)
    return None


def _check_constraint_expressions() -> dict[str, str]:
    constraints: dict[str, str] = {}
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node) != "sa.CheckConstraint" or not node.args:
            continue

        expr = _ast_string(node.args[0])
        if expr is None:
            continue

        name = None
        for kw in node.keywords:
            if kw.arg == "name":
                name = _ast_string(kw.value)

        if name:
            constraints[name] = expr
    return constraints


def test_m22_0025_revision_contract():
    src = _src()

    assert 'revision: str = "0025_m22_intelligence_foundation"' in src
    assert 'down_revision: str | None = "0024_m21_projection_boundary"' in src


def test_m22_0025_creates_only_three_analytical_tables():
    assert _create_table_names() == {
        "student_intelligence_snapshots",
        "cohort_intelligence_daily",
        "institution_intelligence_daily",
    }

    src = _src()
    forbidden = {
        "intervention_intelligence_snapshot",
        'op.alter_column("intelligence_signals"',
        'op.alter_column("interventions"',
        'op.alter_column("student_timeline_entries"',
    }
    for token in forbidden:
        assert token not in src


def test_m22_0025_policy_provenance_contract():
    src = _src()

    for token in (
        '"rule_set_version"',
        '"projection_version"',
        '"policy_source"',
        '"policy_key"',
        '"policy_version"',
        '"control_revision"',
        "'BUILTIN_DEFAULT'",
        "'CONTROL_PLANE'",
        "control_revision IS NULL",
        "control_revision > 0",
    ):
        assert token in src

    assert '"policy_json"' not in src
    assert "institution_policy_controls.id" not in src



def test_m22_0025_policy_provenance_rejects_sql_null_control_revision():
    checks = _check_constraint_expressions()
    expr = checks["ck_{prefix}_policy_provenance"]

    assert (
        "policy_source = 'BUILTIN_DEFAULT' AND control_revision IS NULL"
        in expr
    )
    assert (
        "policy_source = 'CONTROL_PLANE' "
        "AND control_revision IS NOT NULL "
        "AND control_revision > 0"
        in expr
    )


def test_m22_0025_student_snapshot_contract():
    src = _src()
    checks = _check_constraint_expressions()

    for token in (
        '"overall_priority"',
        '"attendance_priority"',
        '"academic_priority"',
        '"intervention_priority"',
        '"evidence_count"',
        '"window_start"',
        '"window_end"',
        "uq_student_intelligence_snapshots_identity",
        "fk_student_intelligence_snapshots_student_inst",
        "fk_student_intelligence_snapshots_period_inst",
        "ix_student_intelligence_snapshots_priority_queue",
    ):
        assert token in src

    assert (
        checks["ck_student_intelligence_snapshots_overall_priority"]
        == "overall_priority IN ('LOW','MEDIUM','HIGH')"
    )
    assert (
        checks["ck_student_intelligence_snapshots_attendance_priority"]
        == "attendance_priority IN ('LOW','MEDIUM','HIGH')"
    )
    assert (
        checks["ck_student_intelligence_snapshots_academic_priority"]
        == "academic_priority IN ('LOW','MEDIUM','HIGH')"
    )
    assert (
        checks["ck_student_intelligence_snapshots_intervention_priority"]
        == "intervention_priority IN ('LOW','MEDIUM','HIGH')"
    )


def test_m22_0025_cohort_privacy_and_idempotency_contract():
    src = _src()
    checks = _check_constraint_expressions()

    for token in (
        '"cohort_type"',
        '"cohort_ref_id"',
        '"suppressed"',
        "uq_cohort_intelligence_daily_identity_ref",
        "uq_cohort_intelligence_daily_identity_institution",
        "postgresql_where",
    ):
        assert token in src

    suppression = checks["ck_cohort_intelligence_daily_suppression"]
    assert "suppressed = true AND high_priority_count IS NULL" in suppression
    assert "medium_priority_count IS NULL" in suppression
    assert "attendance_risk_count IS NULL" in suppression
    assert "academic_risk_count IS NULL" in suppression
    assert "active_intervention_count IS NULL" in suppression
    assert "overdue_followup_count IS NULL" in suppression

    assert "suppressed = false AND high_priority_count IS NOT NULL" in suppression
    assert "medium_priority_count IS NOT NULL" in suppression
    assert "attendance_risk_count IS NOT NULL" in suppression
    assert "academic_risk_count IS NOT NULL" in suppression
    assert "active_intervention_count IS NOT NULL" in suppression
    assert "overdue_followup_count IS NOT NULL" in suppression

    identity = checks["ck_cohort_intelligence_daily_identity"]
    assert "cohort_type = 'INSTITUTION' AND cohort_ref_id IS NULL" in identity
    assert "cohort_type <> 'INSTITUTION' AND cohort_ref_id IS NOT NULL" in identity


def test_m22_0025_institution_daily_contract():
    src = _src()

    for token in (
        '"in_scope_student_count"',
        '"high_priority_count"',
        '"medium_priority_count"',
        '"active_intervention_count"',
        '"interventions_without_action_count"',
        '"overdue_followup_count"',
        '"positive_outcome_count"',
        '"unresolved_outcome_count"',
        "uq_institution_intelligence_daily_identity",
    ):
        assert token in src


def test_m22_0025_force_rls_and_tenant_isolation_contract():
    src = _src()

    assert "ENABLE ROW LEVEL SECURITY" in src
    assert "FORCE ROW LEVEL SECURITY" in src
    assert "TO education_app" in src
    assert "USING ({TENANT})" in src
    assert "WITH CHECK ({TENANT})" in src

    assert "organization_id = {ORG_CTX} AND institution_id = {INST_CTX}" in src


def test_m22_0025_downgrade_is_m22_only():
    src = _src()
    downgrade = src.split("def downgrade() -> None:", 1)[1]

    for table in (
        "cohort_intelligence_daily",
        "institution_intelligence_daily",
        "student_intelligence_snapshots",
    ):
        assert f'op.drop_table("{table}")' in downgrade

    for forbidden in (
        "intelligence_signals",
        "interventions",
        "student_timeline_entries",
        "institution_policy_controls",
        "institution_control_changes",
    ):
        assert forbidden not in downgrade
