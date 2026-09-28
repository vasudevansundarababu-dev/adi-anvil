"""Thirteen-response marketing episode. PostgreSQL is authoritative at every boundary."""

import hashlib
import json
from dataclasses import asdict
from typing import TypedDict

import psycopg
from fastapi import HTTPException
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from anvil import artifacts, budget, marketing_env, providers
from anvil.config import ROOT, setting
from anvil.db import audit, digest, one, transaction, uid
from anvil.evaluation import enqueue
from anvil.marketing_authority import (
    AUTHORITY,
    CALL_BOUND,
    CAP,
    GRAPH_VERSION,
    PRICE_EXPIRES,
    RUN_BOUND,
    binding,
    require_ready,
)


class GraphState(TypedDict):
    episode_id: str
    continuing: bool


def code_digest():
    return digest(
        {
            name: hashlib.sha256(
                (ROOT / "services/backend/src/anvil" / name).read_bytes()
            ).hexdigest()
            for name in (
                "marketing_runtime.py",
                "marketing_env.py",
                "marketing_authority.py",
                "providers.py",
            )
        }
    )


LOADED_DIGEST = code_digest()


def harness_digest():
    if code_digest() != LOADED_DIGEST:
        raise HTTPException(409, "Harness code changed; restart and review the new execution scope")
    return LOADED_DIGEST


def parse_response(text, state):
    """Strict data only. No evaluation, code execution, JSON repair or inferred actions."""

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError("nonfinite_json")

    if not isinstance(text, str) or len(text.encode()) > 60000:
        raise ValueError("response_size")
    try:
        obj = json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)
        json.dumps(obj, ensure_ascii=False).encode("utf-8")
    except (ValueError, RecursionError) as exc:
        raise ValueError("response_json") from exc
    if not isinstance(obj, dict):
        raise ValueError("response_object")

    def prose(value, maximum):
        return isinstance(value, str) and 1 <= len(value.strip()) <= maximum and "\x00" not in value

    week = state["week"]
    if week == 13:
        if set(obj) != {"board_memo", "ledger"} or not prose(obj["board_memo"], 16000):
            raise ValueError("final_deliverables")
        if not isinstance(obj["ledger"], list) or len(obj["ledger"]) != 12:
            raise ValueError("twelve_row_ledger_required")
        if any(
            not isinstance(row, dict) or type(row.get("week")) is not int or row["week"] != i
            for i, row in enumerate(obj["ledger"], 1)
        ):
            raise ValueError("ledger_weeks")
        fields = {
            "week",
            "creative_cost_usd",
            "leads",
            "accepted_qualified_leads",
            "new_customers",
            "cumulative_customers",
            "remaining_budget_usd",
            "pending_qualified_leads",
        }
        for row in obj["ledger"]:
            if set(row) != fields | {"spend_usd"} or any(
                type(row.get(k)) is not int or row[k] < 0 for k in fields
            ):
                raise ValueError("ledger_fields")
            spend = row["spend_usd"]
            if (
                not isinstance(spend, dict)
                or set(spend) != set(marketing_env.CHANNELS)
                or any(type(v) is not int or v < 0 for v in spend.values())
            ):
                raise ValueError("ledger_spend")
        # Arithmetic and qualitative claims remain reviewable, not silently corrected.
        return obj, state
    if set(obj) != {"action", "strategy", "creative", "decision_log"}:
        raise ValueError("weekly_envelope")
    if not prose(obj["decision_log"], 4000):
        raise ValueError("decision_log")
    if (week == 1 and not prose(obj["strategy"], 8000)) or (
        week != 1 and obj["strategy"] is not None
    ):
        raise ValueError("strategy")
    creative = obj["creative"]
    if week in (1, 5, 9):
        if (
            not isinstance(creative, dict)
            or set(creative) != {"headlines", "landing_page"}
            or not isinstance(creative["headlines"], list)
            or len(creative["headlines"]) != 3
            or any(not prose(h, 200) for h in creative["headlines"])
            or not prose(creative["landing_page"], 2000)
        ):
            raise ValueError("creative")
    elif creative is not None:
        raise ValueError("creative_not_due")
    return obj, marketing_env.step(state, obj["action"])


def prompt(c, task, session):
    inputs = [
        artifacts.read(c, aid, actor_only=True).decode("utf-8")
        for aid in task["actor_artifact_ids"]
    ]
    history = c.execute(
        "SELECT step,result FROM anvil.interactive_calls WHERE episode_id=%s AND status='applied' ORDER BY step",
        (session["episode_id"],),
    ).fetchall()
    deliverables = [json.loads(row["result"]["text"]) for row in history]
    context = {
        "observation": marketing_env.observe(session["state"]),
        "receipts": session["state"]["history"],
        "initial_strategy": deliverables[0]["strategy"] if deliverables else None,
        "last_decision_log": deliverables[-1]["decision_log"] if deliverables else None,
        "creative_so_far": [d["creative"] for d in deliverables if d["creative"]],
    }
    contract = (
        'Return only a JSON object with keys "board_memo" (string, at most 16000 characters) and "ledger" (12 objects). Each row must have exactly these keys: week, spend_usd (an object with search/social/webinar/email whole-dollar amounts), creative_cost_usd, leads, accepted_qualified_leads, new_customers, cumulative_customers, remaining_budget_usd, pending_qualified_leads. All numeric fields must be nonnegative integers; week runs from 1 through 12. Reconcile against the observed receipts.'
        if session["step"] == 13
        else 'Return only a JSON object with exactly these keys: "action" (the exact weekly action object specified in the assignment), "strategy" (a string of at most 8000 characters in week 1, otherwise null), "creative" (an object with "headlines": three strings of at most 200 characters and "landing_page": a string of at most 2000 characters in weeks 1, 5, 9; otherwise null), "decision_log" (a concise string of at most 4000 characters).'
    )
    text = (
        "\n\n".join(inputs)
        + "\n\nCURRENT OBSERVABLE CONTEXT\n"
        + json.dumps(context, ensure_ascii=False)
        + "\n\n"
        + contract
    )
    if len(text.encode()) > 100000:
        raise HTTPException(409, "Actor context exceeds the frozen 100000-byte bound")
    return text


def launch(c, run):
    require_ready(c, run)
    protocol, task, _ = binding(c, run)
    window = one(
        c,
        "SELECT * FROM anvil.evaluation_spend_windows WHERE authority_reference=%s FOR UPDATE",
        (AUTHORITY,),
    )
    if not window:
        wid = uid()
        # Global unique authority prevents another project from resetting this user's ceiling.
        c.execute(
            "INSERT INTO anvil.evaluation_spend_windows(id,project_id,cap_micro_usd,end_at,status,authority_reference) VALUES(%s,%s,%s,%s,'active',%s)",
            (wid, run["project_id"], CAP, PRICE_EXPIRES, AUTHORITY),
        )
        window = {"id": wid}
    c.execute(
        "INSERT INTO anvil.run_budgets(project_id,run_id,window_id,cap_micro_usd) VALUES(%s,%s,%s,%s)",
        (run["project_id"], run["id"], window["id"], RUN_BOUND),
    )
    eid = uid()
    c.execute(
        "INSERT INTO anvil.episodes(id,project_id,run_id,task_revision_id,candidate_key,thread_id,graph_version) VALUES(%s,%s,%s,%s,'openai-marketing',%s,%s)",
        (eid, run["project_id"], run["id"], task["id"], uid(), GRAPH_VERSION),
    )
    c.execute(
        "INSERT INTO anvil.interactive_sessions(project_id,episode_id,environment_version,harness_version,state) VALUES(%s,%s,'MKT-LH-001/1.0',%s,%s)",
        (
            run["project_id"],
            eid,
            GRAPH_VERSION,
            Jsonb({**marketing_env.reset(), "_harness_sha256": harness_digest()}),
        ),
    )
    c.execute(
        "UPDATE anvil.runs SET state='queued',cost_status='reserved_or_unknown',row_version=row_version+1 WHERE id=%s",
        (run["id"],),
    )
    enqueue(c, run["project_id"], "marketing_episode", eid, "marketing:" + eid)
    audit(
        c,
        run["project_id"],
        run["created_by"],
        "marketing.run_launched",
        run["id"],
        {"max_responses": 13, "model": "gpt-6-sol"},
    )


def locked(c, job, *, allow_cancel=False):
    # Match API lock order; long external calls hold no database lock.
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (job["project_id"],))
    if not one(
        c,
        "UPDATE anvil.jobs SET lease_until=now()+interval '15 minutes' WHERE id=%s AND status='leased' AND lease_token=%s AND lease_until>now() RETURNING id",
        (job["id"], job["lease_token"]),
    ):
        raise RuntimeError("lease_lost")
    episode = one(c, "SELECT * FROM anvil.episodes WHERE id=%s FOR UPDATE", (job["target_id"],))
    if not episode or episode["graph_version"] != GRAPH_VERSION:
        raise RuntimeError("graph_version_mismatch")
    run = one(c, "SELECT * FROM anvil.runs WHERE id=%s FOR UPDATE", (episode["run_id"],))
    if run["cancel_requested"] and not allow_cancel:
        raise RuntimeError("cancelled")
    session = one(
        c,
        "SELECT * FROM anvil.interactive_sessions WHERE episode_id=%s FOR UPDATE",
        (episode["id"],),
    )
    if not session or session["state"].get("_harness_sha256") != harness_digest():
        raise RuntimeError("graph_version_mismatch")
    return episode, run, session


def stop_unknown(c, episode, run, step):
    c.execute(
        "UPDATE anvil.interactive_calls SET status='execution_unknown',error_code='ambiguous_dispatch',finished_at=now() WHERE episode_id=%s AND step=%s AND status='dispatching'",
        (episode["id"], step),
    )
    c.execute(
        "UPDATE anvil.episodes SET state='execution_unknown',outcome='invalid',row_version=row_version+1 WHERE id=%s",
        (episode["id"],),
    )
    c.execute(
        "UPDATE anvil.runs SET state='reconciliation_required',row_version=row_version+1 WHERE id=%s",
        (run["id"],),
    )
    audit(c, run["project_id"], None, "marketing.dispatch_unknown", episode["id"], {"step": step})


def capture_output(c, episode, run):
    if episode["output_artifact_id"]:
        return
    rows = c.execute(
        "SELECT step,status,jsonb_build_object('status',result->'status','text',result->'text') result,receipt,error_code,request_sha256,state_before_sha256,state_after_sha256,started_at,finished_at FROM anvil.interactive_calls WHERE episode_id=%s ORDER BY step",
        (episode["id"],),
    ).fetchall()
    output = json.dumps(
        {
            "origin": "adi_executed",
            "source_origin": "original_synthetic",
            "task": "MKT-LH-001/1.0",
            "completed_weekly_actions": sum(
                r["step"] <= 12 and r["status"] == "applied" for r in rows
            ),
            "responses": rows,
            "limitations": "Simplified deterministic simulation, development task; costs are conservative reservations, not verified billing.",
        },
        default=str,
        ensure_ascii=False,
    ).encode()
    aid = artifacts.store(c, run["project_id"], output, "internal", origin="adi_executed")
    c.execute(
        "UPDATE anvil.episodes SET output_artifact_id=%s,state='output_captured',invocation_count=1,row_version=row_version+1 WHERE id=%s",
        (aid, episode["id"]),
    )


def advance(job):
    project = job["project_id"]
    dispatch = None
    with transaction(project, worker=True) as c:
        episode, run, session = locked(c, job)
        if episode["state"] in ("execution_unknown", "failed_operational"):
            return False
        if episode["output_artifact_id"] or session["step"] == 14:
            return False
        step = session["step"]
        call = one(
            c,
            "SELECT * FROM anvil.interactive_calls WHERE episode_id=%s AND step=%s",
            (episode["id"], step),
        )
        if call and call["status"] == "dispatching":
            # Crash after committed intent, including before send: conservatively unknown.
            stop_unknown(c, episode, run, step)
            return False
        if call and call["status"] in ("rejected", "execution_unknown"):
            return False
        protocol, task, _ = binding(c, run)
        if not call:
            require_ready(c, run)
            text = prompt(c, task["content"], session)
            rb = one(c, "SELECT * FROM anvil.run_budgets WHERE run_id=%s", (run["id"],))
            operation = f"marketing:{episode['id']}:{step}"
            reservation = budget.reserve(
                c, project, rb["window_id"], run["id"], CALL_BOUND, operation
            )
            c.execute(
                "INSERT INTO anvil.interactive_calls(project_id,episode_id,step,operation_key,reservation_id,request_text,request_sha256,state_before_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    project,
                    episode["id"],
                    step,
                    operation,
                    reservation["id"],
                    text,
                    digest(text),
                    digest(session["state"]),
                ),
            )
            c.execute(
                "UPDATE anvil.episodes SET state='running',invocation_count=1,row_version=row_version+1 WHERE id=%s",
                (episode["id"],),
            )
            c.execute(
                "UPDATE anvil.runs SET state='running',row_version=row_version+1 WHERE id=%s",
                (run["id"],),
            )
            audit(
                c,
                project,
                None,
                "marketing.dispatch_intent",
                episode["id"],
                {"step": step, "request_sha256": digest(text), "reserved_micro_usd": CALL_BOUND},
            )
            dispatch = providers.ActorRequest(
                model="gpt-6-sol", actor_text=text, max_output_tokens=8192, timeout_seconds=600
            )
    if dispatch:
        result = providers.execute_marketing(dispatch)
        with transaction(project, worker=True) as c:
            episode, run, session = locked(c, job, allow_cancel=True)
            c.execute(
                "UPDATE anvil.interactive_calls SET result=%s,status='captured',finished_at=now() WHERE episode_id=%s AND step=%s AND status='dispatching'",
                (Jsonb(asdict(result)), episode["id"], step),
            )
            # Usage is preserved as reported. Billing remains unknown; retain the reservation.
            if run["cancel_requested"]:
                return False
    with transaction(project, worker=True) as c:
        episode, run, session = locked(c, job)
        call = one(
            c,
            "SELECT * FROM anvil.interactive_calls WHERE episode_id=%s AND step=%s FOR UPDATE",
            (episode["id"], session["step"]),
        )
        if not call or call["status"] != "captured":
            raise RuntimeError("interactive_capture_missing")
        result = call["result"]
        if result["status"] == "execution_unknown":
            c.execute(
                "UPDATE anvil.interactive_calls SET status='execution_unknown',error_code='ambiguous_dispatch' WHERE episode_id=%s AND step=%s",
                (episode["id"], session["step"]),
            )
            c.execute(
                "UPDATE anvil.episodes SET state='execution_unknown',outcome='invalid',row_version=row_version+1 WHERE id=%s",
                (episode["id"],),
            )
            c.execute(
                "UPDATE anvil.runs SET state='reconciliation_required',row_version=row_version+1 WHERE id=%s",
                (run["id"],),
            )
            return False
        if result["status"] == "failed_operational":
            c.execute(
                "UPDATE anvil.interactive_calls SET status='rejected',error_code='provider_operational_failure' WHERE episode_id=%s AND step=%s",
                (episode["id"], session["step"]),
            )
            c.execute(
                "UPDATE anvil.episodes SET state='failed_operational',outcome='invalid',row_version=row_version+1 WHERE id=%s",
                (episode["id"],),
            )
            c.execute(
                "UPDATE anvil.runs SET state='execution_complete',row_version=row_version+1 WHERE id=%s",
                (run["id"],),
            )
            return False
        try:
            if result["status"] != "completed":
                raise ValueError("refused_or_truncated")
            _, after = parse_response(result["text"], session["state"])
        except (ValueError, TypeError, UnicodeError):
            c.execute(
                "UPDATE anvil.interactive_calls SET status='rejected',error_code='invalid_candidate_deliverable' WHERE episode_id=%s AND step=%s",
                (episode["id"], session["step"]),
            )
            capture_output(c, episode, run)
            return False
        receipt = marketing_env.observe(after)
        c.execute(
            "UPDATE anvil.interactive_calls SET status='applied',state_after_sha256=%s,receipt=%s WHERE episode_id=%s AND step=%s",
            (digest(after), Jsonb(receipt), episode["id"], session["step"]),
        )
        c.execute(
            "UPDATE anvil.interactive_sessions SET state=%s,step=step+1 WHERE episode_id=%s",
            (Jsonb(after), episode["id"]),
        )
        audit(
            c,
            project,
            None,
            "marketing.step_applied",
            episode["id"],
            {"step": session["step"], "state_sha256": digest(after)},
        )
        if session["step"] == 13:
            capture_output(c, episode, run)
            return False
        return True


def graph_for(job, saver):
    def advance_node(_):
        return {"continuing": advance(job)}

    def review_node(_):
        with transaction(job["project_id"], worker=True) as c:
            episode, run, _ = locked(c, job)
            if not episode["output_artifact_id"]:
                return {}
            c.execute(
                "UPDATE anvil.episodes SET state='awaiting_review' WHERE id=%s AND state='output_captured'",
                (episode["id"],),
            )
            c.execute("UPDATE anvil.runs SET state='review_pending' WHERE id=%s", (run["id"],))
        interrupt({"pending": "independent_human_review"})
        return {}

    def finalize_node(_):
        with transaction(job["project_id"], worker=True) as c:
            episode, run, _ = locked(c, job)
            if not episode["output_artifact_id"]:
                return {}
            binding(c, run)
            if not episode["final_assessment_id"] and not episode["invalidity_resolution_id"]:
                raise RuntimeError("final_review_missing")
            c.execute(
                "UPDATE anvil.episodes SET state='finalized',row_version=row_version+1 WHERE id=%s AND state<>'finalized'",
                (episode["id"],),
            )
            c.execute(
                "UPDATE anvil.runs SET state='reviewed',row_version=row_version+1 WHERE id=%s",
                (run["id"],),
            )
            audit(c, job["project_id"], None, "episode.finalized", episode["id"])
        return {}

    graph = StateGraph(GraphState)
    graph.add_node("advance", advance_node)
    graph.add_node("await_human_review", review_node)
    graph.add_node("finalize_assessment", finalize_node)
    graph.add_edge(START, "advance")
    graph.add_conditional_edges(
        "advance", lambda s: "advance" if s["continuing"] else "await_human_review"
    )
    graph.add_edge("await_human_review", "finalize_assessment")
    graph.add_edge("finalize_assessment", END)
    return graph.compile(checkpointer=saver)


def process(job):
    with transaction(job["project_id"], worker=True) as c:
        episode, _, _ = locked(c, job)
    with psycopg.connect(
        setting("WORKER_DATABASE_URL"),
        autocommit=True,
        row_factory=dict_row,
        options="-c search_path=anvil_checkpoints",
    ) as conn:
        graph = graph_for(job, PostgresSaver(conn, serde=JsonPlusSerializer(pickle_fallback=False)))
        config = {"configurable": {"thread_id": str(episode["thread_id"])}, "recursion_limit": 40}
        snapshot = graph.get_state(config)
        if job["kind"] == "resume":
            if not episode["final_assessment_id"] and not episode["invalidity_resolution_id"]:
                raise RuntimeError("final_review_missing")
            if snapshot.interrupts:
                graph.invoke(Command(resume={"reviewed": True}), config)
            elif episode["state"] != "finalized":
                raise RuntimeError("pending_interrupt_missing")
        elif not snapshot.interrupts:
            graph.invoke(
                None if snapshot.values else {"episode_id": str(episode["id"]), "continuing": True},
                config,
            )
    with transaction(job["project_id"], worker=True) as c:
        c.execute(
            "UPDATE anvil.jobs SET status='succeeded' WHERE id=%s AND lease_token=%s AND lease_until>now()",
            (job["id"], job["lease_token"]),
        )
