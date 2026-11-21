"""Actual enrolled/unenrolled qualifier controls on a marked synthetic target."""
import os
import secrets
from contextlib import contextmanager
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from test_kyc_native_program_sql import prepared as native_prepared

from anvil import evaluator_configurations as configs
from anvil.db import Jsonb, digest
from anvil.golden_kyc_evaluators import CRITERIA
from anvil.golden_kyc_native_program import program
from anvil.golden_kyc_runtime import seed
from anvil.kyc_policy_provision import enter
from infra.gcp.kyc_binding_observation import read_capability

TABLES = ("banking.anvil_imports", "banking.packs", "banking.applications",
          "anvil.environment_versions", "anvil.environment_task_bindings", "anvil.evaluator_configurations",
          "anvil.evaluator_validation_receipts", "anvil.evaluator_revocations")
pytestmark = pytest.mark.skipif(not os.environ.get("ANVIL_CONTEXT_TEST_DSN"), reason="Marked synthetic SQL target required")
prepared = native_prepared


@pytest.fixture(scope="module")
def operator(prepared):
    dsn, ids, refs, _ = prepared
    project, user = ids["project"], ids["user"]
    foreign, foreign_user, foreign_group = uuid4(), uuid4(), uuid4()
    logins = ["binding_qual_" + secrets.token_hex(5), "unmapped_qual_" + secrets.token_hex(5)]
    passwords = {name: secrets.token_urlsafe(32) for name in logins}
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        assert c.execute("SELECT max(version) AS v FROM anvil.schema_versions").fetchone()["v"] == 135
        c.execute("INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,'Foreign synthetic operator scope')", (foreign, ids["org"]))
        c.execute("INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,'synthetic-test',%s,'Foreign synthetic PO')", (foreign_user, ids["org"], str(foreign_user)))
        c.execute("INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,'admin')", (foreign, foreign_user))
        c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (str(foreign), str(foreign_user)))
        c.execute("INSERT INTO anvil.benchmark_task_groups(id,project_id,source_project_id,source_version,name,content,content_sha256,created_by) VALUES(%s,%s,%s,'synthetic','Foreign witness',%s,%s,%s)", (foreign_group, foreign, str(foreign), Jsonb({"fixture": True}), digest({"fixture": True}), foreign_user))
        for p, u, group in ((project, user, ids["group"]), (foreign, foreign_user, foreign_group)):
            c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (str(p), str(u)))
            pack = UUID(seed(c, str(p), str(u), include_expectations=False)["pack_id"])
            epack, env, binding, imported = (uuid4() for _ in range(4))
            body = {"purpose": "manufactured metadata isolation witness only"}
            c.execute("INSERT INTO anvil.environment_packs(id,project_id,template_id,scenario_id,content,content_sha256,validation,created_by) VALUES(%s,%s,'synthetic','synthetic',%s,%s,%s,%s)", (epack, p, Jsonb(body), digest(body), Jsonb({"fixture": True}), u))
            c.execute("INSERT INTO anvil.environment_versions(id,project_id,pack_id,name,manifest,manifest_sha256,created_by) VALUES(%s,%s,%s,'Synthetic scope witness',%s,%s,%s)", (env, p, epack, Jsonb(body), digest(body), u))
            c.execute("INSERT INTO anvil.environment_task_bindings(id,project_id,environment_id,task_group_id,task_id,task_version,snapshot,snapshot_sha256,created_by) VALUES(%s,%s,%s,%s,'synthetic','v1',%s,%s,%s)", (binding, p, env, group, Jsonb(body), digest(body), u))
            c.execute("INSERT INTO banking.anvil_imports(id,project_id,pack_id,task_group_id,environment_id,manifest,manifest_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)", (imported, p, pack, group, env, Jsonb(body), digest(body), u))
            c.execute("SET LOCAL ROLE anvil_app")
            extra = configs.create(c, p, u, configs.Configure(name="Synthetic revocation witness", adapter="builtin", native_kyc=program(next(iter(CRITERIA)))))
            configs.test_kyc_runtime(c, p, u, extra["id"])
            c.execute("INSERT INTO anvil.evaluator_revocations(id,project_id,configuration_id,created_by) VALUES(%s,%s,%s,%s)", (uuid4(), p, extra["id"], u))
            c.execute("RESET ROLE")
        for name in logins:
            c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION").format(sql.Identifier(name), sql.Literal(passwords[name])))
            c.execute(sql.SQL("GRANT anvil_kyc_qualifier TO {}").format(sql.Identifier(name)))
        c.execute("INSERT INTO anvil.kyc_policy_operator_principals(login_role,project_id,user_id) VALUES(%s,%s,%s)", (logins[0], project, user))

    @contextmanager
    def connect(*, enrolled=True, forged_project=None, forged_user=None):
        login = logins[0 if enrolled else 1]
        with psycopg.connect(make_conninfo(dsn, user=login, password=passwords[login]), row_factory=dict_row) as c:
            if enrolled and forged_project is None:
                assert enter(c, project) == user
            else:
                c.execute("SET LOCAL ROLE anvil_kyc_qualifier")
                c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                          (str(forged_project or project), str(forged_user or user)))
            yield c
    return dsn, ids, refs, foreign, foreign_user, connect


def test_actual_enrolled_operator_reads_own_public_records_not_known_foreign_witnesses(operator):
    dsn, ids, refs, foreign, _, connect = operator
    with psycopg.connect(dsn) as owner:
        for table in TABLES:
            assert owner.execute("SELECT count(*) FROM " + table + " WHERE project_id=%s", (foreign,)).fetchone()[0] > 0
    with connect() as c:
        assert read_capability(c, ids["project"])["private_grading_reads"] is False
        assert configs.get(c, refs[0]["id"])["status"] == "ready"
        for table in TABLES:
            assert c.execute("SELECT count(*) AS n FROM " + table + " WHERE project_id=%s", (ids["project"],)).fetchone()["n"] > 0
            assert c.execute("SELECT count(*) AS n FROM " + table + " WHERE project_id<>%s", (ids["project"],)).fetchone()["n"] == 0


def test_forged_admin_project_gucs_cannot_bypass_operator_enrollment(operator):
    _, ids, _, foreign, foreign_user, connect = operator
    for changes in ({"enrolled": False}, {"forged_project": foreign, "forged_user": foreign_user}):
        with connect(**changes) as c:
            with pytest.raises(ValueError, match="enrolled operator"):
                read_capability(c, ids["project"])
            for table in TABLES:
                assert c.execute("SELECT count(*) AS n FROM " + table).fetchone()["n"] == 0
    with connect() as c:
        c.execute("SELECT set_config('anvil.user',%s,true)", (str(foreign_user),))
        for table in TABLES:
            assert c.execute("SELECT count(*) AS n FROM " + table + " WHERE project_id=%s", (ids["project"],)).fetchone()["n"] == 0


def test_operator_gets_no_private_answer_access_or_new_public_writes(operator):
    _, _, _, _, _, connect = operator
    with connect() as c:
        for table in TABLES:
            for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                assert not c.execute("SELECT has_table_privilege(current_user,%s,%s) AS allowed", (table, privilege)).fetchone()["allowed"]
        for table in ("banking_private.expectations", "banking_private.expectation_versions", "banking_private.scenarios", "banking_private.results", "banking.seals"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
                c.execute("SELECT 1 FROM " + table + " LIMIT 1")
        for role in ("anvil_app", "anvil_worker", "anvil_golden_scheduler", "anvil_golden_grader"):
            assert not c.execute("SELECT pg_has_role(%s,'anvil_kyc_qualifier','MEMBER') AS allowed", (role,)).fetchone()["allowed"]


def test_owner_membership_revocation_invalidates_existing_operator_mapping(operator):
    dsn, ids, _, _, _, connect = operator
    with psycopg.connect(dsn) as c:
        c.execute("UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s", (ids["project"], ids["user"]))
    try:
        with connect(forged_project=ids["project"], forged_user=ids["user"]) as c:
            with pytest.raises(ValueError, match="enrolled operator"):
                read_capability(c, ids["project"])
            for table in TABLES:
                assert c.execute("SELECT count(*) AS n FROM " + table).fetchone()["n"] == 0
    finally:
        with psycopg.connect(dsn) as c:
            c.execute("UPDATE anvil.memberships SET active=true WHERE project_id=%s AND user_id=%s", (ids["project"], ids["user"]))
