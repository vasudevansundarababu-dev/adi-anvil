"""Real LOGIN controls on an explicitly marked, isolated schema136 database.

Manufactured receipts below test the SQL publication boundary only. They are
never evidence that a real task, method, owner decision or model is qualified.
"""

import json
import os
import secrets
import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from anvil.db import Jsonb, digest
from anvil.praxis_generic_contract import canonical

pytestmark = pytest.mark.skipif(not os.environ.get("ANVIL_METHOD_TEST_DSN"),
                                reason="Explicit marked method-operator test database required")


@pytest.fixture(scope="module")
def method_operator():
    dsn = os.environ["ANVIL_METHOD_TEST_DSN"]
    ids = {key: uuid4() for key in ("org", "project", "user", "group", "foreign", "foreign_user", "foreign_group")}
    logins = ["méthod_sql_" + secrets.token_hex(5) for _ in range(2)]
    passwords = {login: secrets.token_urlsafe(32) for login in logins}
    content = {"tasks": [{"task_id": "manufactured-task", "task_version": "1",
                         "payload_sha256": "a" * 64,
                         "actor": {"private_reference": "nested private sentinel",
                                   "source": {"answer": "nested source sentinel"},
                                   "sections": {"S8": {"answer": "private section sentinel"},
                                    "S5": {"steps": [{"action": "Synthetic control",
                                                       "tool": {"private_reference": "nested tool sentinel"},
                                                       "private_reference": "step private sentinel"}]}}},
                         "source": {"private_reference": "must not be projected"},
                         "private_reference": "must not be projected"}]}
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        assert c.execute("SELECT label FROM public.context_registrar_test_marker").fetchone() == {
            "label": "synthetic-context-registrar-only"}
        assert c.execute("SELECT max(version) AS v FROM anvil.schema_versions").fetchone()["v"] == 136
        c.execute("INSERT INTO anvil.organizations VALUES(%s,'Synthetic method SQL')", (ids["org"],))
        for p, u, g in ((ids["project"], ids["user"], ids["group"]),
                        (ids["foreign"], ids["foreign_user"], ids["foreign_group"])):
            c.execute("INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,'Synthetic method SQL')", (p, ids["org"]))
            c.execute("INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,'synthetic-test',%s,'Synthetic PO')", (u, ids["org"], str(u)))
            c.execute("INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,'admin')", (p, u))
            c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (str(p), str(u)))
            c.execute("INSERT INTO anvil.benchmark_task_groups(id,project_id,source_project_id,source_version,name,content,content_sha256,created_by) VALUES(%s,%s,%s,'synthetic','Synthetic method only',%s,%s,%s)",
                      (g, p, str(g), Jsonb(content), digest(content), u))
        for login in logins:
            c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION").format(sql.Identifier(login), sql.Literal(passwords[login])))
            c.execute(sql.SQL("GRANT anvil_kyc_qualifier TO {}").format(sql.Identifier(login)))
        c.execute("INSERT INTO anvil.kyc_policy_operator_principals(login_role,project_id,user_id) VALUES(%s,%s,%s)", (logins[0], ids["project"], ids["user"]))

    @contextmanager
    def connect(*, enrolled=True, foreign=False):
        login = logins[0 if enrolled else 1]
        with psycopg.connect(make_conninfo(dsn, user=login, password=passwords[login]), row_factory=dict_row) as c:
            c.execute("SET LOCAL ROLE anvil_kyc_qualifier")
            c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                      (str(ids["foreign" if foreign else "project"]), str(ids["foreign_user" if foreign else "user"])))
            yield c

    def evidence(**changes):
        now = datetime.now(timezone.utc)
        body = {"schema_version": "anvil.task-capability-control.v1", "origin": "independent_qa",
                "project_id": str(ids["project"]), "task_group_id": str(ids["group"]),
                "source_sha256": digest(content), "target": "method:task-rubric-v1",
                "candidate_id": "task-rubric-v1", "publisher_login": logins[0],
                "spending_authority": False, "human_review_approval": False, "model_performance": False,
                "issued_at": now.isoformat(), "expires_at": (now + timedelta(hours=1)).isoformat(),
                "controls": {name: {"status": "passed", "evidence_sha256": "0" * 64}
                             for name in ("positive", "negative", "missing", "project_isolation")},
                "evidence_scope": "technical_method_controls_only"}
        for key in ("candidate_sha256", "runtime_source_sha256", "broker_source_sha256", "runtime_image_sha256",
                    "release_sha256", "observation_sha256", "review_sha256"):
            body[key] = "1" * 64
        return body | changes

    return dsn, ids, logins, connect, evidence


def publish(c, ids, body):
    encoded = canonical(body).decode()
    return c.execute("SELECT anvil.publish_task_method(%s,%s,%s,%s,%s,%s) AS id",
                     (ids["project"], ids["group"], uuid4(), encoded, digest(body), body["expires_at"])).fetchone()["id"]


def test_actual_public_projection_excludes_private_source_and_known_foreign_group(method_operator):
    _, ids, _, connect, _ = method_operator
    with connect() as c:
        body = c.execute("SELECT anvil.task_method_public_group(%s,%s) AS body", (ids["project"], ids["group"])).fetchone()["body"]
        assert len(body["tasks"]) == 1 and body["tasks"][0]["workflow_steps"][0]["action"] == "Synthetic control"
        assert "private_reference" not in json.dumps(body) and "must not be projected" not in json.dumps(body)
        assert "sentinel" not in json.dumps(body) and "S8" not in json.dumps(body)
        assert body["tasks"][0]["workflow_steps"][0]["tool"] is None
        assert c.execute("SELECT anvil.task_method_public_group(%s,%s) AS body", (ids["project"], ids["foreign_group"])).fetchone()["body"] is None
        with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
            c.execute("SELECT content FROM anvil.benchmark_task_groups")


def test_owner_witness_reads_only_actual_metadata_and_requires_read_only_transaction(method_operator):
    from infra.gcp.task_method_owner_observation import observe

    dsn, ids, _, _, _ = method_operator
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        c.execute("SET TRANSACTION READ ONLY")
        body = observe(c, ids["project"], ids["group"], ids["foreign"], ids["foreign_group"])
        assert body["known_foreign_group_exists"] is True
        assert body["private_content_read"] is False and body["qualification_granted"] is False
        assert "Synthetic control" not in json.dumps(body) and "sentinel" not in json.dumps(body)
        with pytest.raises(ValueError, match="must exist"):
            observe(c, ids["project"], ids["group"], ids["foreign"], uuid4())
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        with pytest.raises(ValueError, match="read-only"):
            observe(c, ids["project"], ids["group"], ids["foreign"], ids["foreign_group"])


def test_binding_fence_blocks_project_mutation_without_granting_update(method_operator):
    dsn, ids, _, connect, _ = method_operator
    with connect() as c:
        assert c.execute("SELECT anvil.task_method_binding_fence(%s) AS locked", (ids["project"],)).fetchone()["locked"]
        with psycopg.connect(dsn) as owner:
            owner.execute("SET LOCAL lock_timeout='200ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable), owner.transaction():
                owner.execute("UPDATE anvil.projects SET name=name WHERE id=%s", (ids["project"],))
        with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
            c.execute("SELECT anvil.task_method_binding_fence(%s)", (ids["foreign"],))


def test_enrolled_method_publication_is_scoped_and_attributed(method_operator):
    _, ids, logins, connect, evidence = method_operator
    with connect() as c:
        identifier = publish(c, ids, evidence())
        row = c.execute("SELECT * FROM anvil.task_method_publications WHERE qualification_id=%s", (identifier,)).fetchone()
        assert row["login_role"] == logins[0] and row["sponsoring_admin"] == ids["user"]
        assert row["project_id"] == ids["project"]


def test_unicode_canonical_evidence_matches_the_consuming_digest(method_operator):
    dsn, ids, _, connect, evidence = method_operator
    body = evidence()
    assert "é" in canonical(body).decode()
    with connect() as c:
        identifier = publish(c, ids, body)
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        row = c.execute("SELECT evidence,evidence_sha256 FROM anvil.task_capability_qualifications WHERE id=%s", (identifier,)).fetchone()
        assert row["evidence_sha256"] == digest(row["evidence"]) == digest(body)
    escaped = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert escaped != canonical(body).decode()
    with connect() as c, pytest.raises(psycopg.Error), c.transaction():
        c.execute("SELECT anvil.publish_task_method(%s,%s,%s,%s,%s,%s)",
                  (ids["project"], ids["group"], uuid4(), escaped,
                   hashlib.sha256(escaped.encode()).hexdigest(), body["expires_at"]))


def test_forged_gucs_and_unenrolled_login_cannot_observe_or_publish(method_operator):
    _, ids, _, connect, evidence = method_operator
    for options in ({"enrolled": False}, {"foreign": True}):
        with connect(**options) as c:
            for query, values in (("SELECT anvil.task_method_public_group(%s,%s)", (ids["project"], ids["group"])),):
                with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
                    c.execute(query, values)
            with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
                publish(c, ids, evidence())
            assert c.execute("SELECT count(*) AS n FROM anvil.task_method_publications").fetchone()["n"] == 0


@pytest.mark.parametrize("change", [
    {"source_sha256": "0" * 64}, {"candidate_id": "safety-observed-v1"},
    {"target": "skill:manufactured"}, {"publisher_login": "anvil_app"},
    {"spending_authority": True}, {"human_review_approval": True}, {"model_performance": True},
    {"runtime_image_sha256": "missing"}, {"controls": {}},
    {"expires_at": "2000-01-01T00:00:00+00:00"},
])
def test_invalid_or_broadened_receipts_are_rejected(method_operator, change):
    _, ids, _, connect, evidence = method_operator
    with connect() as c, pytest.raises(psycopg.Error), c.transaction():
        publish(c, ids, evidence(**change))


def test_no_raw_publication_writes_or_private_grading_reads(method_operator):
    _, _, _, connect, _ = method_operator
    with connect() as c:
        for table in ("anvil.task_capability_qualifications", "anvil.task_method_publications"):
            for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                assert not c.execute("SELECT has_table_privilege(current_user,%s,%s) AS allowed", (table, privilege)).fetchone()["allowed"]
        for table in ("banking_private.expectations", "banking_private.expectation_versions", "banking_private.results"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
                c.execute("SELECT 1 FROM " + table + " LIMIT 1")


def test_normal_runtime_roles_cannot_call_method_publisher(method_operator):
    dsn, _, _, _, _ = method_operator
    with psycopg.connect(dsn) as c:
        for role in ("anvil_app", "anvil_worker", "anvil_golden_scheduler", "anvil_golden_grader"):
            assert not c.execute("SELECT has_function_privilege(%s,'anvil.publish_task_method(uuid,uuid,uuid,text,text,timestamptz)','EXECUTE')", (role,)).fetchone()[0]
            assert not c.execute("SELECT has_function_privilege(%s,'anvil.task_method_public_group(uuid,uuid)','EXECUTE')", (role,)).fetchone()[0]
            assert not c.execute("SELECT has_function_privilege(%s,'anvil.revoke_task_method(uuid,uuid,uuid,text)','EXECUTE')", (role,)).fetchone()[0]


def test_revoked_sponsor_is_not_an_operator_authority(method_operator):
    dsn, ids, _, connect, evidence = method_operator
    with psycopg.connect(dsn) as c:
        c.execute("UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s", (ids["project"], ids["user"]))
    try:
        with connect() as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
                publish(c, ids, evidence())
    finally:
        with psycopg.connect(dsn) as c:
            c.execute("UPDATE anvil.memberships SET active=true WHERE project_id=%s AND user_id=%s", (ids["project"], ids["user"]))


def test_publication_holds_actual_sponsor_and_enrollment_fences(method_operator):
    dsn, ids, logins, connect, evidence = method_operator
    with connect() as c:
        publish(c, ids, evidence())
        with psycopg.connect(dsn) as owner:
            owner.execute("SET LOCAL lock_timeout='200ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable), owner.transaction():
                owner.execute("UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s", (ids["project"], ids["user"]))
            with pytest.raises(psycopg.errors.LockNotAvailable), owner.transaction():
                owner.execute("DELETE FROM anvil.kyc_policy_operator_principals WHERE login_role=%s AND project_id=%s", (logins[0], ids["project"]))


def test_revoke_serializes_with_publication_and_reader_row_locks(method_operator):
    dsn, ids, logins, connect, evidence = method_operator
    with connect() as writer:
        identifier = publish(writer, ids, evidence())
        with connect() as revoker:
            revoker.execute("SET LOCAL lock_timeout='200ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable), revoker.transaction():
                revoker.execute("SELECT anvil.revoke_task_method(%s,%s,%s,%s)",
                                (ids["project"], identifier, uuid4(), "Synthetic publication race control"))
    # Production admission takes a qualification row lock. Exercise that actual
    # PostgreSQL boundary here without claiming this is a full SDK dispatch test.
    with psycopg.connect(dsn) as reader:
        assert reader.execute("SELECT id FROM anvil.task_capability_qualifications WHERE id=%s FOR SHARE", (identifier,)).fetchone()[0] == identifier
        with connect() as revoker:
            revoker.execute("SET LOCAL lock_timeout='200ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable), revoker.transaction():
                revoker.execute("SELECT anvil.revoke_task_method(%s,%s,%s,%s)",
                                (ids["project"], identifier, uuid4(), "Synthetic reader race control"))
    revocation = uuid4()
    with connect() as revoker:
        assert revoker.execute("SELECT anvil.revoke_task_method(%s,%s,%s,%s) AS id",
                               (ids["project"], identifier, revocation, "Synthetic completed revocation control")).fetchone()["id"] == revocation
    with psycopg.connect(dsn, row_factory=dict_row) as owner:
        row = owner.execute("SELECT * FROM anvil.task_capability_revocations WHERE id=%s", (revocation,)).fetchone()
        assert row["operator_login"] == logins[0] and row["operator_admin"] == ids["user"]
        assert not owner.execute("SELECT id FROM anvil.task_capability_qualifications q WHERE id=%s AND NOT EXISTS(SELECT 1 FROM anvil.task_capability_revocations r WHERE r.qualification_id=q.id)", (identifier,)).fetchone()
