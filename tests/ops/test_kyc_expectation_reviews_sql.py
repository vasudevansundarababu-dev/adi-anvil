"""Private review custody under real roles in a marked disposable SQL target."""
import os
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from anvil import kyc_expectation_reviews as reviews
from anvil.db import digest
from anvil.golden_kyc_runtime import seed
from anvil.kyc_policy_expectation_loader import enter
from anvil.praxis_generic_contract import canonical

pytestmark = pytest.mark.skipif(not os.environ.get("ANVIL_CONTEXT_TEST_DSN"), reason="Explicit marked isolated SQL target required")


@pytest.fixture
def scope():
    dsn = os.environ["ANVIL_CONTEXT_TEST_DSN"]
    org, project, user = uuid4(), uuid4(), uuid4()
    loader, grader = "expect_loader_" + secrets.token_hex(5), "expect_grader_" + secrets.token_hex(5)
    passwords = {loader: secrets.token_urlsafe(32), grader: secrets.token_urlsafe(32)}
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        assert c.execute("SELECT label FROM public.context_registrar_test_marker").fetchone() == {"label": "synthetic-context-registrar-only"}
        assert c.execute("SELECT max(version) AS v FROM anvil.schema_versions").fetchone()["v"] in {134, 135}
        c.execute("INSERT INTO anvil.organizations VALUES(%s,'Synthetic expectation review SQL')", (org,))
        c.execute("INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,'Synthetic review SQL')", (project, org))
        c.execute("INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,'synthetic-test',%s,'Synthetic PO')", (user, org, str(user)))
        c.execute("INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,'admin')", (project, user))
        pack = UUID(seed(c, str(project), str(user), include_expectations=False)["pack_id"])
        apps = c.execute("SELECT id,snapshot,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id", (project, pack)).fetchall()
        for name, role in ((loader, "anvil_kyc_expectation_loader"), (grader, "anvil_golden_grader")):
            c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION").format(sql.Identifier(name), sql.Literal(passwords[name])))
            c.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(role), sql.Identifier(name)))
        c.execute("INSERT INTO anvil.kyc_policy_operator_principals(login_role,project_id,user_id) VALUES(%s,%s,%s)", (loader, project, user))
    packet = reviews.Packet(schema_version="anvil.kyc-private-expectation-packet.v1", project_id=project,
        pack_id=pack, cases=[reviews.PrivateCase(application_id=a["id"], snapshot_sha256=a["snapshot_sha256"],
            salt=secrets.token_hex(32), expectation=reviews.Expected(intended_decision="request_information",
                notes="Manufactured SQL-only review fixture, never QA approval")) for a in apps])
    @contextmanager
    def connection(role):
        params = {"user": loader if role == "loader" else grader,
                  "password": passwords[loader if role == "loader" else grader]} if role != "app" else {}
        with psycopg.connect(make_conninfo(dsn, **params), row_factory=dict_row) as c:
            if role == "loader":
                assert enter(c, project) == user
            else:
                c.execute("SET LOCAL ROLE " + ("anvil_app" if role == "app" else "anvil_golden_grader"))
                c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (str(project), str(user)))
            yield c
    return dsn, project, user, packet, apps, connection


def decision(subject, packet):
    return reviews.Decision(subject_sha256=subject["sha256"], private_packet_sha256=reviews.subject_for(packet).private_packet_sha256,
        decision="approved", rationale="Explicit manufactured SQL fixture review only",
        evidence_reference="synthetic-review-packet-only", expires_at=datetime.now(timezone.utc) + timedelta(hours=1))


def test_grader_policy_context_is_explicit_without_interactive_user(scope):
    _, _, _, _, _, connection = scope
    with connection("grader") as c:
        c.execute("SELECT set_config('anvil.user','',true)")
        assert c.execute("SELECT banking.product_policy_grader_binding(%s,0) AS value", (uuid4(),)).fetchone()["value"] is None
        with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
            c.execute("SELECT banking.product_policy_trial_binding(%s,0)", (uuid4(),))
    with connection("app") as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
            c.execute("SELECT banking.product_policy_grader_binding(%s,0)", (uuid4(),))


def test_actual_loader_owner_grader_review_and_revocation(scope):
    _, project, user, packet, apps, connection = scope
    with connection("loader") as c:
        staged = reviews.stage_private(c, project, user, packet)
        assert staged["review"] == "pending"
    with connection("loader") as c:
        assert reviews.stage_private(c, project, user, packet)["id"] == staged["id"]
    with connection("app") as c:
        assert not reviews.current(c, project, packet.pack_id)["ready"]
        for table in ("expectation_versions", "expectation_packets"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
                c.execute("SELECT * FROM banking_private." + table)
        approved = reviews.decide(c, project, user, staged["id"], decision(staged, packet))
        assert approved["self_approved"] is True
    with connection("app") as c:
        current = reviews.current(c, project, packet.pack_id)
        assert current["ready"] and current["case_count"] == 200
        assert "intended_decision" not in str(current)
    frozen = reviews.public_reference(current)
    with connection("grader") as c:
        result = reviews.reviewed(c, project, packet.pack_id, apps[0]["id"], apps[0]["snapshot"], frozen_reference=frozen)
        assert result["independent_expectation_review"] == "approved"
        assert result["intended_decision"] == "request_information" and result["legal_qualification"] == "pending"
        changed = frozen | {"receipt_sha256": "a" * 64}
        assert reviews.reviewed(c, project, packet.pack_id, apps[0]["id"], apps[0]["snapshot"], frozen_reference=changed)["review_issue"] == "AV_KYC_FROZEN_EXPECTATION_REVIEW_CHANGED"
        with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
            c.execute("UPDATE banking_private.expectation_versions SET body_canonical='{}'")
        c.execute("SELECT set_config('anvil.project',%s,true)", (str(uuid4()),))
        assert not c.execute("SELECT subject_id FROM banking_private.expectation_versions").fetchall()
    with connection("app") as c:
        reviews.revoke(c, project, user, approved["id"], "Synthetic explicit revocation control")
    with connection("grader") as c:
        result = reviews.reviewed(c, project, packet.pack_id, apps[0]["id"], apps[0]["snapshot"], frozen_reference=frozen)
        assert result["independent_expectation_review"] == "pending"


def test_database_refuses_unbacked_public_metadata_and_private_api_writes(scope):
    dsn, project, user, packet, _, connection = scope
    subject = reviews.subject_for(packet).model_dump(mode="json")
    identifier = uuid4()
    with pytest.raises(psycopg.errors.RaiseException, match="complete exact private"), connection("loader") as c:
        c.execute("INSERT INTO anvil.kyc_expectation_subjects(id,project_id,pack_id,created_by,body_canonical,content_sha256) VALUES(%s,%s,%s,%s,%s,%s)",
                  (identifier, project, packet.pack_id, user, canonical(subject).decode(), digest(subject)))
    with psycopg.connect(dsn) as c:
        assert not c.execute("SELECT id FROM anvil.kyc_expectation_subjects WHERE id=%s", (identifier,)).fetchall()
    with connection("app") as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
            c.execute("INSERT INTO anvil.kyc_expectation_subjects(id,project_id,pack_id,created_by,body_canonical,content_sha256) VALUES(%s,%s,%s,%s,%s,%s)",
                      (identifier, project, packet.pack_id, user, canonical(subject).decode(), digest(subject)))
    with connection("loader") as c:
        c.execute("SELECT set_config('anvil.project',%s,true)", (str(uuid4()),))
        with pytest.raises(ValueError, match="Enrolled restricted"):
            reviews.stage_private(c, project, user, packet)


def test_new_review_population_never_replaces_frozen_expected_answers(scope):
    _, project, user, packet, apps, connection = scope
    with connection("loader") as c:
        original = reviews.stage_private(c, project, user, packet)
    with connection("app") as c:
        reviews.decide(c, project, user, original["id"], decision(original, packet))
        old_ref = reviews.public_reference(reviews.current(c, project, packet.pack_id))
    replacement = packet.model_copy(update={"cases": [case.model_copy(update={
        "salt": secrets.token_hex(32), "expectation": reviews.Expected(intended_decision="specialist_review")}) for case in packet.cases]})
    with connection("loader") as c:
        fresh = reviews.stage_private(c, project, user, replacement)
    with connection("app") as c:
        assert not reviews.current(c, project, packet.pack_id)["ready"]
        reviews.decide(c, project, user, fresh["id"], decision(fresh, replacement))
    with connection("grader") as c:
        value = reviews.reviewed(c, project, packet.pack_id, apps[0]["id"], apps[0]["snapshot"], frozen_reference=old_ref)
        assert value["independent_expectation_review"] == "pending" and "intended_decision" not in value
