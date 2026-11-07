"""Concurrent run finalization with real PostgreSQL transactions.

Each test forces one interleaving deterministically. A finalizer is held inside its open
transaction (at the `episode.finalized` audit write) until either the competing transaction
has reached the same point or PostgreSQL reports that the competitor is waiting on a lock
held by the paused transaction. Only this test's own connections, tagged with a unique
`application_name`, count as competitors, so a local dev worker or API cannot release a
pause. No sleeps decide the outcome.
"""

import json
import threading
import time

import psycopg
import pytest
from test_api_security import client_factory  # noqa: F401

from anvil import evaluation, worker
from anvil.config import ROOT, setting
from anvil.db import one, transaction, uid
from anvil.evaluation import GRAPH_VERSION

USERS = json.loads((ROOT / ".local/demo-identities.json").read_text())
CANDIDATES = ("fixture-correct", "fixture-constraint-blind")
TIMEOUT = 20
REAL_ONE = worker.one


@pytest.fixture(autouse=True)
def tagged_connections(monkeypatch):
    monkeypatch.setenv("PGAPPNAME", "anvil-finalization-test-" + uid()[:8])


def blocked_by(pid):
    with psycopg.connect(setting("WORKER_DATABASE_URL")) as c:
        return bool(
            c.execute(
                "SELECT 1 FROM pg_stat_activity WHERE application_name=current_setting('application_name') AND %s = ANY(pg_blocking_pids(pid))",
                (pid,),
            ).fetchone()
        )


class Rendezvous:
    """Pause each thread at a hook until `ready()` holds or another backend waits on it."""

    def __init__(self, ready):
        self.ready = ready
        self.arrived = []
        self.lock = threading.Lock()

    def pause(self, conn):
        with self.lock:
            self.arrived.append(threading.current_thread().name)
        deadline = time.monotonic() + TIMEOUT
        while not (self.ready(self) or blocked_by(conn.info.backend_pid)):
            assert time.monotonic() < deadline, "rendezvous timed out"
            time.sleep(0.01)


def lease(c, project, kind, eid, key):
    jid = uid()
    c.execute(
        "INSERT INTO anvil.jobs(id,project_id,kind,target_id,operation_key,status,lease_token,lease_until) "
        "VALUES(%s,%s,%s,%s,%s,'leased',%s,now()+interval '60 seconds')",
        (jid, project, kind, eid, f"{key}:{jid}", uid()),
    )
    return one(c, "SELECT * FROM anvil.jobs WHERE id=%s", (jid,))


REMAINING_AFTER_FAILURE = (
    "SELECT 1 FROM anvil.episodes WHERE run_id=%s AND state NOT IN ('failed_operational'"
)


def tick_as(monkeypatch, assignments, after=None):
    """Patch claim so the named thread processes exactly its assigned job.

    `after` maps a query prefix to a hook called with the open connection after that query.
    """
    original = REAL_ONE

    def claim(c, query, params=()):
        if query == "SELECT * FROM anvil.claim_job()":
            return assignments[threading.current_thread().name]
        row = original(c, query, params)
        for prefix, hook in (after or {}).items():
            if query.startswith(prefix):
                hook(c)
        return row

    monkeypatch.setattr(worker, "one", claim)


def run_threads(targets):
    errors = {}

    def wrap(name, fn):
        def go():
            try:
                fn()
            except BaseException as exc:  # surfaced to the test below
                errors[name] = exc

        return threading.Thread(target=go, name=name)

    threads = [wrap(name, fn) for name, fn in targets.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(TIMEOUT + 10)
        assert not t.is_alive(), f"{t.name} did not finish"
    return errors


def awaiting_run(journey, monkeypatch, episodes=2):
    """A fixture run whose episodes have captured output and wait at the durable review interrupt."""
    project = journey["project_id"]
    researcher = USERS["researcher"]
    rid = uid()
    with transaction(project, researcher) as c:
        task = one(
            c,
            "SELECT task_revision_id FROM anvil.episodes WHERE id=%s",
            (journey["episodes"][0]["id"],),
        )["task_revision_id"]
        c.execute(
            "INSERT INTO anvil.runs(id,project_id,protocol_revision_id,origin,created_by,state) VALUES(%s,%s,%s,'illustrative',%s,'queued')",
            (rid, project, journey["protocol"]["current_revision_id"], researcher),
        )
        eids = []
        for candidate in CANDIDATES[:episodes]:
            eid = uid()
            c.execute(
                "INSERT INTO anvil.episodes(id,project_id,run_id,task_revision_id,candidate_key,thread_id,graph_version) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (eid, project, rid, task, candidate, uid(), GRAPH_VERSION),
            )
            eids.append(eid)
    for eid in eids:
        with transaction(project, worker=True) as c:
            job = lease(c, project, "episode", eid, "finalization-test-episode")
        tick_as(monkeypatch, {threading.current_thread().name: job})
        assert worker.tick()
        monkeypatch.setattr(worker, "one", REAL_ONE)
    with transaction(project, worker=True) as c:
        states = [
            one(c, "SELECT state,invocation_count FROM anvil.episodes WHERE id=%s", (e,))
            for e in eids
        ]
        assert all(s["state"] == "awaiting_review" and s["invocation_count"] == 1 for s in states)
        assert (
            one(c, "SELECT state FROM anvil.runs WHERE id=%s", (rid,))["state"] == "review_pending"
        )
    return project, rid, eids


def final_review(project, eid):
    """Record a synthetic final assessment directly; review routing is covered elsewhere."""
    reviewer = USERS["reviewer-1"]
    aid = uid()
    with transaction(project, reviewer) as c:
        c.execute(
            "INSERT INTO anvil.assessments(id,project_id,episode_id,reviewer_id,scores,critical,evidence,rationale,score,outcome,round) "
            "VALUES(%s,%s,%s,%s,'{}','[]','{}','Synthetic finalization concurrency test.',80,'pass','independent')",
            (aid, project, eid, reviewer),
        )
        c.execute(
            "UPDATE anvil.episodes SET final_assessment_id=%s,score=80,outcome='pass',row_version=row_version+1 WHERE id=%s",
            (aid, eid),
        )


def resume_job(project, eid):
    with transaction(project, worker=True) as c:
        return lease(c, project, "resume", eid, "finalization-test-resume")


def pause_finalized_audit(monkeypatch, rendezvous):
    original = worker.audit

    def audit(c, project, user, action, target=None, metadata=None):
        if action == "episode.finalized":
            rendezvous.pause(c)
        return original(c, project, user, action, target, metadata)

    monkeypatch.setattr(worker, "audit", audit)


def snapshot(project, rid, eids):
    with transaction(project, worker=True) as c:
        return {
            "run": one(c, "SELECT state FROM anvil.runs WHERE id=%s", (rid,))["state"],
            "episodes": [
                one(c, "SELECT state,invocation_count FROM anvil.episodes WHERE id=%s", (e,))
                for e in eids
            ],
            "audits": {
                e: one(
                    c,
                    "SELECT count(*) n FROM anvil.audit_events WHERE action='episode.finalized' AND target_id=%s",
                    (e,),
                )["n"]
                for e in eids
            },
        }


def job_state(project, job):
    with transaction(project, worker=True) as c:
        return one(c, "SELECT status,error_code FROM anvil.jobs WHERE id=%s", (job["id"],))


def test_last_two_episodes_finalized_concurrently_mark_run_reviewed(monkeypatch, journey):
    project, rid, eids = awaiting_run(journey, monkeypatch)
    for eid in eids:
        final_review(project, eid)
    jobs = {
        "finalizer-a": resume_job(project, eids[0]),
        "finalizer-b": resume_job(project, eids[1]),
    }
    tick_as(monkeypatch, jobs)
    pause_finalized_audit(monkeypatch, Rendezvous(lambda r: len(r.arrived) >= 2))
    errors = run_threads({name: worker.tick for name in jobs})
    assert not errors, errors
    assert all(
        job_state(project, j) == {"status": "succeeded", "error_code": None} for j in jobs.values()
    )
    state = snapshot(project, rid, eids)
    assert [e["state"] for e in state["episodes"]] == ["finalized", "finalized"]
    assert [e["invocation_count"] for e in state["episodes"]] == [1, 1]
    assert state["audits"] == {e: 1 for e in eids}
    assert state["run"] == "reviewed"


def test_finalization_racing_operational_failure_completes_run(monkeypatch, journey):
    project, rid, eids = awaiting_run(journey, monkeypatch)
    final_review(project, eids[0])
    jobs = {
        "finalizer": resume_job(project, eids[0]),
        # No final review: the worker rejects this delivery as an operational failure.
        "failing": resume_job(project, eids[1]),
    }
    meet = Rendezvous(lambda r: len(r.arrived) >= 2)
    # The failure path pauses after deciding whether other episodes remain unfinished.
    tick_as(monkeypatch, jobs, after={REMAINING_AFTER_FAILURE: meet.pause})
    pause_finalized_audit(monkeypatch, meet)
    errors = run_threads({name: worker.tick for name in jobs})
    assert not errors, errors
    assert job_state(project, jobs["finalizer"])["status"] == "succeeded"
    assert job_state(project, jobs["failing"]) == {
        "status": "failed",
        "error_code": "final_review_missing",
    }
    state = snapshot(project, rid, eids)
    assert [e["state"] for e in state["episodes"]] == ["finalized", "failed_operational"]
    assert state["audits"] == {eids[0]: 1, eids[1]: 0}
    assert state["run"] == "execution_complete"


def test_duplicate_resume_delivery_finalizes_once(monkeypatch, journey):
    project, rid, eids = awaiting_run(journey, monkeypatch, episodes=1)
    final_review(project, eids[0])
    jobs = {"first": resume_job(project, eids[0]), "duplicate": resume_job(project, eids[0])}
    tick_as(monkeypatch, jobs)
    pause_finalized_audit(monkeypatch, Rendezvous(lambda r: len(r.arrived) >= 2))
    errors = run_threads({name: worker.tick for name in jobs})
    assert not errors, errors
    assert all(job_state(project, j)["status"] == "succeeded" for j in jobs.values())
    state = snapshot(project, rid, eids)
    assert state["episodes"][0] == {"state": "finalized", "invocation_count": 1}
    assert state["audits"] == {eids[0]: 1}
    assert state["run"] == "reviewed"
    # A later redelivery after completion is a no-op.
    late = resume_job(project, eids[0])
    tick_as(monkeypatch, {threading.current_thread().name: late})
    assert worker.tick()
    assert job_state(project, late)["status"] == "succeeded"
    assert snapshot(project, rid, eids) == state


def test_cancel_racing_last_finalization_does_not_deadlock(monkeypatch, journey, client_factory):  # noqa: F811
    project, rid, eids = awaiting_run(journey, monkeypatch)
    for eid in eids:
        final_review(project, eid)
    finished = resume_job(project, eids[0])
    tick_as(monkeypatch, {threading.current_thread().name: finished})
    assert worker.tick()
    monkeypatch.setattr(worker, "one", REAL_ONE)
    last = resume_job(project, eids[1])
    client, _ = client_factory("researcher")
    with transaction(project, worker=True) as c:
        version = one(c, "SELECT row_version FROM anvil.runs WHERE id=%s", (rid,))["row_version"]

    # Cancel holds the run lock and waits until the finalizer is queued behind it.
    hold = Rendezvous(lambda r: False)
    original_get_run = evaluation.get_run

    def get_run(c, run_id, lock=False):
        row = original_get_run(c, run_id, lock)
        if lock and str(run_id) == rid:
            hold.pause(c)
        return row

    monkeypatch.setattr(evaluation, "get_run", get_run)
    tick_as(monkeypatch, {"finalizer": last})
    response = {}

    def cancel():
        response["r"] = client.post(
            f"/api/v1/projects/{project}/runs/{rid}/cancel", headers={"If-Match": str(version)}
        )

    errors = run_threads({"canceller": cancel, "finalizer": worker.tick})
    assert not errors, errors
    assert response["r"].status_code == 200, response["r"].text
    # Cancel committed first and cancelled the leased job, so the finalizer's lease is gone.
    assert job_state(project, last) == {"status": "failed", "error_code": "lease_lost"}
    state = snapshot(project, rid, eids)
    assert [e["state"] for e in state["episodes"]] == ["finalized", "cancelled"]
    assert state["audits"] == {eids[0]: 1, eids[1]: 0}
    assert state["run"] == "cancelled"


def blocked_count():
    """Test backends waiting on a lock. Later waiters queue behind earlier ones, not the holder."""
    with psycopg.connect(setting("WORKER_DATABASE_URL")) as c:
        return c.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE application_name=current_setting('application_name') AND cardinality(pg_blocking_pids(pid))>0"
        ).fetchone()[0]


def wait_until(predicate):
    deadline = time.monotonic() + TIMEOUT
    while not predicate():
        assert time.monotonic() < deadline, "wait timed out"
        time.sleep(0.01)


def test_cancel_queued_on_project_lock_racing_finalization_does_not_deadlock(
    monkeypatch,
    journey,
    client_factory,  # noqa: F811
):
    """A third transaction (such as sales-kit preparation) holds the project row.

    Cancel queues on the project first, then the last finalizer arrives. When the holder
    commits, both must complete in project -> run order without a deadlock.
    """
    project, rid, eids = awaiting_run(journey, monkeypatch)
    for eid in eids:
        final_review(project, eid)
    finished = resume_job(project, eids[0])
    tick_as(monkeypatch, {threading.current_thread().name: finished})
    assert worker.tick()
    monkeypatch.setattr(worker, "one", REAL_ONE)
    last = resume_job(project, eids[1])
    client, _ = client_factory("researcher")
    with transaction(project, worker=True) as c:
        version = one(c, "SELECT row_version FROM anvil.runs WHERE id=%s", (rid,))["row_version"]
    tick_as(monkeypatch, {"finalizer": last})
    response, errors = {}, {}

    def cancel():
        try:
            response["r"] = client.post(
                f"/api/v1/projects/{project}/runs/{rid}/cancel", headers={"If-Match": str(version)}
            )
        except BaseException as exc:
            errors["canceller"] = exc

    def finalize():
        try:
            worker.tick()
        except BaseException as exc:
            errors["finalizer"] = exc

    canceller = threading.Thread(target=cancel, name="canceller")
    finalizer = threading.Thread(target=finalize, name="finalizer")
    with transaction(project, worker=True) as holder:
        holder.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
        canceller.start()
        wait_until(lambda: blocked_count() >= 1)
        finalizer.start()
        wait_until(lambda: blocked_count() >= 2)
    for t in (canceller, finalizer):
        t.join(TIMEOUT + 10)
        assert not t.is_alive(), f"{t.name} did not finish"
    assert not errors, errors
    assert response["r"].status_code == 200, response["r"].text
    assert job_state(project, last) == {"status": "failed", "error_code": "lease_lost"}
    state = snapshot(project, rid, eids)
    assert [e["state"] for e in state["episodes"]] == ["finalized", "cancelled"]
    assert state["audits"] == {eids[0]: 1, eids[1]: 0}
    assert state["run"] == "cancelled"
