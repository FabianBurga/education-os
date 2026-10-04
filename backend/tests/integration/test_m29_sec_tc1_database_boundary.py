import os
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.accountability.acknowledgement_evidence import (
    read_obligation_acknowledgement_batch,
)
from app.modules.interventions.acknowledgement_evidence import (
    read_followup_acknowledgement_batch,
)
from app.security import trusted_context

OWNER_URL = os.getenv(
    "OWNER_DATABASE_URL_PG",
    "postgresql://education_owner:education_owner_dev@127.0.0.1:5432/education_os",
)
APP_URL = os.getenv(
    "DATABASE_URL_PG",
    "postgresql://education_app:education_app_dev@127.0.0.1:5432/education_os",
)
ISSUER_URL = os.getenv("TRUSTED_CONTEXT_ISSUER_DATABASE_URL_PG") or os.getenv("TRUSTED_CONTEXT_ISSUER_DATABASE_URL")

TABLES = (
    "sec_tc1_capabilities",
    "intervention_followup_acknowledgement_evidence_links",
    "intervention_followup_acknowledgement_evidence_corrections",
    "accountability_obligation_acknowledgement_evidence_links",
    "accountability_obligation_acknowledgement_evidence_corrections",
)


def _require_revision(cur):
    cur.execute("SELECT version_num FROM alembic_version")
    if cur.fetchone()[0] not in {"0047_sec_tc1_m29_ack_bridge", "0048_m29_batch_ack_reads"}:
        pytest.skip("SEC-TC1 migration 0047/0048 is not installed in this test database")


def _local_url(value: str, expected_user: str) -> str:
    parsed = make_url(value)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or parsed.database != "education_os":
        pytest.fail("M29 SEC-TC1 integration tests only allow localhost/education_os")
    if parsed.username != expected_user:
        pytest.fail(f"M29 SEC-TC1 integration URL must use {expected_user}")
    return parsed.set(drivername="postgresql").render_as_string(hide_password=False)


def _require_runtime_urls():
    if not ISSUER_URL:
        pytest.skip("TRUSTED_CONTEXT_ISSUER_DATABASE_URL is required for M13 capability integration tests")
    return (
        _local_url(OWNER_URL, "education_owner"),
        _local_url(APP_URL, "education_app"),
        _local_url(ISSUER_URL, "education_context_issuer"),
    )


@pytest.fixture
def m13_guardian_fixture():
    owner_url, _app_url, _issuer_url = _require_runtime_urls()
    org_id, inst_id, guardian_person, student_person = uuid4(), uuid4(), uuid4(), uuid4()
    user_id, staff_person, staff_user, staff_role, staff_membership = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    guardian_id, student_id, grant_id = uuid4(), uuid4(), uuid4()
    notice_id, legacy_notice_id, legacy_receipt_id = uuid4(), uuid4(), uuid4()
    intervention_id, followup_id, replacement_followup_id, race_followup_id = uuid4(), uuid4(), uuid4(), uuid4()
    case_id, obligation_id = uuid4(), uuid4()
    email = f"sec-tc1-{user_id}@example.invalid"
    payload = {
        "org": org_id, "inst": inst_id, "guardian_person": guardian_person,
        "student_person": student_person, "user": user_id, "guardian": guardian_id,
        "staff_person": staff_person, "staff_user": staff_user, "staff_role": staff_role,
        "staff_membership": staff_membership,
        "student": student_id, "grant": grant_id, "notice": notice_id,
        "legacy_notice": legacy_notice_id, "legacy_receipt": legacy_receipt_id,
        "intervention": intervention_id, "followup": followup_id,
        "replacement_followup": replacement_followup_id, "race_followup": race_followup_id,
        "case": case_id,
        "obligation": obligation_id,
        "email": email,
    }
    # Skip before allocating fixture IDs if the local DB has not migrated.
    with psycopg.connect(_local_url(OWNER_URL, "education_owner")) as conn, conn.cursor() as cur:
        _require_revision(cur)
    try:
        with psycopg.connect(_local_url(OWNER_URL, "education_owner")) as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO organizations(id,name,status,created_at) VALUES(%s,%s,'ACTIVE',now())", (org_id, "SEC-TC1 Test Org"))
            cur.execute("INSERT INTO institutions(id,organization_id,name,type,status,created_at) VALUES(%s,%s,%s,'PRIVATE','ACTIVE',now())", (inst_id, org_id, "SEC-TC1 Test Institution"))
            cur.execute("INSERT INTO persons(id,organization_id,given_names,family_names,created_at) VALUES(%s,%s,'Synthetic Guardian','Test',now()),(%s,%s,'Synthetic Student','Test',now())", (guardian_person, org_id, student_person, org_id))
            cur.execute("INSERT INTO user_accounts(id,person_id,login_email,password_hash,is_active,created_at) VALUES(%s,%s,%s,'test',true,now())", (user_id, guardian_person, email))
            cur.execute("INSERT INTO persons(id,organization_id,given_names,family_names,created_at) VALUES(%s,%s,'Synthetic Coordinator','Test',now())", (staff_person, org_id))
            cur.execute("INSERT INTO user_accounts(id,person_id,login_email,password_hash,is_active,created_at) VALUES(%s,%s,%s,'test',true,now())", (staff_user, staff_person, f"sec-tc1-staff-{staff_user}@example.invalid"))
            cur.execute("INSERT INTO memberships(id,user_id,institution_id,status,created_at) VALUES(%s,%s,%s,'ACTIVE',now())", (staff_membership, staff_user, inst_id))
            cur.execute("INSERT INTO roles(id,institution_id,key,name) VALUES(%s,%s,'RECTOR','SEC-TC1 Synthetic Rector')", (staff_role, inst_id))
            cur.execute("INSERT INTO membership_roles(membership_id,role_id) VALUES(%s,%s)", (staff_membership, staff_role))
            cur.execute("""INSERT INTO role_permissions(role_id,permission_id)
                           SELECT %s,id FROM permissions WHERE key = ANY(%s)""",
                        (staff_role, ["communications.delivery.view", "intervention.read", "intervention.followup.acknowledgement_evidence.manage", "accountability.view", "accountability.obligation.acknowledgement_evidence.manage"]))
            assert cur.rowcount == 5, "SEC-TC1 test requires all current staff permissions"
            cur.execute("INSERT INTO guardian_profiles(id,organization_id,institution_id,person_id,status,created_at) VALUES(%s,%s,%s,%s,'ACTIVE',now())", (guardian_id, org_id, inst_id, guardian_person))
            cur.execute("INSERT INTO student_profiles(id,organization_id,institution_id,person_id,status,created_at,updated_at) VALUES(%s,%s,%s,%s,'ACTIVE',now(),now())", (student_id, org_id, inst_id, student_person))
            cur.execute("INSERT INTO guardian_student_portal_access(id,organization_id,institution_id,guardian_profile_id,student_profile_id,access_level,status,granted_at) VALUES(%s,%s,%s,%s,%s,'STANDARD','ACTIVE',now())", (grant_id, org_id, inst_id, guardian_id, student_id))
            for target_id in (notice_id, legacy_notice_id):
                cur.execute("""INSERT INTO family_notices(id,organization_id,institution_id,student_profile_id,notice_type,title,body,requires_acknowledgement,status,published_at,created_at)
                               VALUES(%s,%s,%s,%s,'GENERAL','Synthetic title','Synthetic body',true,'PUBLISHED',now(),now())""",
                            (target_id, org_id, inst_id, student_id))
            cur.execute("""INSERT INTO interventions(
                           id,organization_id,institution_id,student_profile_id,intervention_type,severity,status,
                           sensitivity,title,reason,origin_type,opened_by_user_id,opened_at,created_at,updated_at)
                           VALUES(%s,%s,%s,%s,'ACADEMIC_SUPPORT','MEDIUM','OPEN','GENERAL',
                                  'Synthetic M29 follow-up','Synthetic test only','HUMAN',%s,now(),now(),now())""",
                        (intervention_id, org_id, inst_id, student_id, staff_user))
            for target_id in (followup_id, replacement_followup_id, race_followup_id):
                cur.execute("""INSERT INTO intervention_followups(
                               id,organization_id,institution_id,intervention_id,followup_type,sensitivity,note,
                               observed_at,created_by_user_id,created_at)
                               VALUES(%s,%s,%s,%s,'FAMILY_CONTACT','GENERAL','Synthetic test note',now(),%s,now())""",
                            (target_id, org_id, inst_id, intervention_id, staff_user))
            cur.execute("""INSERT INTO accountability_cases(
                           id,organization_id,institution_id,subject_type,subject_id,source_category,
                           normalized_category,identity_key_sha256,episode_anchor,primary_owner_user_id,
                           owner_state,created_at,updated_at)
                           VALUES(%s,%s,%s,'STUDENT',%s,'SEC_TC1_TEST','SOURCE:SEC_TC1_TEST',%s,'sec-tc1-test',%s,'ASSIGNED',now(),now())""",
                        (case_id, org_id, inst_id, student_id, "a" * 64, staff_user))
            cur.execute("""INSERT INTO accountability_obligations(
                           id,organization_id,institution_id,case_id,origin_type,origin_id,obligation_type,
                           next_required_step,identity_key_sha256,sla_status,sla_resolution_sha256,
                           provenance_sha256,creation_idempotency_key)
                           VALUES(%s,%s,%s,%s,'CASE',%s,'INFORMATION_REQUIRED','REQUEST_INFORMATION',
                                  %s,'RESOLVED',%s,%s,%s)""",
                        (obligation_id, org_id, inst_id, case_id, case_id, "b" * 64, "c" * 64, "d" * 64, sha256(f"obligation:{obligation_id}".encode()).hexdigest()))
            cur.execute("""INSERT INTO family_notice_receipts(id,organization_id,institution_id,family_notice_id,guardian_profile_id,read_at,acknowledged_at,created_at)
                           VALUES(%s,%s,%s,%s,%s,now(),now(),now())""",
                        (legacy_receipt_id, org_id, inst_id, legacy_notice_id, guardian_id))
        yield payload
    finally:
        history_triggers = (
            ("intervention_followup_acknowledgement_evidence_links", "sec_tc1_hist_immutable_1"),
            ("intervention_followup_acknowledgement_evidence_corrections", "sec_tc1_hist_immutable_2"),
            ("accountability_obligation_acknowledgement_evidence_links", "sec_tc1_hist_immutable_3"),
            ("accountability_obligation_acknowledgement_evidence_corrections", "sec_tc1_hist_immutable_4"),
        )
        # Cleanup is confined to the locally asserted test database and this
        # fixture's UUID tenant. Trigger state and deletes share one transaction:
        # any failure rolls back both, leaving append-only enforcement enabled.
        with psycopg.connect(_local_url(OWNER_URL, "education_owner")) as conn, conn.cursor() as cur:
            for table, trigger in history_triggers:
                cur.execute(
                    "SELECT tgenabled FROM pg_catalog.pg_trigger WHERE tgrelid=%s::regclass AND tgname=%s AND NOT tgisinternal",
                    (f"public.{table}", trigger),
                )
                if cur.fetchone() != ("O",):
                    raise RuntimeError(f"Expected enabled fixture cleanup trigger {trigger}")
            for table, trigger in history_triggers:
                cur.execute(f'ALTER TABLE public."{table}" DISABLE TRIGGER "{trigger}"')

            cur.execute("DELETE FROM intervention_followup_acknowledgement_evidence_corrections WHERE organization_id=%s AND institution_id=%s", (org_id, inst_id))
            cur.execute("DELETE FROM intervention_followup_acknowledgement_evidence_links WHERE organization_id=%s AND institution_id=%s", (org_id, inst_id))
            cur.execute("DELETE FROM accountability_obligation_acknowledgement_evidence_corrections WHERE organization_id=%s AND institution_id=%s", (org_id, inst_id))
            cur.execute("DELETE FROM accountability_obligation_acknowledgement_evidence_links WHERE organization_id=%s AND institution_id=%s", (org_id, inst_id))
            cur.execute("DELETE FROM sec_tc1_capabilities WHERE actor_user_id=ANY(%s)", ([user_id, staff_user],))
            cur.execute("DELETE FROM audit_logs WHERE actor_user_id=ANY(%s) OR entity_id=ANY(%s)", ([user_id, staff_user], [notice_id, legacy_notice_id, legacy_receipt_id]))
            cur.execute("DELETE FROM family_notice_receipts WHERE id=%s OR family_notice_id=ANY(%s)", (legacy_receipt_id, [notice_id, legacy_notice_id]))
            cur.execute("DELETE FROM family_notices WHERE id=ANY(%s)", ([notice_id, legacy_notice_id],))
            cur.execute("DELETE FROM accountability_obligations WHERE id=%s", (obligation_id,))
            cur.execute("DELETE FROM accountability_cases WHERE id=%s", (case_id,))
            cur.execute("DELETE FROM intervention_followups WHERE id=ANY(%s)", ([followup_id, replacement_followup_id, race_followup_id],))
            cur.execute("DELETE FROM interventions WHERE id=%s", (intervention_id,))
            cur.execute("DELETE FROM guardian_student_portal_access WHERE id=%s", (grant_id,))
            cur.execute("DELETE FROM student_profiles WHERE id=%s", (student_id,))
            cur.execute("DELETE FROM guardian_profiles WHERE id=%s", (guardian_id,))
            cur.execute("DELETE FROM membership_roles WHERE membership_id=%s", (staff_membership,))
            cur.execute("DELETE FROM role_permissions WHERE role_id=%s", (staff_role,))
            cur.execute("DELETE FROM roles WHERE id=%s", (staff_role,))
            cur.execute("DELETE FROM memberships WHERE user_id=ANY(%s)", ([user_id, staff_user],))
            cur.execute("DELETE FROM user_accounts WHERE id=ANY(%s)", ([user_id, staff_user],))
            cur.execute("DELETE FROM persons WHERE id=ANY(%s)", ([guardian_person, student_person, staff_person],))
            cur.execute("DELETE FROM institutions WHERE id=%s", (inst_id,))
            cur.execute("DELETE FROM organizations WHERE id=%s", (org_id,))
            for table, trigger in history_triggers:
                cur.execute(f'ALTER TABLE public."{table}" ENABLE TRIGGER "{trigger}"')

            cleanup_checks = (
                ("sec_tc1_capabilities", "actor_user_id=ANY(%s)", ([user_id, staff_user],)),
                ("intervention_followup_acknowledgement_evidence_links", "organization_id=%s AND institution_id=%s", (org_id, inst_id)),
                ("intervention_followup_acknowledgement_evidence_corrections", "organization_id=%s AND institution_id=%s", (org_id, inst_id)),
                ("accountability_obligation_acknowledgement_evidence_links", "organization_id=%s AND institution_id=%s", (org_id, inst_id)),
                ("accountability_obligation_acknowledgement_evidence_corrections", "organization_id=%s AND institution_id=%s", (org_id, inst_id)),
                ("audit_logs", "actor_user_id=ANY(%s)", ([user_id, staff_user],)),
                ("family_notice_receipts", "id=%s OR family_notice_id=ANY(%s)", (legacy_receipt_id, [notice_id, legacy_notice_id])),
                ("family_notices", "id=ANY(%s)", ([notice_id, legacy_notice_id],)),
                ("accountability_obligations", "id=%s", (obligation_id,)),
                ("accountability_cases", "id=%s", (case_id,)),
                ("intervention_followups", "id=ANY(%s)", ([followup_id, replacement_followup_id, race_followup_id],)),
                ("interventions", "id=%s", (intervention_id,)),
                ("guardian_student_portal_access", "id=%s", (grant_id,)),
                ("student_profiles", "id=%s", (student_id,)),
                ("guardian_profiles", "id=%s", (guardian_id,)),
                ("membership_roles", "membership_id=%s", (staff_membership,)),
                ("role_permissions", "role_id=%s", (staff_role,)),
                ("roles", "id=%s", (staff_role,)),
                ("memberships", "user_id=ANY(%s)", ([user_id, staff_user],)),
                ("user_accounts", "id=ANY(%s)", ([user_id, staff_user],)),
                ("persons", "id=ANY(%s)", ([guardian_person, student_person, staff_person],)),
                ("institutions", "id=%s", (inst_id,)),
                ("organizations", "id=%s", (org_id,)),
            )
            for table, predicate, params in cleanup_checks:
                cur.execute(f'SELECT count(*) FROM public."{table}" WHERE {predicate}', params)
                if cur.fetchone()[0] != 0:
                    raise RuntimeError(f"SEC-TC1 fixture cleanup left rows in {table}")
            for table, trigger in history_triggers:
                cur.execute(
                    "SELECT tgenabled FROM pg_catalog.pg_trigger WHERE tgrelid=%s::regclass AND tgname=%s AND NOT tgisinternal",
                    (f"public.{table}", trigger),
                )
                if cur.fetchone() != ("O",):
                    raise RuntimeError(f"SEC-TC1 fixture cleanup did not re-enable {trigger}")


def _issue_m13_capability(urls, fixture, op_key=None):
    _owner_url, _app_url, issuer_url = urls
    operation_key = op_key or sha256(f"ack:{fixture['user']}:{fixture['notice']}".encode()).hexdigest()
    fingerprint = sha256(f"M13_NOTICE_ACK:{fixture['org']}:{fixture['inst']}:{fixture['notice']}:{fixture['guardian']}".encode()).hexdigest()
    with psycopg.connect(issuer_url) as conn, conn.cursor() as cur:
        cur.execute("""SELECT public.sec_tc1_issue_capability(
            'M13_NOTICE_ACK',%s,%s,%s,NULL,%s,%s,NULL,NULL,NULL,%s,%s)""",
            (fixture['user'], fixture['org'], fixture['inst'], fixture['notice'], fixture['guardian'], operation_key, fingerprint))
        return cur.fetchone()[0]


def _consume_m13_capability(urls, capability):
    _owner_url, app_url, _issuer_url = urls
    with psycopg.connect(_local_url(APP_URL, "education_app")) as conn, conn.cursor() as cur:
        cur.execute("SELECT public.m13_acknowledge_family_notice(%s)", (capability,))
        receipt_id = cur.fetchone()[0]
        conn.commit()
        return receipt_id


def _issue_staff_capability(urls, fixture, purpose, receipt_id, target_id, *, related_link=None, replacement_target=None, reason=None):
    _owner_url, _app_url, issuer_url = urls
    bound = ":".join(str(value) if value is not None else "-" for value in (
        purpose, fixture["staff_user"], fixture["org"], fixture["inst"], receipt_id,
        target_id, related_link, replacement_target, reason,
    ))
    operation_key = sha256(f"operation:{bound}".encode()).hexdigest()
    fingerprint = sha256(f"fingerprint:{bound}".encode()).hexdigest()
    with psycopg.connect(issuer_url) as conn, conn.cursor() as cur:
        cur.execute("""SELECT public.sec_tc1_issue_capability(
            %s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s)""",
            (purpose, fixture["staff_user"], fixture["org"], fixture["inst"], receipt_id,
             target_id, related_link, replacement_target, reason, operation_key, fingerprint))
        return cur.fetchone()[0]


def _consume_staff_capability(urls, operation, capability):
    allowed = {
        "M21_ACK_LINK": "m21_link_acknowledgement_evidence",
        "M21_ACK_CORRECT": "m21_correct_acknowledgement_evidence",
        "M21_ACK_READ": "m21_read_acknowledgement_evidence",
        "M27_ACK_LINK": "m27_link_acknowledgement_evidence",
        "M27_ACK_CORRECT": "m27_correct_acknowledgement_evidence",
        "M27_ACK_READ": "m27_read_acknowledgement_evidence",
    }
    _owner_url, app_url, _issuer_url = urls
    with psycopg.connect(app_url) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM public.{allowed[operation]}(%s)", (capability,))
        rows = cur.fetchall()
        conn.commit()
        return rows[0][0] if operation.endswith(("_LINK", "_CORRECT")) else rows


def _issue_batch_capability(urls, fixture, purpose, target_ids, *, operation_key=None):
    _, _, issuer_url = urls
    canonical = (
        f"{purpose}|{fixture['org']}|{fixture['inst']}|"
        f"{','.join(sorted(str(target_id) for target_id in target_ids))}"
    )
    digest = sha256(canonical.encode()).hexdigest()
    op_key = operation_key or sha256(f"batch-op:{uuid4()}".encode()).hexdigest()
    fingerprint = sha256(f"batch-fingerprint:{op_key}:{digest}".encode()).hexdigest()
    with psycopg.connect(issuer_url) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT public.sec_tc1_issue_batch_capability(
                   %s,%s,%s,%s,%s,%s,%s)""",
            (purpose, fixture["staff_user"], fixture["org"], fixture["inst"], digest, op_key, fingerprint),
        )
        return cur.fetchone()[0], op_key, digest


def test_m13_guardian_ack_capability_converges_and_is_idempotent(m13_guardian_fixture):
    urls = _require_runtime_urls()
    fixture = m13_guardian_fixture
    with ThreadPoolExecutor(max_workers=2) as pool:
        capabilities = list(pool.map(lambda _i: _issue_m13_capability(urls, fixture), range(2)))
    assert capabilities[0] == capabilities[1]

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipt_ids = list(pool.map(lambda _cap: _consume_m13_capability(urls, _cap), capabilities))
    assert receipt_ids[0] == receipt_ids[1]
    retry_capability = _issue_m13_capability(urls, fixture)
    assert retry_capability == capabilities[0]
    assert _consume_m13_capability(urls, retry_capability) == receipt_ids[0]

    owner_url, _app_url, _issuer_url = urls
    with psycopg.connect(_local_url(OWNER_URL, "education_owner")) as conn, conn.cursor() as cur:
        cur.execute("UPDATE sec_tc1_capabilities SET expires_at=now()-interval '1 second' WHERE actor_user_id=%s AND purpose='M13_NOTICE_ACK' AND result_id=%s", (fixture["user"], receipt_ids[0]))
    expired_retry_capability = _issue_m13_capability(urls, fixture)
    assert expired_retry_capability != retry_capability
    assert _consume_m13_capability(urls, expired_retry_capability) == receipt_ids[0]

    with psycopg.connect(_local_url(OWNER_URL, "education_owner")) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), min(acknowledged_at) FROM family_notice_receipts WHERE id=%s", (receipt_ids[0],))
        row_count, acknowledged_at = cur.fetchone()
        assert row_count == 1 and acknowledged_at is not None
        cur.execute("SELECT count(*) FROM audit_logs WHERE entity_id=%s AND action='FAMILY_NOTICE_ACKNOWLEDGED'", (receipt_ids[0],))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM sec_tc1_capabilities WHERE actor_user_id=%s AND purpose='M13_NOTICE_ACK' AND result_id=%s AND consumed_at IS NOT NULL", (fixture["user"], receipt_ids[0]))
        assert cur.fetchone()[0] == 1


@pytest.mark.parametrize("revocation", ["grant", "profile", "actor"])
def test_m13_ack_capability_fails_after_current_guardian_authorization_revocation(m13_guardian_fixture, revocation):
    urls = _require_runtime_urls()
    fixture = m13_guardian_fixture
    capability = _issue_m13_capability(urls, fixture)
    owner_url, app_url, _issuer_url = urls
    with psycopg.connect(_local_url(OWNER_URL, "education_owner")) as conn, conn.cursor() as cur:
        if revocation == "grant":
            cur.execute("UPDATE guardian_student_portal_access SET status='REVOKED',revoked_at=now() WHERE id=%s", (fixture["grant"],))
        elif revocation == "profile":
            cur.execute("UPDATE guardian_profiles SET status='INACTIVE' WHERE id=%s", (fixture["guardian"],))
        else:
            cur.execute("UPDATE user_accounts SET is_active=false WHERE id=%s", (fixture["user"],))

    with psycopg.connect(_local_url(APP_URL, "education_app")) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.Error) as error:
            cur.execute("SELECT public.m13_acknowledge_family_notice(%s)", (capability,))
        assert error.value.sqlstate == "42501"
        conn.rollback()


def test_m13_committed_retry_rechecks_revoked_guardian_grant(m13_guardian_fixture):
    urls = _require_runtime_urls()
    fixture = m13_guardian_fixture
    capability = _issue_m13_capability(urls, fixture)
    receipt_id = _consume_m13_capability(urls, capability)
    assert _issue_m13_capability(urls, fixture) == capability
    owner_url, app_url, _issuer_url = urls
    with psycopg.connect(owner_url) as conn, conn.cursor() as cur:
        cur.execute("UPDATE guardian_student_portal_access SET status='REVOKED',revoked_at=now() WHERE id=%s", (fixture["grant"],))
    with psycopg.connect(app_url) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.Error) as error:
            cur.execute("SELECT public.m13_acknowledge_family_notice(%s)", (capability,))
        assert error.value.sqlstate == "42501"
        conn.rollback()
    with psycopg.connect(owner_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM family_notice_receipts WHERE id=%s AND acknowledged_at IS NOT NULL", (receipt_id,))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM audit_logs WHERE entity_id=%s AND action='FAMILY_NOTICE_ACKNOWLEDGED'", (receipt_id,))
        assert cur.fetchone()[0] == 1


def test_m21_m27_acknowledgement_bridge_is_authorized_append_only_and_idempotent(m13_guardian_fixture):
    urls = _require_runtime_urls()
    owner_url, _app_url, _issuer_url = urls
    fixture = m13_guardian_fixture
    receipt_id = _consume_m13_capability(urls, _issue_m13_capability(urls, fixture))

    m21_link_cap = _issue_staff_capability(urls, fixture, "M21_ACK_LINK", receipt_id, fixture["followup"])
    m21_link_id = _consume_staff_capability(urls, "M21_ACK_LINK", m21_link_cap)
    assert _issue_staff_capability(urls, fixture, "M21_ACK_LINK", receipt_id, fixture["followup"]) == m21_link_cap
    assert _consume_staff_capability(urls, "M21_ACK_LINK", m21_link_cap) == m21_link_id

    second_link = _consume_staff_capability(
        urls, "M21_ACK_LINK",
        _issue_staff_capability(urls, fixture, "M21_ACK_LINK", receipt_id, fixture["replacement_followup"]),
    )
    void_cap = _issue_staff_capability(
        urls, fixture, "M21_ACK_CORRECT", receipt_id, fixture["followup"],
        related_link=m21_link_id, reason="DUPLICATE_ASSOCIATION",
    )
    void_id = _consume_staff_capability(urls, "M21_ACK_CORRECT", void_cap)
    assert _issue_staff_capability(
        urls, fixture, "M21_ACK_CORRECT", receipt_id, fixture["followup"],
        related_link=m21_link_id, reason="DUPLICATE_ASSOCIATION",
    ) == void_cap
    assert _consume_staff_capability(urls, "M21_ACK_CORRECT", void_cap) == void_id

    supersede_cap = _issue_staff_capability(
        urls, fixture, "M21_ACK_CORRECT", receipt_id, fixture["replacement_followup"],
        related_link=second_link, replacement_target=fixture["followup"], reason="WRONG_CONTEXT",
    )
    supersede_id = _consume_staff_capability(urls, "M21_ACK_CORRECT", supersede_cap)
    assert _consume_staff_capability(urls, "M21_ACK_CORRECT", supersede_cap) == supersede_id

    m21_read = _consume_staff_capability(
        urls, "M21_ACK_READ",
        _issue_staff_capability(urls, fixture, "M21_ACK_READ", receipt_id, fixture["followup"]),
    )
    m21_states = {row[5] for row in m21_read}
    assert "VOIDED" in m21_states and "ACTIVE" in m21_states
    superseded_target_read = _consume_staff_capability(
        urls, "M21_ACK_READ",
        _issue_staff_capability(urls, fixture, "M21_ACK_READ", receipt_id, fixture["replacement_followup"]),
    )
    assert len(superseded_target_read) == 1 and superseded_target_read[0][5] == "SUPERSEDED"

    m27_link_cap = _issue_staff_capability(urls, fixture, "M27_ACK_LINK", receipt_id, fixture["obligation"])
    m27_link_id = _consume_staff_capability(urls, "M27_ACK_LINK", m27_link_cap)
    m27_void_cap = _issue_staff_capability(
        urls, fixture, "M27_ACK_CORRECT", receipt_id, fixture["obligation"],
        related_link=m27_link_id, reason="ACKNOWLEDGEMENT_NOT_RELEVANT",
    )
    _consume_staff_capability(urls, "M27_ACK_CORRECT", m27_void_cap)
    m27_read = _consume_staff_capability(
        urls, "M27_ACK_READ",
        _issue_staff_capability(urls, fixture, "M27_ACK_READ", receipt_id, fixture["obligation"]),
    )
    assert len(m27_read) == 1 and m27_read[0][5] == "VOIDED"

    revoked_m21_read = _issue_staff_capability(urls, fixture, "M21_ACK_READ", receipt_id, fixture["followup"])
    revoked_m27_read = _issue_staff_capability(urls, fixture, "M27_ACK_READ", receipt_id, fixture["obligation"])
    with psycopg.connect(owner_url) as conn, conn.cursor() as cur:
        cur.execute("""DELETE FROM role_permissions rp USING permissions p
                       WHERE rp.permission_id=p.id AND rp.role_id=%s
                         AND p.key IN ('intervention.read','accountability.view')""", (fixture["staff_role"],))
    with psycopg.connect(urls[1]) as conn, conn.cursor() as cur:
        for function_name, token in (
            ("m21_read_acknowledgement_evidence", revoked_m21_read),
            ("m27_read_acknowledgement_evidence", revoked_m27_read),
        ):
            with pytest.raises(psycopg.Error) as error:
                cur.execute(f"SELECT * FROM public.{function_name}(%s)", (token,))
            assert error.value.sqlstate == "42501"
            conn.rollback()

    with psycopg.connect(owner_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM interventions WHERE id=%s", (fixture["intervention"],))
        assert cur.fetchone()[0] == "OPEN"
        cur.execute("SELECT lifecycle FROM accountability_obligations WHERE id=%s", (fixture["obligation"],))
        assert cur.fetchone()[0] == "OPEN"
        cur.execute("SELECT lifecycle FROM accountability_cases WHERE id=%s", (fixture["case"],))
        assert cur.fetchone()[0] == "OPEN"
        cur.execute("SELECT count(*) FROM intervention_followup_acknowledgement_evidence_corrections WHERE organization_id=%s AND institution_id=%s", (fixture["org"], fixture["inst"]))
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM accountability_obligation_acknowledgement_evidence_corrections WHERE organization_id=%s AND institution_id=%s", (fixture["org"], fixture["inst"]))
        assert cur.fetchone()[0] == 1


def test_m21_concurrent_same_receipt_followup_link_converges_to_one_link(m13_guardian_fixture):
    urls = _require_runtime_urls()
    fixture = m13_guardian_fixture
    receipt_id = _consume_m13_capability(urls, _issue_m13_capability(urls, fixture))
    barrier = Barrier(2)

    def issue_and_consume(_index):
        capability = _issue_staff_capability(urls, fixture, "M21_ACK_LINK", receipt_id, fixture["followup"])
        barrier.wait(timeout=10)
        return _consume_staff_capability(urls, "M21_ACK_LINK", capability)

    with ThreadPoolExecutor(max_workers=2) as pool:
        link_ids = list(pool.map(issue_and_consume, range(2)))
    assert link_ids[0] == link_ids[1]

    with psycopg.connect(urls[0]) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM intervention_followup_acknowledgement_evidence_links WHERE receipt_id=%s AND followup_id=%s", (receipt_id, fixture["followup"]))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM audit_logs WHERE actor_user_id=%s AND entity_id=%s AND action='student.intervention.followup.acknowledgement_evidence.linked'", (fixture["staff_user"], link_ids[0]))
        assert cur.fetchone()[0] == 1


def test_m21_rollback_retry_and_committed_lost_response_are_idempotent(m13_guardian_fixture):
    urls = _require_runtime_urls()
    fixture = m13_guardian_fixture
    receipt_id = _consume_m13_capability(urls, _issue_m13_capability(urls, fixture))
    capability = _issue_staff_capability(urls, fixture, "M21_ACK_LINK", receipt_id, fixture["followup"])
    with psycopg.connect(urls[1]) as conn, conn.cursor() as cur:
        cur.execute("SELECT public.m21_link_acknowledgement_evidence(%s)", (capability,))
        rolled_back_link_id = cur.fetchone()[0]
        conn.rollback()

    committed_link_id = _consume_staff_capability(urls, "M21_ACK_LINK", capability)
    assert committed_link_id != rolled_back_link_id
    # Simulate a lost HTTP response: replay the same committed capability and
    # require its saved result without a second semantic mutation or audit.
    assert _consume_staff_capability(urls, "M21_ACK_LINK", capability) == committed_link_id
    with psycopg.connect(urls[0]) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM intervention_followup_acknowledgement_evidence_links WHERE receipt_id=%s AND followup_id=%s", (receipt_id, fixture["followup"]))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM audit_logs WHERE actor_user_id=%s AND entity_id=%s AND action='student.intervention.followup.acknowledgement_evidence.linked'", (fixture["staff_user"], committed_link_id))
        assert cur.fetchone()[0] == 1


def test_m21_duplicate_correction_and_competing_supersessions_are_serialized(m13_guardian_fixture):
    urls = _require_runtime_urls()
    fixture = m13_guardian_fixture
    receipt_id = _consume_m13_capability(urls, _issue_m13_capability(urls, fixture))
    original_link_id = _consume_staff_capability(
        urls, "M21_ACK_LINK",
        _issue_staff_capability(urls, fixture, "M21_ACK_LINK", receipt_id, fixture["replacement_followup"]),
    )
    duplicate_barrier = Barrier(2)

    def issue_and_duplicate(_index):
        capability = _issue_staff_capability(
            urls, fixture, "M21_ACK_CORRECT", receipt_id, fixture["replacement_followup"],
            related_link=original_link_id, reason="DUPLICATE_ASSOCIATION",
        )
        duplicate_barrier.wait(timeout=10)
        return _consume_staff_capability(urls, "M21_ACK_CORRECT", capability)

    with ThreadPoolExecutor(max_workers=2) as pool:
        correction_ids = list(pool.map(issue_and_duplicate, range(2)))
    assert correction_ids[0] == correction_ids[1]
    with psycopg.connect(urls[0]) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM intervention_followup_acknowledgement_evidence_corrections WHERE original_link_id=%s", (original_link_id,))
        assert cur.fetchone()[0] == 1

    race_original = _consume_staff_capability(
        urls, "M21_ACK_LINK",
        _issue_staff_capability(urls, fixture, "M21_ACK_LINK", receipt_id, fixture["followup"]),
    )
    race_barrier = Barrier(2)
    replacements = (fixture["replacement_followup"], fixture["race_followup"])

    def supersede(replacement):
        capability = _issue_staff_capability(
            urls, fixture, "M21_ACK_CORRECT", receipt_id, fixture["followup"],
            related_link=race_original, replacement_target=replacement, reason="WRONG_CONTEXT",
        )
        race_barrier.wait(timeout=10)
        try:
            result = _consume_staff_capability(urls, "M21_ACK_CORRECT", capability)
            return ("ok", replacement, result)
        except psycopg.Error as error:
            return ("error", replacement, error.sqlstate)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(supersede, replacements))
    successes = [outcome for outcome in outcomes if outcome[0] == "ok"]
    failures = [outcome for outcome in outcomes if outcome[0] == "error"]
    assert len(successes) == 1 and len(failures) == 1
    assert failures[0][2] == "23505"
    with psycopg.connect(urls[0]) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM intervention_followup_acknowledgement_evidence_corrections WHERE original_link_id=%s", (race_original,))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT replacement_link_id FROM intervention_followup_acknowledgement_evidence_corrections WHERE original_link_id=%s", (race_original,))
        replacement_link_id = cur.fetchone()[0]
        assert replacement_link_id is not None
        cur.execute("SELECT followup_id FROM intervention_followup_acknowledgement_evidence_links WHERE id=%s", (replacement_link_id,))
        assert cur.fetchone()[0] == successes[0][1]


def test_application_services_issue_and_consume_order_independent_m21_m27_batches(
    m13_guardian_fixture, monkeypatch
):
    urls = _require_runtime_urls()
    fixture = m13_guardian_fixture
    owner_url, app_url, issuer_url = urls
    receipt_id = _consume_m13_capability(urls, _issue_m13_capability(urls, fixture))

    for operation, target_id in (
        ("M21_ACK_LINK", fixture["followup"]),
        ("M21_ACK_LINK", fixture["replacement_followup"]),
        ("M27_ACK_LINK", fixture["obligation"]),
    ):
        _consume_staff_capability(
            urls,
            operation,
            _issue_staff_capability(urls, fixture, operation, receipt_id, target_id),
        )

    issuer_engine = create_engine(
        make_url(issuer_url).set(drivername="postgresql+psycopg").render_as_string(
            hide_password=False
        )
    )
    app_engine = create_engine(
        make_url(app_url).set(drivername="postgresql+psycopg").render_as_string(
            hide_password=False
        )
    )
    monkeypatch.setattr(
        trusted_context,
        "get_trusted_context_issuer_engine",
        lambda: issuer_engine,
    )
    principal = CurrentPrincipal(
        user_id=fixture["staff_user"],
        organization_id=fixture["org"],
        institution_id=fixture["inst"],
    )
    hidden_followup = uuid4()
    hidden_obligation = uuid4()
    followup_targets = [
        fixture["replacement_followup"],
        hidden_followup,
        fixture["followup"],
    ]
    obligation_targets = [fixture["obligation"], hidden_obligation]

    try:
        with Session(app_engine) as session:
            m21_rows = read_followup_acknowledgement_batch(
                session,
                principal,
                followup_ids=followup_targets,
                idempotency_key=uuid4(),
            )
        with Session(app_engine) as session:
            m27_rows = read_obligation_acknowledgement_batch(
                session,
                principal,
                obligation_ids=obligation_targets,
                idempotency_key=uuid4(),
            )

        assert [row["target_id"] for row in m21_rows] == sorted(
            [fixture["followup"], fixture["replacement_followup"]]
        )
        assert all(row["acknowledgement_evidence_present"] for row in m21_rows)
        assert [row["target_id"] for row in m27_rows] == [fixture["obligation"]]
        assert m27_rows[0]["acknowledgement_evidence_present"] is True

        # The service canonicalizes set identity independent of caller order;
        # two separate operations therefore persist equal target-set digests.
        followup_pair = [fixture["followup"], fixture["replacement_followup"]]
        for ordered_targets in (followup_pair, list(reversed(followup_pair))):
            with Session(app_engine) as session:
                rows = read_followup_acknowledgement_batch(
                    session,
                    principal,
                    followup_ids=ordered_targets,
                    idempotency_key=uuid4(),
                )
            assert [row["target_id"] for row in rows] == sorted(followup_pair)

        with psycopg.connect(owner_url) as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT target_set_digest FROM sec_tc1_capabilities
                   WHERE actor_user_id=%s AND purpose='M21_ACK_BATCH_READ'
                   ORDER BY issued_at DESC LIMIT 2""",
                (fixture["staff_user"],),
            )
            ordered_digests = [row[0] for row in cur.fetchall()]
            assert len(ordered_digests) == 2 and ordered_digests[0] == ordered_digests[1]
    finally:
        app_engine.dispose()
        issuer_engine.dispose()


def test_batch_capability_rejects_target_set_conflict_and_expiry(m13_guardian_fixture):
    urls = _require_runtime_urls()
    fixture = m13_guardian_fixture
    app_url, owner_url = urls[1], urls[0]
    targets = [fixture["followup"]]

    conflict_capability, _, _ = _issue_batch_capability(
        urls, fixture, "M21_ACK_BATCH_READ", targets
    )
    with psycopg.connect(app_url) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.Error) as error:
            cur.execute(
                "SELECT * FROM public.m21_read_acknowledgement_evidence_batch(%s,%s)",
                (conflict_capability, [fixture["followup"], uuid4()]),
            )
        assert error.value.sqlstate == "42501"
        conn.rollback()

    expired_capability, _, _ = _issue_batch_capability(
        urls, fixture, "M27_ACK_BATCH_READ", [fixture["obligation"]]
    )
    with psycopg.connect(owner_url) as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE sec_tc1_capabilities SET expires_at=now()-interval '1 second'
               WHERE capability_value=%s""",
            (expired_capability,),
        )
        assert cur.rowcount == 1
    with psycopg.connect(app_url) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.Error) as error:
            cur.execute(
                "SELECT * FROM public.m27_read_acknowledgement_evidence_batch(%s,%s)",
                (expired_capability, [fixture["obligation"]]),
            )
        assert error.value.sqlstate == "42501"
        conn.rollback()


@pytest.mark.parametrize("purpose", ["M21_ACK_LINK", "M27_ACK_LINK"])
def test_pre_0047_acknowledged_at_without_m13_provenance_cannot_be_linked(m13_guardian_fixture, purpose):
    urls = _require_runtime_urls()
    fixture = m13_guardian_fixture
    operation_key = sha256(f"legacy-link:{purpose}:{uuid4()}".encode()).hexdigest()
    fingerprint = sha256(f"{purpose}:{fixture['legacy_receipt']}".encode()).hexdigest()
    _owner_url, _app_url, issuer_url = urls
    with psycopg.connect(issuer_url) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.Error) as error:
            cur.execute("""SELECT public.sec_tc1_issue_capability(
                %s,%s,%s,%s,%s,%s,NULL,NULL,NULL,NULL,%s,%s)""",
                (purpose, fixture["user"], fixture["org"], fixture["inst"], fixture["legacy_receipt"], uuid4(), operation_key, fingerprint))
        assert error.value.sqlstate == "42501"
        conn.rollback()


def test_sec_tc1_roles_are_restricted_and_do_not_form_membership_paths():
    with psycopg.connect(_local_url(OWNER_URL, "education_owner")) as conn, conn.cursor() as cur:
        _require_revision(cur)
        cur.execute(
            """SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                      rolinherit, rolbypassrls FROM pg_roles
               WHERE rolname IN ('education_context_issuer','education_context_function_owner')
               ORDER BY rolname"""
        )
        attrs = cur.fetchall()
        assert attrs == [
            ("education_context_function_owner", False, False, False, False, False, False),
            ("education_context_issuer", True, False, False, False, False, False),
        ]
        cur.execute(
            """SELECT count(*) FROM pg_auth_members am
               JOIN pg_roles granted ON granted.oid=am.roleid
               JOIN pg_roles member ON member.oid=am.member
               WHERE granted.rolname IN ('education_context_issuer','education_context_function_owner')
                  OR member.rolname IN ('education_context_issuer','education_context_function_owner')"""
        )
        assert cur.fetchone()[0] == 0


def test_education_app_has_no_direct_access_to_sec_tc1_or_m29_tables():
    with psycopg.connect(_local_url(OWNER_URL, "education_owner")) as conn, conn.cursor() as cur:
        _require_revision(cur)
        for table in TABLES:
            cur.execute(
                """SELECT has_table_privilege('education_app', %s, 'SELECT'),
                          has_table_privilege('education_app', %s, 'INSERT'),
                          has_table_privilege('education_app', %s, 'UPDATE'),
                          has_table_privilege('education_app', %s, 'DELETE')""",
                (f"public.{table}",) * 4,
            )
            assert cur.fetchone() == (False, False, False, False), table


def test_education_app_can_only_mutate_read_receipt_columns():
    with psycopg.connect(_local_url(OWNER_URL, "education_owner")) as conn, conn.cursor() as cur:
        _require_revision(cur)
        cur.execute(
            """SELECT has_table_privilege('education_app','public.family_notice_receipts','INSERT'),
                      has_table_privilege('education_app','public.family_notice_receipts','UPDATE'),
                      has_table_privilege('education_app','public.family_notice_receipts','DELETE'),
                      has_column_privilege('education_app','public.family_notice_receipts','read_at','UPDATE'),
                      has_column_privilege('education_app','public.family_notice_receipts','acknowledged_at','UPDATE'),
                      has_column_privilege('education_app','public.family_notice_receipts','acknowledged_at','INSERT')"""
        )
        assert cur.fetchone() == (False, False, False, True, False, False)
        cur.execute("SELECT has_column_privilege('education_app','public.family_notice_receipts','read_at','INSERT')")
        assert cur.fetchone()[0] is True


@pytest.mark.parametrize("privilege,statement", [
    ("SELECT", "SELECT * FROM public.sec_tc1_capabilities"),
    ("INSERT", "INSERT INTO public.sec_tc1_capabilities DEFAULT VALUES"),
    ("UPDATE", "UPDATE public.sec_tc1_capabilities SET consumed_at=now()"),
    ("DELETE", "DELETE FROM public.sec_tc1_capabilities"),
])
def test_education_app_direct_capability_table_access_is_denied(privilege, statement):
    try:
        with psycopg.connect(_local_url(APP_URL, "education_app")) as conn, conn.cursor() as cur:
            _require_revision(cur)
            cur.execute(statement)
    except psycopg.Error as exc:
        assert exc.sqlstate == "42501"
    else:
            pytest.fail(f"education_app unexpectedly had direct {privilege} access")


def test_education_app_cannot_set_family_notice_acknowledged_at_directly():
    try:
        with psycopg.connect(_local_url(APP_URL, "education_app")) as conn, conn.cursor() as cur:
            _require_revision(cur)
            cur.execute(
                "UPDATE public.family_notice_receipts SET acknowledged_at=now() WHERE id=%s",
                ("00000000-0000-0000-0000-000000000000",),
            )
    except psycopg.Error as exc:
        assert exc.sqlstate == "42501"
    else:
        pytest.fail("education_app unexpectedly could write acknowledgement timestamps")


def test_education_app_cannot_assume_issuer_or_function_owner():
    with psycopg.connect(_local_url(APP_URL, "education_app")) as conn, conn.cursor() as cur:
        _require_revision(cur)
        for role in ("education_context_issuer", "education_context_function_owner"):
            with pytest.raises(psycopg.Error) as error:
                cur.execute(f"SET ROLE {role}")
            assert error.value.sqlstate == "42501"
            conn.rollback()


def test_runtime_cannot_execute_capability_issuer_function():
    with psycopg.connect(_local_url(APP_URL, "education_app")) as conn, conn.cursor() as cur:
        _require_revision(cur)
        with pytest.raises(psycopg.Error) as error:
            cur.execute(
                """SELECT public.sec_tc1_issue_capability(
                  'M21_ACK_LINK',gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),
                  gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),NULL,NULL,NULL,%s,%s)""",
                ("0" * 64, "0" * 64),
            )
        assert error.value.sqlstate == "42501"


def test_app_cannot_execute_internal_capability_validator():
    with psycopg.connect(_local_url(OWNER_URL, "education_owner")) as conn, conn.cursor() as cur:
        _require_revision(cur)
        cur.execute("SELECT has_function_privilege('education_app','public.sec_tc1_validate_capability(text,text)','EXECUTE')")
        assert cur.fetchone()[0] is False
        cur.execute("SELECT has_function_privilege('education_app','public.m13_acknowledge_family_notice(text)','EXECUTE')")
        assert cur.fetchone()[0] is True
