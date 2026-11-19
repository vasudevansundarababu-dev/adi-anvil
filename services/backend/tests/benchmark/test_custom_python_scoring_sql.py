"""Isolated SQL prerequisites, NOT physical Python-runner qualification.

Synthetic program selection/qualification stubs are explicit below. Real FKs,
dedicated grader LOGIN, private RLS, immutable inputs, transitions and durable
reconciliation remain enabled. No submitted Python, Docker or model is executed.
"""

import copy
import hashlib
import secrets
from contextlib import contextmanager
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from test_golden_kyc_sql import connection
from test_golden_kyc_sql import owned as owned_fixture

from anvil import custom_python_grading as grading
from anvil.db import Jsonb, digest
from anvil.golden_kyc_evaluators import CRITERIA, score
from anvil.golden_kyc_runtime import create_trial

owned = owned_fixture


@pytest.fixture
def scoring(owned, monkeypatch):
    project, user = owned[1:3]
    group, binding_id, evaluator = (uuid4() for _ in range(3))
    code = 'def evaluate(actual, expected):\n    return {"status": "pass"}\n'
    code_sha = hashlib.sha256(code.encode()).hexdigest()
    target = "criterion:" + digest({"task_id": "synthetic-task", "task_version": "r1",
                                    "payload_sha256": "a" * 64, "criterion_id": "profile"})
    snapshot = {"source_sha256": "b" * 64, "rubric": [{"kind": "custom_python", "id": str(evaluator),
                 "sha256": code_sha, "target": target}], "policy": [], "synthetic_only": "SQL-not-QA"}
    with connection(owned) as c:
        c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (project, user))
        c.execute("SET LOCAL ROLE anvil_app")
        c.execute("INSERT INTO anvil.benchmark_task_groups(id,project_id,source_project_id,source_version,name,content,content_sha256,created_by) "
                  "VALUES(%s,%s,'synthetic-private-python','test-v1','Synthetic SQL only',%s,%s,%s)",
                  (group, project, Jsonb({}), digest({}), user))
        c.execute("INSERT INTO anvil.project_binding_versions(id,project_id,task_group_id,version,snapshot,snapshot_sha256,created_by) "
                  "VALUES(%s,%s,%s,1,%s,%s,%s)", (binding_id, project, group, Jsonb(snapshot), digest(snapshot), user))
        c.execute("INSERT INTO anvil.custom_python_evaluators(id,project_id,name,code,code_sha256,created_by) "
                  "VALUES(%s,%s,'Synthetic never executed',%s,%s,%s)", (evaluator, project, code, code_sha, user))
        c.execute("RESET ROLE")
        trial = create_trial(c, project, user, owned[4], "GB-001", "synthetic-private-python", 1)
        binding = c.execute("SELECT * FROM anvil.project_binding_versions WHERE id=%s", (binding_id,)).fetchone()
        login, password = "python_sql_" + secrets.token_hex(5), secrets.token_urlsafe(32)
        c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION")
                  .format(sql.Identifier(login), sql.Literal(password)))
        c.execute(sql.SQL("GRANT anvil_golden_grader TO {}").format(sql.Identifier(login)))
    dsn = make_conninfo(owned[0], user=login, password=password)

    @contextmanager
    def grader():
        with psycopg.connect(dsn, row_factory=dict_row) as c:
            c.execute("SET LOCAL ROLE anvil_golden_grader")
            c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (project, user))
            yield c

    program = snapshot["rubric"][0] | {"code": code, "criterion": "profile", "policy": None}
    # External frozen-Run admission is outside this bounded queue test. Never
    # reuse this stub as evidence that programs()/qualification succeeded.
    monkeypatch.setattr(grading, "programs", lambda *args: (binding, [program]))
    monkeypatch.setenv("ANVIL_CUSTOM_PYTHON_SCORING_ENABLED", "true")
    return {"owned": owned, "binding": binding, "program": program, "trial": trial,
            "grader": grader, "snapshot": snapshot}


def enqueue(scoring, *, reviewed=True, final="synthetic-private-final"):
    with scoring["grader"]() as c:
        outcome = grading.collect_or_queue(c, scoring["owned"][1], {}, scoring["trial"]["trial_id"], 0,
            {"final": final}, {"independent_expectation_review": "approved" if reviewed else "pending",
                               "criterion_references": {"profile": "synthetic-private-reference"}}, {"profile": True})
        job = c.execute("SELECT * FROM banking_private.python_grading_jobs WHERE trial_id=%s",
                        (scoring["trial"]["trial_id"],)).fetchone()
    return outcome, job


def test_real_private_queue_is_idempotent_hidden_and_immutable(scoring):
    first, job = enqueue(scoring)
    again, same = enqueue(scoring)
    assert first["pending"] and again["pending"] and same["id"] == job["id"]
    assert job["request"]["expected"]["criterion_reference"] == "synthetic-private-reference"
    assert job["request_sha256"] == digest(job["request"])
    with pytest.raises(RuntimeError, match="input_changed_no_replay"):
        enqueue(scoring, final="changed-input-must-not-replace-intent")
    for role in ("anvil_app", "anvil_golden_scheduler", "anvil_worker"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connection(scoring["owned"]) as c:
            c.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
            c.execute("SELECT request FROM banking_private.python_grading_jobs")
    with pytest.raises(psycopg.errors.InsufficientPrivilege), scoring["grader"]() as c:
        c.execute("UPDATE banking_private.python_grading_jobs SET request=%s WHERE id=%s", (Jsonb({}), job["id"]))
    with scoring["grader"]() as c:
        c.execute("SELECT set_config('anvil.project',%s,true)", (str(uuid4()),))
        assert not c.execute("SELECT id FROM banking_private.python_grading_jobs").fetchall()


def test_pending_review_never_queues_or_awards_points(scoring):
    result, job = enqueue(scoring, reviewed=False)
    assert job is None and not result["pending"]
    assert result["receipts"][0]["status"] == "unscored"
    assert result["receipts"][0]["reason"] == "source_review_pending"


def test_binding_target_program_and_revocation_fences_with_synthetic_qualification(scoring, monkeypatch):
    from anvil import project_bindings

    _, job = enqueue(scoring)
    release = "d" * 64
    monkeypatch.setenv("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256", release)
    # Deliberately manufactured prerequisite: tests downstream identity matching,
    # not independent qualification, evidence_gaps(), or physical execution.
    evidence = {"synthetic_only": "NOT independent QA qualification"}
    with connection(scoring["owned"]) as c:
        c.execute("INSERT INTO anvil.project_binding_qualifications(id,project_id,binding_id,release_sha256,evidence,evidence_sha256,expires_at) "
                  "VALUES(%s,%s,%s,%s,%s,%s,clock_timestamp()+interval '5 minutes')",
                  (uuid4(), scoring["owned"][1], scoring["binding"]["id"], release, Jsonb(evidence), digest(evidence)))
    monkeypatch.setattr(project_bindings, "evidence_gaps", lambda *args: [])
    with scoring["grader"]() as c:
        assert grading.job_eligible(c, job)
        for field, value in (("target", "criterion:wrong-task-target"), ("code_sha256", "0" * 64),
                             ("binding_sha256", "0" * 64), ("source_sha256", "0" * 64), ("image_id", "wrong-image")):
            changed = copy.deepcopy(job)
            changed["request"][field] = value
            assert not grading.job_eligible(c, changed), field
        changed = dict(job, evaluator_id=uuid4())
        assert not grading.job_eligible(c, changed)
    with connection(scoring["owned"]) as c:
        c.execute("INSERT INTO anvil.custom_python_revocations(id,project_id,evaluator_id,created_by) VALUES(%s,%s,%s,%s)",
                  (uuid4(), scoring["owned"][1], scoring["program"]["id"], scoring["owned"][2]))
    with scoring["grader"]() as c:
        assert not grading.job_eligible(c, job)


def test_claim_commit_unknown_reconciliation_and_terminal_no_replay(scoring, tmp_path, monkeypatch):
    _, job = enqueue(scoring)
    root = tmp_path / "private-grading"
    root.mkdir(mode=0o700)
    # Synthetic admission only: no coordinator/execute() is started. Waiting for
    # a nonexistent result deliberately reproduces an ambiguous completion.
    monkeypatch.setattr(grading, "job_eligible", lambda *args: True)
    with pytest.raises(RuntimeError, match="completion_unconfirmed_no_replay"):
        grading.grader_once(scoring["grader"], root, seconds=1)
    with scoring["grader"]() as c:
        claimed = c.execute("SELECT * FROM banking_private.python_grading_jobs WHERE id=%s", (job["id"],)).fetchone()
        assert claimed["state"] == "claimed" and claimed["claim_token"] and claimed["claimed_at"]
    assert (root / UUID(str(job["id"])).hex / "request.json").exists()
    assert grading.grader_once(scoring["grader"], root, seconds=1) is None
    pending = grading.reconcile(scoring["grader"], root, str(job["id"]))
    assert pending["state"] == "claimed" and pending["physical_execution_replayed"] is False
    disposed = grading.reconcile(scoring["grader"], root, str(job["id"]), abandon=True)
    assert disposed["state"] == "error" and disposed["physical_execution_replayed"] is False
    assert grading.reconcile(scoring["grader"], root, str(job["id"]))["already_terminal"]
    with scoring["grader"]() as c:
        result = c.execute("SELECT result FROM banking_private.python_grading_jobs WHERE id=%s", (job["id"],)).fetchone()["result"]
        assert result["execution_may_have_occurred"] is True and result["cleanup_status"] == "not_verified"
    with pytest.raises(psycopg.Error), scoring["grader"]() as c:
        c.execute("UPDATE banking_private.python_grading_jobs SET state='queued' WHERE id=%s", (job["id"],))


@pytest.mark.parametrize("status", ["error", "unscored"])
def test_missing_or_error_override_unscored_and_mandatory_critical_veto_survives(scoring, status):
    # Pure scorer consumes the same status vocabulary as SQL results. No physical
    # runner result is manufactured or published by this test.
    baseline = score(dict.fromkeys(CRITERIA, 5), correct_decision=True, mandatory=False,
                     critical_failures=["synthetic-mandatory-veto"])
    receipt = {"criterion": "profile", "target": scoring["program"]["target"], "status": status}
    result = grading.apply_overrides(baseline, {"independent_expectation_review": "approved"}, [receipt])
    assert result["checks"]["profile"] is None and result["rubric_score"]["unscored_points"] == 5
    assert result["mandatory_conditions"] is False and result["overall_result"] == "critical_fail"
    passing = grading.apply_overrides(baseline, {"independent_expectation_review": "approved"}, [receipt | {"status": "pass"}])
    assert passing["overall_result"] == "critical_fail" and passing["mandatory_conditions"] is False
