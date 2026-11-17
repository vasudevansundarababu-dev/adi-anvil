"""Actual PostgreSQL claims/checkpoints; manufactured effects, no SDK requests."""

import json
from pathlib import Path

import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from test_golden_kyc_anvil_sql import scoped
from test_golden_kyc_sql import connection
from test_golden_kyc_sql import owned as owned_fixture

from anvil import marketing_task2_store
from anvil.db import digest
from anvil.marketing_task2_runtime import Task2Controller
from anvil.marketing_task2_workflow import compile_graph, initial
from anvil.marketing_task2_workflow_store import Journal

owned = owned_fixture


def contract():
    return json.loads(
        (Path(__file__).parents[1] / "fixtures/veyra-template-execution-v3.json").read_text()
    )


def create(owned):
    controller = Task2Controller(
        "GT2-R01",
        records={},
        start="2027-01-06T00:00:00Z",
        outcome="positive",
        budget_minor=20000000,
    )
    with scoped(owned, "scheduler")() as c:
        result = marketing_task2_store.create(
            c,
            owned[1],
            owned[2],
            {"id": "software-US-pair", "version": "fixture-1", "sha256": "a" * 64, "case_count": 2},
            "b" * 64,
            controller,
        )
    return result["trial_id"]


def test_effect_commit_survives_checkpoint_replay_but_uncertain_claim_never_replays(owned):
    identifier = create(owned)
    calls = []

    def adapter(node, inputs, week, visit):
        calls.append(node["id"])
        return {
            "artifact": {"assignment": "software control"},
            "receipt": {"input_sha256": digest(inputs)},
        }

    execution = contract()
    journal = Journal(
        scoped(owned, "scheduler"), owned[1], owned[2], identifier, 0, execution, adapter
    )
    node = next(node for node in execution["workflow_graph"]["nodes"] if node["id"] == "intake")
    inputs = {"campaign_context": {}, "released_evidence": {"week": 1}}
    result = journal(node, inputs, 1, 1)
    assert journal(node, inputs, 1, 1) == result and calls == ["intake"]
    with pytest.raises(RuntimeError, match="inputs changed"):
        journal(node, inputs | {"released_evidence": {"week": 2}}, 1, 1)

    def ambiguous(*args):
        calls.append("ambiguous")
        raise TimeoutError("Manufactured post-dispatch uncertainty")

    journal.adapter = ambiguous
    with pytest.raises(TimeoutError):
        journal(node, inputs, 1, 2)
    with pytest.raises(RuntimeError, match="no replay"):
        journal(node, inputs, 1, 2)
    assert calls == ["intake", "ambiguous"]
    with scoped(owned, "grader")() as c:
        rows = c.execute(
            "SELECT state FROM marketing_runtime.workflow_effects WHERE episode_id=%s ORDER BY visit",
            (identifier,),
        ).fetchall()
        assert [row["state"] for row in rows] == ["completed", "execution_unknown"]
    with scoped(owned, "scheduler")() as c:
        with pytest.raises(Exception, match="cannot be replayed"):
            c.execute(
                "UPDATE marketing_runtime.workflow_effects SET state='claimed' WHERE episode_id=%s AND visit=2",
                (identifier,),
            )


def test_actual_postgres_langgraph_checkpoints_twelve_windows_without_extra_effects(owned):
    def candidate(node, inputs, week, visit):
        artifacts = {
            "campaign_plan": {"action": "creative" if week == 1 else "hold"},
            "campaign_findings": {"outcome": "clear"},
            "approval_status": {"decision": "approved"},
            "weekly_review": {"campaign_complete": week == 12},
        }
        return {
            "artifact": artifacts.get(
                node.get("outputArtifact"), {"origin": "manufactured_software_control"}
            ),
            "receipt": {"input_sha256": digest(inputs), "origin": "manufactured_software_control"},
            "port": "responded" if node["type"] == "human_step" else None,
        }

    identifier = create(owned)
    execution = contract()
    journal = Journal(
        scoped(owned, "scheduler"), owned[1], owned[2], identifier, 0, execution, candidate
    )
    # Dedicated migration-owner connection to the fresh test database, never
    # actor-accessible checkpoint credentials or a shared deployed database.
    with connection(owned) as c:
        c.execute("SET search_path TO anvil_checkpoints")
        saver = PostgresSaver(c, serde=JsonPlusSerializer(pickle_fallback=False))
        graph = compile_graph(execution, journal, lambda week: {"week": week}, saver)
        config = {"configurable": {"thread_id": identifier}, "recursion_limit": 410}
        result = graph.invoke(
            initial({"origin": "manufactured_software_control"}, {"week": 1}), config
        )
        assert result["terminal"] == "done" and result["week"] == 12
        assert graph.get_state(config).values == result
    with scoped(owned, "grader")() as c:
        rows = c.execute(
            "SELECT node_id,state FROM marketing_runtime.workflow_effects WHERE episode_id=%s",
            (identifier,),
        ).fetchall()
        assert rows and all(row["state"] == "completed" for row in rows)
        assert {"brief_step", "policy_step", "intent_step", "performance_step"} <= {
            row["node_id"] for row in rows
        }


def test_guard_limits_privileges_assignment_generation_project_and_live_membership(owned):
    identifier = create(owned)
    with connection(owned) as c:
        assert not c.execute(
            "SELECT has_table_privilege('anvil_golden_scheduler','anvil.memberships','UPDATE') AS allowed"
        ).fetchone()["allowed"]
        for role in ("anvil_app", "anvil_worker", "anvil_golden_grader"):
            assert not c.execute(
                "SELECT has_function_privilege(%s,'marketing_runtime.execution_guard(uuid,uuid,integer)','EXECUTE') AS allowed",
                (role,),
            ).fetchone()["allowed"]

    def guard(user, generation):
        with scoped(owned, "scheduler")() as c:
            return c.execute(
                "SELECT marketing_runtime.execution_guard(%s,%s,%s) AS allowed",
                (user, identifier, generation),
            ).fetchone()["allowed"]

    assert guard(owned[2], 0)
    assert not guard(owned[3], 0) and not guard(owned[2], 1)
    with scoped(owned, "scheduler")() as c:
        c.execute("SELECT set_config('anvil.project',%s,true)", (owned[3],))
        assert not c.execute(
            "SELECT marketing_runtime.execution_guard(%s,%s,0) AS allowed", (owned[2], identifier)
        ).fetchone()["allowed"]
    with connection(owned) as c:
        c.execute(
            "UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s",
            (owned[1], owned[2]),
        )
    assert not guard(owned[2], 0)
