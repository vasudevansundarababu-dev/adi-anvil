import json
import subprocess
import sys

import psycopg
import pytest
from psycopg.errors import RaiseException
from psycopg.rows import dict_row

from anvil import worker
from anvil.config import ROOT, setting
from anvil.db import one, transaction, uid
from anvil.evaluation import GRAPH_VERSION


def prepared_job(graph_version):
    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    project = journey["project_id"]
    user = json.loads((ROOT / ".local/demo-identities.json").read_text())["researcher"]
    rid, eid, jid, token = uid(), uid(), uid(), uid()
    with transaction(project, user) as c:
        task = one(
            c,
            "SELECT task_revision_id FROM anvil.episodes WHERE id=%s",
            (journey["episodes"][0]["id"],),
        )
        c.execute(
            "INSERT INTO anvil.runs(id,project_id,protocol_revision_id,origin,created_by,state) VALUES(%s,%s,%s,'illustrative',%s,'queued')",
            (rid, project, journey["protocol"]["current_revision_id"], user),
        )
        c.execute(
            "INSERT INTO anvil.episodes(id,project_id,run_id,task_revision_id,candidate_key,thread_id,graph_version) VALUES(%s,%s,%s,%s,'fixture-correct',%s,%s)",
            (eid, project, rid, task["task_revision_id"], uid(), graph_version),
        )
        c.execute(
            "INSERT INTO anvil.jobs(id,project_id,kind,target_id,operation_key,status,lease_token,lease_until) VALUES(%s,%s,'episode',%s,%s,'leased',%s,now()+interval '60 seconds')",
            (jid, project, eid, "isolated-worker-test:" + jid, token),
        )
        return one(c, "SELECT * FROM anvil.jobs WHERE id=%s", (jid,))


def test_stale_worker_token_cannot_mutate_or_invoke():
    job = prepared_job(GRAPH_VERSION)
    with transaction(job["project_id"], worker=True) as c:
        with pytest.raises(RuntimeError, match="lease_lost"):
            worker.guard(c, {**job, "lease_token": uid()})
        e = one(
            c, "SELECT state,invocation_count FROM anvil.episodes WHERE id=%s", (job["target_id"],)
        )
        assert e["state"] == "queued" and e["invocation_count"] == 0
        c.execute("UPDATE anvil.jobs SET status='cancelled' WHERE id=%s", (job["id"],))
        c.execute("UPDATE anvil.episodes SET state='cancelled' WHERE id=%s", (job["target_id"],))


def test_runtime_bindings_and_checkpoint_thread_are_immutable():
    job = prepared_job(GRAPH_VERSION)
    with transaction(job["project_id"], worker=True) as c:
        episode = one(c, "SELECT * FROM anvil.episodes WHERE id=%s", (job["target_id"],))
        for query, value in [
            ("UPDATE anvil.episodes SET thread_id=%s WHERE id=%s", uid()),
            ("UPDATE anvil.episodes SET graph_version=%s WHERE id=%s", "another-graph"),
            ("UPDATE anvil.episodes SET candidate_key=%s WHERE id=%s", "fixture-constraint-blind"),
            ("UPDATE anvil.episodes SET task_revision_id=%s WHERE id=%s", uid()),
        ]:
            with pytest.raises(RaiseException, match="immutable episode binding"), c.transaction():
                c.execute(query, (value, episode["id"]))
        with pytest.raises(RaiseException, match="immutable run binding"), c.transaction():
            c.execute(
                "UPDATE anvil.runs SET origin='adi_executed' WHERE id=%s", (episode["run_id"],)
            )
        with pytest.raises(RaiseException, match="immutable run binding"), c.transaction():
            c.execute(
                "UPDATE anvil.runs SET protocol_revision_id=%s WHERE id=%s",
                (uid(), episode["run_id"]),
            )
        c.execute("UPDATE anvil.jobs SET status='cancelled' WHERE id=%s", (job["id"],))
        c.execute("UPDATE anvil.episodes SET state='cancelled' WHERE id=%s", (episode["id"],))


def test_worker_rechecks_rights_and_active_run_author():
    job = prepared_job(GRAPH_VERSION)
    with transaction(job["project_id"], worker=True) as c:
        episode = worker.guard(c, job)
        task = one(
            c, "SELECT content FROM anvil.revisions WHERE id=%s", (episode["task_revision_id"],)
        )["content"]
        with (
            pytest.raises(RuntimeError, match="rights_revoked"),
            c.transaction(force_rollback=True),
        ):
            c.execute(
                "UPDATE anvil.rights_grants SET status='revoked' WHERE source_revision_id=%s AND operation='managed_evaluation'",
                (task["source_revision_id"],),
            )
            worker.guard(c, job)
        assert worker.guard(c, job)["invocation_count"] == 0
    # Only the migration/test owner can prepare a membership revocation. Exercise the
    # guard after switching to the actual non-owner worker role, then roll back.
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as owner:
        with (
            pytest.raises(RuntimeError, match="run_authorization_revoked"),
            owner.transaction(force_rollback=True),
        ):
            owner.execute(
                "UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s AND role='researcher'",
                (job["project_id"], episode["run_author"]),
            )
            owner.execute("SELECT set_config('anvil.project',%s,true)", (str(job["project_id"]),))
            owner.execute("SET LOCAL ROLE anvil_worker")
            worker.guard(owner, job)
    with transaction(job["project_id"], worker=True) as c:
        assert worker.guard(c, job)["invocation_count"] == 0
        c.execute("UPDATE anvil.jobs SET status='cancelled' WHERE id=%s", (job["id"],))
        c.execute("UPDATE anvil.episodes SET state='cancelled' WHERE id=%s", (episode["id"],))


def test_expired_lease_cannot_commit_even_with_matching_token():
    job = prepared_job(GRAPH_VERSION)
    with transaction(job["project_id"], worker=True) as c:
        c.execute(
            "UPDATE anvil.jobs SET lease_until=now()-interval '1 second' WHERE id=%s", (job["id"],)
        )
        with pytest.raises(RuntimeError, match="lease_lost"):
            worker.guard(c, job)
        c.execute("UPDATE anvil.jobs SET status='cancelled' WHERE id=%s", (job["id"],))
        c.execute("UPDATE anvil.episodes SET state='cancelled' WHERE id=%s", (job["target_id"],))


@pytest.mark.parametrize(
    "crash_stage,expected_captures",
    [("validate_authorization", 0), ("invoke_fixture_capture_output", 1)],
)
def test_abrupt_fixture_worker_exit_recovers_without_duplicate_invocation(
    monkeypatch, crash_stage, expected_captures
):
    job = prepared_job(GRAPH_VERSION)
    child = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/crash_fixture_child.py"),
            str(job["project_id"]),
            str(job["id"]),
            crash_stage,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == -9, child.stderr
    with transaction(job["project_id"], worker=True) as c:
        episode = one(c, "SELECT * FROM anvil.episodes WHERE id=%s", (job["target_id"],))
        assert episode["invocation_count"] == expected_captures
        replacement = uid()
        c.execute(
            "UPDATE anvil.jobs SET lease_token=%s,lease_until=now()+interval '60 seconds',attempts=attempts+1 WHERE id=%s",
            (replacement, job["id"]),
        )
        recovered = one(c, "SELECT * FROM anvil.jobs WHERE id=%s", (job["id"],))
        with pytest.raises(RuntimeError, match="lease_lost"):
            worker.guard(c, job)
    original = worker.one
    monkeypatch.setattr(
        worker,
        "one",
        lambda c, query, params=(): (
            recovered if query == "SELECT * FROM anvil.claim_job()" else original(c, query, params)
        ),
    )
    assert worker.tick()
    with transaction(job["project_id"], worker=True) as c:
        episode = one(c, "SELECT * FROM anvil.episodes WHERE id=%s", (job["target_id"],))
        assert episode["state"] == "awaiting_review"
        assert episode["invocation_count"] == 1 and episode["score"] is None
        assert (
            one(c, "SELECT status FROM anvil.jobs WHERE id=%s", (job["id"],))["status"]
            == "succeeded"
        )


def test_graph_version_mismatch_is_operational_invalidity_not_candidate_failure(monkeypatch):
    job = prepared_job("unsupported-test-graph-version")
    original = worker.one

    def claim(c, query, params=()):
        return job if query == "SELECT * FROM anvil.claim_job()" else original(c, query, params)

    monkeypatch.setattr(worker, "one", claim)
    assert worker.tick()
    with transaction(job["project_id"], worker=True) as c:
        e = one(c, "SELECT * FROM anvil.episodes WHERE id=%s", (job["target_id"],))
        assert e["state"] == "failed_operational" and e["outcome"] == "invalid"
        assert e["score"] is None and e["invocation_count"] == 0
        assert (
            one(c, "SELECT state FROM anvil.runs WHERE id=%s", (e["run_id"],))["state"]
            == "execution_complete"
        )
        assert (
            one(c, "SELECT error_code FROM anvil.jobs WHERE id=%s", (job["id"],))["error_code"]
            == "graph_version_mismatch"
        )
