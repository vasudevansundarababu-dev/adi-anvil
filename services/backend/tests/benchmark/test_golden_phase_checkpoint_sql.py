"""Real durable SQL phase fences, including interrupted effect and tenant denial."""

from uuid import uuid4

import pytest
from test_golden_kyc_anvil_sql import scoped
from test_golden_kyc_sql import connection
from test_golden_kyc_sql import owned as owned_fixture

from anvil.golden_phase_checkpoints import execute

owned = owned_fixture


def test_checkpoint_commits_before_effect_and_denies_replay_after_failure(owned):
    connections = scoped(owned, "scheduler")
    job = {
        "project_id": owned[1],
        "id": str(uuid4()),
        "plan_id": str(uuid4()),
        "lease_token": "synthetic-private-lease-never-in-state",
    }
    calls = []

    def interrupted():
        # A separate transaction sees the phase BEFORE the long-running effect.
        with connection(owned) as c:
            rows = c.execute(
                "SELECT checkpoint FROM anvil_golden_checkpoints.checkpoints WHERE thread_id LIKE %s",
                (owned[1] + ":%",),
            ).fetchall()
            assert any(
                r["checkpoint"].get("channel_values", {}).get("phase") == "native_attempt_started"
                for r in rows
            )
            assert job["lease_token"] not in str(rows)
        calls.append("effect")
        raise RuntimeError("simulated_interruption")

    with pytest.raises(RuntimeError, match="simulated_interruption"):
        execute(connections, job, interrupted)
    # New graph/saver instance reads durable history; it cannot rerun the effect.
    with pytest.raises(RuntimeError, match="already_recorded_no_replay"):
        execute(connections, job, interrupted)
    assert calls == ["effect"]
    with connections() as c:
        assert (
            c.execute("SELECT count(*) AS n FROM anvil_golden_checkpoints.checkpoints").fetchone()[
                "n"
            ]
            > 0
        )
        c.execute("SELECT set_config('anvil.project',%s,true)", (str(uuid4()),))
        assert (
            c.execute("SELECT count(*) AS n FROM anvil_golden_checkpoints.checkpoints").fetchone()[
                "n"
            ]
            == 0
        )
    with connection(owned) as c:
        assert not c.execute(
            "SELECT has_schema_privilege('anvil_app','anvil_golden_checkpoints','USAGE') AS allowed"
        ).fetchone()["allowed"]


def test_completed_graph_persists_only_phase_identities_and_result_hash(owned):
    connections = scoped(owned, "scheduler")
    job = {
        "project_id": owned[1],
        "id": str(uuid4()),
        "plan_id": str(uuid4()),
        "lease_token": "synthetic-private-token",
    }
    result = {"status": "succeeded", "private_fixture_value": "not-for-checkpoint"}
    assert execute(connections, job, lambda: result) == result
    with connections() as c:
        rows = c.execute("SELECT checkpoint FROM anvil_golden_checkpoints.checkpoints").fetchall()
        assert any(
            r["checkpoint"].get("channel_values", {}).get("phase") == "native_attempt_finished"
            for r in rows
        )
        assert "not-for-checkpoint" not in str(rows)
        assert job["lease_token"] not in str(rows)
