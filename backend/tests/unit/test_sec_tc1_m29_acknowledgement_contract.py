from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "backend" / "alembic" / "versions" / "0047_sec_tc1_m29_acknowledgement_bridge.py"


def test_sec_tc1_migration_is_single_linear_successor_and_uses_secure_random_uuid():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "0047_sec_tc1_m29_ack_bridge"' in source
    assert 'down_revision: str | None = "0046_m28_attendance_perms"' in source
    assert source.count("pg_catalog.gen_random_uuid()::text") >= 2
    assert "CREATE EXTENSION" not in source
    assert "md5(" not in source.lower()


def test_sec_tc1_roles_functions_and_new_tables_are_narrowly_granted():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "education_context_issuer" in source
    assert "education_context_function_owner" in source
    assert "rolbypassrls" in source
    assert "session_user <> 'education_context_issuer'" in source
    assert "session_user <> 'education_app'" in source
    assert "REVOKE ALL ON FUNCTION public.sec_tc1_issue_capability" in source
    assert "TO education_context_issuer" in source
    assert "REVOKE ALL ON TABLE public.sec_tc1_capabilities" in source
    for table in (
        "sec_tc1_capabilities",
        "intervention_followup_acknowledgement_evidence_links",
        "intervention_followup_acknowledgement_evidence_corrections",
        "accountability_obligation_acknowledgement_evidence_links",
        "accountability_obligation_acknowledgement_evidence_corrections",
    ):
        assert table in source
    assert 'ENABLE ROW LEVEL SECURITY' in source
    assert 'FORCE ROW LEVEL SECURITY' in source
    for trigger_name in (
        "sec_tc1_hist_immutable_1",
        "sec_tc1_hist_immutable_2",
        "sec_tc1_hist_immutable_3",
        "sec_tc1_hist_immutable_4",
        "sec_tc1_hist_no_truncate_1",
        "sec_tc1_hist_no_truncate_2",
        "sec_tc1_hist_no_truncate_3",
        "sec_tc1_hist_no_truncate_4",
    ):
        assert trigger_name in source


def test_sec_tc1_operations_are_typed_audited_and_do_not_change_domain_lifecycle():
    source = MIGRATION.read_text(encoding="utf-8")
    for name in (
        "m21_link_acknowledgement_evidence",
        "m21_correct_acknowledgement_evidence",
        "m27_link_acknowledgement_evidence",
        "m27_correct_acknowledgement_evidence",
    ):
        assert f"public.{name}" in source
    assert 'public.{domain}_read_acknowledgement_evidence' in source
    assert "student.intervention.followup.acknowledgement_evidence.linked" in source
    assert "student.intervention.followup.acknowledgement_evidence.corrected" in source
    assert "accountability.obligation.acknowledgement_evidence.linked" in source
    assert "accountability.obligation.acknowledgement_evidence.corrected" in source
    assert "follow-up completion" not in source.lower()
    assert "COMMUNICATION_PUBLISHED" not in source
    assert "WRONG_CONTEXT" in source and "DUPLICATE_ASSOCIATION" in source
    assert "ACKNOWLEDGEMENT_NOT_RELEVANT" in source
    m13 = source.split("CREATE FUNCTION public.m13_acknowledge_family_notice", 1)[1].split("ALTER FUNCTION public.m13_acknowledge_family_notice", 1)[0]
    assert m13.index("guardian grant unavailable") < m13.index("IF c.result_id IS NOT NULL")
    assert m13.index("IF c.result_id IS NOT NULL") < m13.index("FAMILY_NOTICE_ACKNOWLEDGED")


def test_issuer_engine_requires_distinct_explicit_issuer_url():
    source = (ROOT / "backend" / "app" / "db" / "session.py").read_text(encoding="utf-8")
    assert "TRUSTED_CONTEXT_ISSUER_DATABASE_URL" in source
    assert "settings.DATABASE_URL" in source
    assert "settings.OWNER_DATABASE_URL" in source
    assert 'parsed.username != "education_context_issuer"' in source
    assert "fall back" in source.lower()


def test_provisioner_does_not_contain_a_password_and_suppresses_errors():
    source = (ROOT / "scripts" / "provision_sec_tc1_roles.py").read_text(encoding="utf-8")
    assert "TRUSTED_CONTEXT_ISSUER_PASSWORD" in source
    assert "OWNER_DATABASE_URL" in source
    assert "sql.Literal(password)" in source
    assert "Secret values and exception details are suppressed" in source
    assert "education_context_issuer" in source and "education_context_function_owner" in source


def test_m13_acknowledgement_is_guardian_bound_and_database_validated():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "'M13_NOTICE_ACK'" in source
    assert "p_guardian_profile uuid" in source
    assert "gp.id=p_guardian_profile" in source
    assert "gp.id=v_cap.guardian_profile_id" in source
    assert "CREATE FUNCTION public.m13_acknowledge_family_notice" in source
    assert "FAMILY_NOTICE_ACKNOWLEDGED" in source
    assert "IF c.result_id IS NOT NULL THEN RETURN c.result_id; END IF;" in source


def test_receipt_acknowledged_at_is_not_directly_writable_by_runtime():
    source = MIGRATION.read_text(encoding="utf-8")
    service = (ROOT / "backend" / "app" / "modules" / "family_portal" / "service.py").read_text(encoding="utf-8")
    assert "REVOKE INSERT, UPDATE, DELETE ON TABLE public.family_notice_receipts FROM education_app" in source
    assert "GRANT INSERT (id, organization_id, institution_id, family_notice_id, guardian_profile_id, read_at)" in source
    assert "GRANT UPDATE (read_at) ON TABLE public.family_notice_receipts TO education_app" in source
    assert "INSERT INTO family_notice_receipts(" in service
    assert "guardian_profile_id, read_at" in service
    assert "SET read_at=COALESCE(read_at,:read_at)" in service
    assert "acknowledged_at=now()" not in service


def test_same_active_operation_issuance_converges_without_rotating_token():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "c.expires_at>clock_timestamp()" in source
    assert "c.result_id IS NOT NULL AND p_purpose NOT IN ('M21_ACK_READ','M27_ACK_READ')" in source
    assert "IF FOUND THEN RETURN v_token; END IF;" in source
    assert "consumed_at=NULL" in source
    assert "result_id" in source


def test_only_post_0047_protected_m13_acknowledgements_are_linkable():
    source = MIGRATION.read_text(encoding="utf-8")
    provenance = "ack.result_id=r.id AND ack.target_id=n.id AND ack.guardian_profile_id=r.guardian_profile_id"
    assert source.count(provenance) >= 1
    assert "ack.purpose='M13_NOTICE_ACK'" in source
    assert source.count("ack.consumed_at IS NOT NULL") >= 2
    assert "UPDATE public.sec_tc1_capabilities SET consumed_at=clock_timestamp(),result_id=v_id" in source
    assert "(SELECT count(*) FROM public.sec_tc1_capabilities)" in source.split("def downgrade()", 1)[1]
