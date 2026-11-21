"""Actual disjoint grader reads, only an explicitly marked synthetic cluster."""
import os
import secrets
from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from anvil import evaluator_configurations as configs
from anvil import golden_kyc_native_program as native
from anvil.db import Jsonb, digest
from anvil.golden_kyc_evaluators import CRITERIA

pytestmark = pytest.mark.skipif(not os.environ.get("ANVIL_CONTEXT_TEST_DSN"),
                                reason="Explicit isolated synthetic PostgreSQL required")


@pytest.fixture(scope="module")
def prepared():
    dsn = os.environ["ANVIL_CONTEXT_TEST_DSN"]
    names = ("org", "project", "user", "artifact", "template", "resolution", "resolved", "source",
             "package", "framework", "preset", "preparation", "execution", "group", "binding")
    ids = {name: uuid4() for name in names}
    p, u = ids["project"], ids["user"]
    body = {"purpose": "synthetic-sealed-criterion-sql-not-qualification"}
    h = digest(body)
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        assert c.execute("SELECT label FROM public.context_registrar_test_marker").fetchone() == {
            "label": "synthetic-context-registrar-only"}
        assert c.execute("SELECT max(version) AS v FROM anvil.schema_versions").fetchone()["v"] == 133
        c.execute("INSERT INTO anvil.organizations VALUES(%s,'Synthetic criterion SQL')", (ids["org"],))
        c.execute("INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,'Synthetic criterion SQL')", (p, ids["org"]))
        c.execute("INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,'synthetic-test',%s,'Synthetic PO')", (u, ids["org"], str(u)))
        c.execute("INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,'admin')", (p, u))
        c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (str(p), str(u)))
        c.execute("INSERT INTO anvil.artifacts(id,project_id,object_key,sha256,byte_size,mime_type,classification,scan_status,origin) VALUES(%s,%s,%s,%s,0,'application/octet-stream','hidden_reference','quarantined','synthetic-test')", (ids["artifact"], p, str(ids["artifact"]), h))
        c.execute("INSERT INTO anvil.praxis_template_versions(id,project_id,template_key,version,spec,spec_sha256,part_hashes,catalogue_sha256,created_by) VALUES(%s,%s,%s,1,%s,%s,'{}',%s,%s)", (ids["template"], p, str(ids["template"]), Jsonb(body), h, h, u))
        c.execute("INSERT INTO anvil.praxis_export_resolutions(id,project_id,package_key,version,package_sha256,batch_key,part_index,part_count,private_archive_id,receipt,receipt_sha256,created_by) VALUES(%s,%s,%s,'synthetic',%s,%s,0,1,%s,%s,%s,%s)", (ids["resolution"], p, str(ids["resolution"]), h, str(ids["resolution"]), ids["artifact"], Jsonb(body), h, u))
        c.execute("INSERT INTO anvil.praxis_resolved_tasks(id,project_id,resolution_id,template_id,task_key,revision,actor,actor_sha256,private_reference_sha256,binding,binding_sha256,created_by) VALUES(%s,%s,%s,%s,'synthetic-task','r1',%s,%s,%s,%s,%s,%s)", (ids["resolved"], p, ids["resolution"], ids["template"], Jsonb(body), h, h, Jsonb(body), h, u))
        c.execute("INSERT INTO anvil.praxis_sources(id,project_id,task_id,task_version,revision_id,source_sha256,source_artifact_id,actor_spec,created_by) VALUES(%s,%s,'synthetic-task','r1','r1',%s,%s,%s,%s)", (ids["source"], p, h, ids["artifact"], Jsonb(body), u))
        c.execute("INSERT INTO anvil.harbor_packages(id,project_id,source_id,package_sha256,package_artifact_id,manifest,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)", (ids["package"], p, ids["source"], h, ids["artifact"], Jsonb(body), u))
        c.execute("INSERT INTO anvil.workspace_framework_profiles(id,project_id,name,framework,config,config_hash,created_by) VALUES(%s,%s,'Synthetic only','harbor',%s,%s,%s)", (ids["framework"], p, Jsonb(body), h, u))
        c.execute("INSERT INTO anvil.workspace_execution_presets(id,project_id,name,runner_profile_id,snapshot,subject_hash,created_by) VALUES(%s,%s,'Synthetic only',%s,%s,%s,%s)", (ids["preset"], p, ids["framework"], Jsonb(body), h, u))
        c.execute("INSERT INTO anvil.workspace_run_preparations(id,project_id,preset_id,package_id,snapshot,subject_hash,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)", (ids["preparation"], p, ids["preset"], ids["package"], Jsonb(body), h, u))
        c.execute("INSERT INTO anvil.benchmark_task_groups(id,project_id,source_project_id,source_version,name,content,content_sha256,created_by) VALUES(%s,%s,%s,'synthetic','Synthetic only',%s,%s,%s)", (ids["group"], p, str(ids["group"]), Jsonb(body), h, u))
        refs = []
        c.execute("SET LOCAL ROLE anvil_app")
        for criterion in CRITERIA:
            row = configs.create(c, p, u, configs.Configure(name="Synthetic " + criterion,
                adapter="builtin", native_kyc=native.program(criterion)))
            row = configs.test_kyc_runtime(c, p, u, row["id"])
            assert row["status"] == "ready"
            target = "criterion:" + digest({"task_id": "synthetic-task", "task_version": "r1",
                                            "payload_sha256": h, "criterion_id": criterion})
            refs.append({"kind": "evaluator", "id": str(row["id"]), "sha256": row["configuration_sha256"], "target": target})
        snapshot = {"rubric": refs, "purpose": "synthetic-not-qualified"}
        c.execute("INSERT INTO anvil.project_binding_versions(id,project_id,task_group_id,version,snapshot,snapshot_sha256,created_by) VALUES(%s,%s,%s,1,%s,%s,%s)", (ids["binding"], p, ids["group"], Jsonb(snapshot), digest(snapshot), u))
        execution = {"preparation": {"project_binding": {"id": str(ids["binding"]), "task_group_id": str(ids["group"]), "snapshot_sha256": digest(snapshot)}}}
        c.execute("INSERT INTO anvil.workspace_execution_groups(id,project_id,preparation_id,created_by,snapshot,subject_hash) VALUES(%s,%s,%s,%s,%s,%s)", (ids["execution"], p, ids["preparation"], u, Jsonb(execution), digest(execution)))
        c.execute("RESET ROLE")
        login, password = "sealed_kyc_sql_" + secrets.token_hex(5), secrets.token_urlsafe(32)
        c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION").format(sql.Identifier(login), sql.Literal(password)))
        c.execute(sql.SQL("GRANT anvil_golden_grader TO {}").format(sql.Identifier(login)))
    @contextmanager
    def grader():
        with psycopg.connect(make_conninfo(dsn, user=login, password=password), row_factory=dict_row) as c:
            c.execute("SET LOCAL ROLE anvil_golden_grader")
            c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (str(p), str(u)))
            yield c
    return dsn, ids, refs, grader


def test_real_disjoint_grader_reads_exact_programs_and_cannot_modify(prepared):
    _, ids, refs, grader = prepared
    paid = {"group_id": ids["execution"], "resolved_task_id": ids["resolved"]}
    with grader() as c:
        assert c.execute("SELECT current_user AS role").fetchone()["role"] == "anvil_golden_grader"
        result = native.selected(c, ids["project"], paid)
        assert len(result) == 20 and {r["criterion"] for r in result} == set(CRITERIA)
        with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
            c.execute("INSERT INTO anvil.evaluator_revocations(id,project_id,configuration_id,created_by) VALUES(%s,%s,%s,%s)", (uuid4(), ids["project"], refs[0]["id"], ids["user"]))
        c.execute("SELECT set_config('anvil.project',%s,true)", (str(uuid4()),))
        assert not c.execute("SELECT id FROM anvil.evaluator_configurations WHERE id=%s", (refs[0]["id"],)).fetchall()
        with pytest.raises(ValueError, match="Frozen KYC execution"):
            native.selected(c, ids["project"], paid)


def test_revocation_is_rechecked_under_actual_grader(prepared):
    dsn, ids, refs, grader = prepared
    with psycopg.connect(dsn) as c:
        c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                  (str(ids["project"]), str(ids["user"])))
        c.execute("SET LOCAL ROLE anvil_app")
        c.execute("INSERT INTO anvil.evaluator_revocations(id,project_id,configuration_id,created_by) VALUES(%s,%s,%s,%s)", (uuid4(), ids["project"], refs[0]["id"], ids["user"]))
    with grader() as c, pytest.raises(ValueError, match="Exact qualified"):
        native.selected(c, ids["project"], {"group_id": ids["execution"], "resolved_task_id": ids["resolved"]})
