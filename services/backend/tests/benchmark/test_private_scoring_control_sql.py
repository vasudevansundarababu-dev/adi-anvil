"""Real private selection/queue and isolated admission, no mocks or Docker.

SQL-only precursor to installed physical controls; no runtime qualification,
paid capture, model result or human/legal approval is created.
"""

import importlib.util
import os
import secrets
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from test_golden_kyc_sql import owned as owned_fixture

from anvil import custom_python_grading as grading
from anvil.db import Jsonb, digest
from anvil.golden_kyc_source import source_hash
from anvil.native_image_profile import IMAGE_ID


@pytest.fixture(scope="module")
def fixture():
    owned = owned_fixture.__wrapped__()
    root = Path(__file__).resolve().parents[4]
    spec = importlib.util.spec_from_file_location("synthetic_private_scoring_fixture", root / "runtime-checks/private_scoring_fixture.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    code, cases, review_sha = helper.reviewed_files(root / "fixtures/private-scoring-control")
    nonce, password = secrets.token_hex(32), secrets.token_urlsafe(32)
    login = "technical_grader_" + secrets.token_hex(5)
    # Explicit SQL-only runtime pin, not evidence of an installed image.
    previous = os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST")
    os.environ["ANVIL_RUNTIME_IMAGE_DIGEST"] = IMAGE_ID.removeprefix("sha256:")
    with psycopg.connect(owned[0], row_factory=dict_row) as c:
        c.execute("CREATE TABLE anvil.component_control_fixture(fixture_nonce text PRIMARY KEY,fixture_label text,project_id uuid,created_at timestamptz DEFAULT clock_timestamp(),consumed_at timestamptz)")
        c.execute("INSERT INTO anvil.component_control_fixture(fixture_nonce,fixture_label,project_id) VALUES(%s,'synthetic-component-control-not-performance',%s)", (nonce, owned[1]))
        c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION").format(sql.Identifier(login), sql.Literal(password)))
        c.execute(sql.SQL("GRANT anvil_golden_grader TO {}").format(sql.Identifier(login)))
        database = c.info.dbname
    config = {"project_id": str(owned[1]), "user_id": str(owned[2]), "pack_id": str(owned[4]), "application_id": "GB-001",
              "fixture_nonce": nonce, "runtime_image_sha256": os.environ["ANVIL_RUNTIME_IMAGE_DIGEST"], "golden_source_sha256": source_hash()}
    dsn = make_conninfo(owned[0], user=login, password=password)

    @contextmanager
    def grader():
        with psycopg.connect(dsn, row_factory=dict_row) as c:
            c.execute("SET LOCAL ROLE anvil_golden_grader")
            c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (owned[1], owned[2]))
            yield c

    def prepare(index=0):
        with psycopg.connect(owned[0], row_factory=dict_row) as c:
            return helper.prepare(c, config, code, cases["reference"], cases["cases"][index], review_sha)

    yield {"owned": owned, "grader": grader, "prepare": prepare, "database": database}
    if previous is None:
        os.environ.pop("ANVIL_RUNTIME_IMAGE_DIGEST", None)
    else:
        os.environ["ANVIL_RUNTIME_IMAGE_DIGEST"] = previous


def enqueue(fixture, item, *, technical=True):
    with fixture["grader"]() as c:
        result = grading.collect_or_queue(c, fixture["owned"][1], item["execution"], item["trial"]["trial_id"], item["trial"]["generation"],
            item["state"], item["expectation"], item["checks"], **({"_technical": item["reference"]} if technical else {}))
        job = c.execute("SELECT * FROM banking_private.python_grading_jobs WHERE id=%s", (item["context"]["job_id"],)).fetchone()
    return result, job


def test_real_selection_queue_no_production_qualification_and_idempotence(fixture):
    item = fixture["prepare"]()
    with pytest.raises(RuntimeError, match="qualification_required"):
        enqueue(fixture, item, technical=False)
    result, job = enqueue(fixture, item)
    assert result["pending"] and job["state"] == "queued"
    assert job["request"]["schema_version"] == "anvil.private-python-control-grade.v1"
    assert job["request"]["technical_control"] == item["reference"].wire()
    again, same = enqueue(fixture, item)
    assert again["pending"] and same["id"] == job["id"]
    with fixture["grader"]() as c:
        assert grading.job_eligible(c, job)
        intent = c.execute("SELECT * FROM banking_private.python_control_intents WHERE admission_id=%s", (item["reference"].id,)).fetchall()
        assert len(intent) == 1 and intent[0]["job_id"] == job["id"]
        assert not c.execute("SELECT id FROM anvil.project_binding_qualifications").fetchall()
        with pytest.raises(RuntimeError, match="cross purposes"):
            grading.consume_result(c, job, {"criterion": "profile", "target": item["context"]["target"]})


def test_current_admission_revocation_and_input_changes_deny_without_effect(fixture):
    item = fixture["prepare"](1)
    _, job = enqueue(fixture, item)
    with psycopg.connect(fixture["owned"][0]) as c:
        c.execute("INSERT INTO banking_private.python_control_revocations(admission_id,project_id,reason) VALUES(%s,%s,'Synthetic revocation control')",
                  (item["reference"].id, fixture["owned"][1]))
    with fixture["grader"]() as c:
        assert not grading.job_eligible(c, job)
    with pytest.raises(RuntimeError, match="admission required"):
        enqueue(fixture, item)
    other = fixture["prepare"](2)
    other["state"] = {"final": {"sum": 7}}
    with pytest.raises(RuntimeError, match="reviewed synthetic"):
        enqueue(fixture, other)


def test_app_scheduler_and_mixed_principal_cannot_mint_or_read_admission(fixture):
    item = fixture["prepare"](3)
    for role in ("anvil_app", "anvil_golden_scheduler", "anvil_worker"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(fixture["owned"][0]) as c:
            c.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
            c.execute("SELECT * FROM banking_private.python_control_admissions")
    with pytest.raises(psycopg.errors.InsufficientPrivilege), fixture["grader"]() as c:
        c.execute("UPDATE banking_private.python_control_admissions SET context='{}' WHERE id=%s", (item["reference"].id,))
    with fixture["grader"]() as c:
        c.execute("SELECT set_config('anvil.project',%s,true)", (str(uuid4()),))
        assert not c.execute("SELECT id FROM banking_private.python_control_admissions").fetchall()
    with pytest.raises(psycopg.errors.InsufficientPrivilege), fixture["grader"]() as c:
        c.execute("SELECT user_id FROM anvil.memberships")


def test_revocation_after_committed_claim_preserves_error_purpose_and_unscored(fixture):
    item = fixture["prepare"](4)
    _, job = enqueue(fixture, item)
    with fixture["grader"]() as c:
        c.execute("UPDATE banking_private.python_grading_jobs SET state='claimed',claim_token=%s,claimed_at=clock_timestamp() WHERE id=%s", (uuid4(), job["id"]))
    with psycopg.connect(fixture["owned"][0]) as c:
        c.execute("INSERT INTO banking_private.python_control_revocations(admission_id,project_id,reason) VALUES(%s,%s,'Revoked after actual committed claim')", (item["reference"].id, fixture["owned"][1]))
    result = grading.result_envelope(job["request"], job["request_sha256"]) | {"reason": "authority_changed_during_execution"}
    with fixture["grader"]() as c:
        assert not grading.job_eligible(c, job)
        with pytest.raises(psycopg.errors.RaiseException), c.transaction():
            c.execute("UPDATE banking_private.python_grading_jobs SET state='completed',result=%s,result_sha256=%s,finished_at=now() WHERE id=%s", (Jsonb(result | {"status": "pass"}), digest(result | {"status": "pass"}), job["id"]))
        c.execute("UPDATE banking_private.python_grading_jobs SET state='error',result=%s,result_sha256=%s,finished_at=now() WHERE id=%s", (Jsonb(result), digest(result), job["id"]))
        stored = c.execute("SELECT * FROM banking_private.python_grading_jobs WHERE id=%s", (job["id"],)).fetchone()
        program = {"criterion": "profile", "target": item["context"]["target"], "id": item["context"]["evaluator_id"], "sha256": item["context"]["code_sha256"]}
        receipt = grading.consume_result(c, stored, program, _technical=item["reference"])
        assert receipt["status"] == "error" and receipt["technical_control"] == item["reference"].wire()


def test_cross_purpose_result_substitution_is_rejected_by_real_sql(fixture):
    item = fixture["prepare"](5)
    _, job = enqueue(fixture, item)
    with fixture["grader"]() as c:
        c.execute("UPDATE banking_private.python_grading_jobs SET state='claimed',claim_token=%s,claimed_at=clock_timestamp() WHERE id=%s", (uuid4(), job["id"]))
    forged = grading.result_envelope(job["request"], job["request_sha256"])
    forged.pop("technical_control")
    forged["schema_version"] = grading.SCHEMA
    with pytest.raises(psycopg.errors.RaiseException), fixture["grader"]() as c:
        c.execute("UPDATE banking_private.python_grading_jobs SET state='error',result=%s,result_sha256=%s,finished_at=now() WHERE id=%s", (Jsonb(forged), digest(forged), job["id"]))
