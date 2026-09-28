"""Finite fixture graph; PostgreSQL queue, fencing and durable review interrupts."""

import json
import signal
import time
from typing import TypedDict

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg.rows import dict_row

from anvil import artifacts, domain
from anvil.config import ROOT, setting
from anvil.db import audit, one, transaction
from anvil.evaluation import GRAPH_VERSION

STOP = False


class State(TypedDict):
    episode_id: str
    project_id: str
    graph_version: str
    output_artifact_id: str | None


def guard(c, job):
    if not one(
        c,
        "SELECT 1 FROM anvil.jobs WHERE id=%s AND status='leased' AND lease_token=%s AND lease_until>now() FOR UPDATE",
        (job["id"], job["lease_token"]),
    ):
        raise RuntimeError("lease_lost")
    e = one(
        c,
        "SELECT e.*,r.cancel_requested FROM anvil.episodes e JOIN anvil.runs r ON r.id=e.run_id WHERE e.id=%s FOR UPDATE OF e",
        (job["target_id"],),
    )
    if not e or e["cancel_requested"] or e["state"] == "cancelled":
        raise RuntimeError("cancelled")
    if e["graph_version"] != GRAPH_VERSION:
        raise RuntimeError("graph_version_mismatch")
    task = domain.get_revision(c, e["task_revision_id"], "task", ["published"])
    rubric = one(
        c,
        "SELECT 1 FROM anvil.resources WHERE current_revision_id=%s AND kind='rubric' AND lifecycle='approved'",
        (task["content"]["rubric_revision_id"],),
    )
    if not rubric:
        raise RuntimeError("rubric_no_longer_qualified")
    return e


def graph_for(job, saver):
    project = job["project_id"]

    def validate(state):
        with transaction(project, worker=True) as c:
            e = guard(c, job)
            task = domain.get_revision(c, e["task_revision_id"], "task", ["published"])["content"]
            if task["mode"] != "static" or not domain.rights_ok(c, task["source_revision_id"]):
                raise RuntimeError("rights_or_mode_blocked")
            if state["graph_version"] != GRAPH_VERSION:
                raise RuntimeError("graph_version_mismatch")
        return {}

    def invoke(state):
        with transaction(project, worker=True) as c:
            e = guard(c, job)
            if e["output_artifact_id"]:
                return {"output_artifact_id": str(e["output_artifact_id"])}
            task = domain.get_revision(c, e["task_revision_id"], "task", ["published"])["content"]
            if not domain.rights_ok(c, task["source_revision_id"]):
                raise RuntimeError("rights_revoked")
            # Separate, actor-only resolver. Neither references nor expected scores are read here.
            actor = [artifacts.read(c, aid, actor_only=True) for aid in task["actor_artifact_ids"]]
            if not actor or any(not x for x in actor):
                raise RuntimeError("missing_actor_input")
            responses = json.loads(
                (ROOT / "fixtures/candidate-outputs/responses.json").read_text()
            )["responses"]
            matches = [
                r
                for r in responses
                if r["candidate"] == e["candidate_key"] and r["case_id"] == task["external_case_id"]
            ]
            if len(matches) != 1:
                raise RuntimeError("unregistered_fixture_candidate")
            output = json.dumps(matches[0]["output"], ensure_ascii=False, indent=2).encode()
            aid = artifacts.store(c, project, output, "internal")
            c.execute(
                "UPDATE anvil.episodes SET output_artifact_id=%s,invocation_count=invocation_count+1,state='output_captured',row_version=row_version+1 WHERE id=%s",
                (aid, e["id"]),
            )
            c.execute("UPDATE anvil.runs SET state='running' WHERE id=%s", (e["run_id"],))
            audit(c, project, None, "fixture.output_captured", e["id"], {"origin": "illustrative"})
            if (
                one(
                    c,
                    "SELECT count(*) n FROM anvil.episodes WHERE run_id=%s AND output_artifact_id IS NULL",
                    (e["run_id"],),
                )["n"]
                == 0
            ):
                from anvil.evaluation import enqueue

                enqueue(
                    c,
                    project,
                    "sales_kit_prepare",
                    e["run_id"],
                    "provisional-kit:" + str(e["run_id"]),
                )
            return {"output_artifact_id": aid}

    def await_review(state):
        with transaction(project, worker=True) as c:
            e = guard(c, job)
            if not e["final_assessment_id"]:
                c.execute(
                    "UPDATE anvil.episodes SET state='awaiting_review' WHERE id=%s", (e["id"],)
                )
                c.execute(
                    "UPDATE anvil.runs SET state='review_pending' WHERE id=%s", (e["run_id"],)
                )
        interrupt({"episode_id": state["episode_id"], "pending": "independent_human_review"})
        with transaction(project, worker=True) as c:
            e = guard(c, job)
            if not e["final_assessment_id"]:
                raise RuntimeError("final_review_missing")
        return {}

    def finalize(state):
        with transaction(project, worker=True) as c:
            e = guard(c, job)
            if not e["final_assessment_id"]:
                raise RuntimeError("final_review_missing")
            c.execute(
                "UPDATE anvil.episodes SET state='finalized',row_version=row_version+1 WHERE id=%s AND state<>'finalized'",
                (e["id"],),
            )
            pending = one(
                c,
                "SELECT count(*) n FROM anvil.episodes WHERE run_id=%s AND state NOT IN ('finalized','failed_operational','execution_unknown','cancelled')",
                (e["run_id"],),
            )["n"]
            if pending == 0:
                c.execute(
                    "UPDATE anvil.runs SET state=CASE WHEN EXISTS(SELECT 1 FROM anvil.episodes WHERE run_id=%s AND state<>'finalized') THEN 'execution_complete' ELSE 'reviewed' END,row_version=row_version+1 WHERE id=%s AND NOT cancel_requested",
                    (e["run_id"], e["run_id"]),
                )
            audit(c, project, None, "episode.finalized", e["id"])
        return {}

    g = StateGraph(State)
    g.add_node("validate_authorization", validate)
    g.add_node("invoke_fixture_capture_output", invoke)
    g.add_node("await_human_review", await_review)
    g.add_node("finalize_assessment", finalize)
    g.add_edge(START, "validate_authorization")
    g.add_edge("validate_authorization", "invoke_fixture_capture_output")
    g.add_edge("invoke_fixture_capture_output", "await_human_review")
    g.add_edge("await_human_review", "finalize_assessment")
    g.add_edge("finalize_assessment", END)
    return g.compile(checkpointer=saver)


def tick():
    with transaction(worker=True) as c:
        job = one(c, "SELECT * FROM anvil.claim_job()")
    if not job:
        return False
    project = job["project_id"]
    try:
        if job["kind"] in ("sales_kit_prepare", "sales_kit_render", "fixture_mail"):
            from anvil.reports import prepare_provisional, render_kit

            with transaction(project, worker=True) as c:
                if not one(
                    c,
                    "SELECT 1 FROM anvil.jobs WHERE id=%s AND lease_token=%s AND lease_until>now() AND status='leased' FOR UPDATE",
                    (job["id"], job["lease_token"]),
                ):
                    raise RuntimeError("lease_lost")
                if job["kind"] == "fixture_mail":
                    from anvil.delivery import dispatch_fixture

                    dispatch_fixture(c, job)
                elif job["kind"] == "sales_kit_prepare":
                    prepare_provisional(c, job["target_id"])
                else:
                    report = domain.get_resource(c, job["target_id"])
                    render_kit(c, report, report["created_by"])
                c.execute(
                    "UPDATE anvil.jobs SET status='succeeded' WHERE id=%s AND lease_token=%s AND lease_until>now()",
                    (job["id"], job["lease_token"]),
                )
            return True
        with transaction(project, worker=True) as c:
            e = guard(c, job)
        with psycopg.connect(
            setting("WORKER_DATABASE_URL"),
            autocommit=True,
            row_factory=dict_row,
            options="-c search_path=anvil_checkpoints",
        ) as conn:
            saver = PostgresSaver(conn, serde=JsonPlusSerializer(pickle_fallback=False))
            graph = graph_for(job, saver)
            config = {"configurable": {"thread_id": str(e["thread_id"])}, "recursion_limit": 20}
            if job["kind"] == "resume":
                if not e["final_assessment_id"]:
                    raise RuntimeError("final_review_missing")
                snapshot = graph.get_state(config)
                if not snapshot.next and e["state"] == "finalized":
                    pass
                elif not snapshot.interrupts:
                    raise RuntimeError("pending_interrupt_missing")
                else:
                    graph.invoke(
                        Command(resume={"final_assessment_id": str(e["final_assessment_id"])}),
                        config,
                    )
            elif job["kind"] == "episode":
                snapshot = graph.get_state(config)
                if snapshot.interrupts:
                    pass  # crash after durable interrupt: never restart the candidate
                else:
                    state = {
                        "episode_id": str(e["id"]),
                        "project_id": str(project),
                        "graph_version": GRAPH_VERSION,
                        "output_artifact_id": None,
                    }
                    graph.invoke(None if snapshot.values else state, config)
            else:
                raise RuntimeError("unknown_job_kind")
        with transaction(project, worker=True) as c:
            c.execute(
                "UPDATE anvil.jobs SET status='succeeded' WHERE id=%s AND lease_token=%s AND lease_until>now()",
                (job["id"], job["lease_token"]),
            )
    except Exception as exc:
        # Codes only. Never print raw data, credentials, SQL or exception messages.
        code = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        if code not in {
            "lease_lost",
            "cancelled",
            "graph_version_mismatch",
            "rights_or_mode_blocked",
            "rights_revoked",
            "final_review_missing",
            "pending_interrupt_missing",
        }:
            code = type(exc).__name__
        with transaction(project, worker=True) as c:
            failed = c.execute(
                "UPDATE anvil.jobs SET status='failed',error_code=%s WHERE id=%s AND lease_token=%s AND lease_until>now() RETURNING id",
                (code, job["id"], job["lease_token"]),
            ).fetchone()
            if failed and job["kind"] in ("episode", "resume"):
                episode = c.execute(
                    "UPDATE anvil.episodes SET state='failed_operational',outcome='invalid',score=NULL,row_version=row_version+1 WHERE id=%s AND state NOT IN ('cancelled','finalized') RETURNING run_id",
                    (job["target_id"],),
                ).fetchone()
                if episode:
                    remaining = one(
                        c,
                        "SELECT 1 FROM anvil.episodes WHERE run_id=%s AND state NOT IN ('failed_operational','execution_unknown','cancelled','finalized') LIMIT 1",
                        (episode["run_id"],),
                    )
                    if not remaining:
                        c.execute(
                            "UPDATE anvil.runs SET state='execution_complete',row_version=row_version+1 WHERE id=%s AND NOT cancel_requested",
                            (episode["run_id"],),
                        )
                    outputs_pending = one(
                        c,
                        "SELECT 1 FROM anvil.episodes WHERE run_id=%s AND output_artifact_id IS NULL AND state NOT IN ('failed_operational','execution_unknown','cancelled','finalized') LIMIT 1",
                        (episode["run_id"],),
                    )
                    if not outputs_pending:
                        from anvil.evaluation import enqueue

                        enqueue(
                            c,
                            project,
                            "sales_kit_prepare",
                            episode["run_id"],
                            "provisional-kit:" + str(episode["run_id"]),
                        )
        print(f"job={job['id']} status=failed code={code}", flush=True)
    return True


def main():
    def stop(*_):
        global STOP
        STOP = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print("Anvil fixture worker ready; live dispatch disabled", flush=True)
    while not STOP:
        if not tick():
            from anvil.graph import project_pending

            project_pending()
            time.sleep(0.5)


if __name__ == "__main__":
    main()
