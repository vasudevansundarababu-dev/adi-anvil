"""Real SQL lifecycle over manufactured metadata; no native inspection is claimed."""

from uuid import uuid4

from test_benchmark_pipeline import signed_lab as pipeline_lab
from test_benchmark_scheduler_security import actor_connection, launch
from test_benchmark_scheduler_security import frozen as scheduler_frozen
from test_private_storage import lab as storage_lab

from anvil import benchmark_scheduler as scheduler

lab = storage_lab
signed_lab = pipeline_lab
frozen = scheduler_frozen


def test_resume_keeps_exact_checkpoint_children_and_windows_and_cannot_undo_cancel(frozen):
    case = frozen
    created = launch(case).json()["data"]
    path = case["base"] + "/comparisons/" + created["run_id"]
    body = {
        "expected_subject_sha256": created["subject_sha256"],
        "expected_event_seq": created["checkpoint_event_seq"],
    }
    response = case["admin"].post(
        path + "/resume", json=body, headers={"idempotency-key": str(uuid4())}
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["data"]["resumable"] == 18 and response.json()["data"]["new_attempts"] == 0
    )
    with actor_connection(case) as c:
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.benchmark_cell_attempts a JOIN anvil.benchmark_cells cell ON cell.id=a.cell_id WHERE cell.run_id=%s",
                (created["run_id"],),
            ).fetchone()["n"]
            == 18
        )
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.benchmark_spend_bindings WHERE run_id=%s",
                (created["run_id"],),
            ).fetchone()["n"]
            == 2
        )
    cancelled = case["admin"].post(
        path + "/cancel",
        json={
            "expected_subject_sha256": created["subject_sha256"],
            "rationale": "Synthetic explicit cancellation in SQL only",
        },
        headers={"idempotency-key": str(uuid4())},
    )
    assert cancelled.status_code == 200
    body["expected_event_seq"] = cancelled.json()["data"]["checkpoint_event_seq"]
    denied = case["admin"].post(
        path + "/resume", json=body, headers={"idempotency-key": str(uuid4())}
    )
    assert denied.status_code == 409


def test_explicit_stop_attestation_releases_only_capacity_never_retries_or_scores_unknown(frozen):
    case = frozen
    created = launch(case).json()["data"]
    run = created["run_id"]
    path = case["base"] + "/comparisons/" + run
    with actor_connection(case) as c:
        row = c.execute(
            "SELECT rt.*,cell.id cell_id,cell.slot FROM anvil.benchmark_offline_runtime rt JOIN anvil.benchmark_cell_attempts a ON a.id=rt.attempt_id JOIN anvil.benchmark_cells cell ON cell.id=a.cell_id WHERE rt.run_id=%s ORDER BY cell.id LIMIT 1",
            (run,),
        ).fetchone()
        c.execute(
            "UPDATE anvil.benchmark_offline_runtime SET state='claimed',lease_until=now()-interval '1 second' WHERE attempt_id=%s",
            (row["attempt_id"],),
        )
        c.execute(
            "INSERT INTO anvil.benchmark_capacity_claims(id,project_id,run_id,cell_id,attempt_id,provider,slot,fence,generation,lease_until,state) VALUES(%s,%s,%s,%s,%s,'openai',%s,%s,1,now()-interval '1 second','held')",
            (
                uuid4(),
                case["lab"]["project"],
                run,
                row["cell_id"],
                row["attempt_id"],
                row["slot"],
                row["fence"],
            ),
        )
        c.execute(
            "UPDATE anvil.benchmark_offline_runtime SET state='intent' WHERE attempt_id=%s",
            (row["attempt_id"],),
        )
    with actor_connection(case) as c:
        assert scheduler.expire(c, case["lab"]["project"], run) == 1
        event = c.execute(
            "SELECT max(event_seq) n FROM anvil.benchmark_attempt_events WHERE attempt_id=%s",
            (row["attempt_id"],),
        ).fetchone()["n"]
    evidence = case["admin"].post(
        path + "/operator-evidence",
        json={
            "evidence_text": "Manufactured SQL proof only: no actual native actor inspection occurred"
        },
        headers={"idempotency-key": str(uuid4())},
    )
    assert evidence.status_code == 200, evidence.text
    proof = evidence.json()["data"]
    body = {
        "expected_subject_sha256": created["subject_sha256"],
        "expected_event_seq": event,
        "cell_id": str(row["cell_id"]),
        "evidence_artifact_id": proof["evidence_artifact_id"],
        "evidence_sha256": proof["evidence_sha256"],
        "owned_actors_stopped_confirmed": False,
    }
    denied = case["admin"].post(
        path + "/reconciliations", json=body, headers={"idempotency-key": str(uuid4())}
    )
    assert denied.status_code == 409
    body["owned_actors_stopped_confirmed"] = True
    key = str(uuid4())
    response = case["admin"].post(
        path + "/reconciliations", json=body, headers={"idempotency-key": key}
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["data"]["outcome"] == "unknown_unscored"
        and response.json()["data"]["retry"] is False
    )
    repeated = case["admin"].post(
        path + "/reconciliations", json=body, headers={"idempotency-key": key}
    )
    assert (
        repeated.status_code == 200
        and repeated.json()["data"]["reconciliation_id"]
        == response.json()["data"]["reconciliation_id"]
    )
    with actor_connection(case) as c:
        assert (
            c.execute(
                "SELECT state FROM anvil.benchmark_offline_runtime WHERE attempt_id=%s",
                (row["attempt_id"],),
            ).fetchone()["state"]
            == "dispatch_unknown"
        )
        assert (
            c.execute(
                "SELECT state FROM anvil.benchmark_capacity_claims WHERE attempt_id=%s",
                (row["attempt_id"],),
            ).fetchone()["state"]
            == "released"
        )
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.benchmark_cell_attempts WHERE cell_id=%s",
                (row["cell_id"],),
            ).fetchone()["n"]
            == 1
        )
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.benchmark_evaluator_calls WHERE attempt_id=%s",
                (row["attempt_id"],),
            ).fetchone()["n"]
            == 0
        )
