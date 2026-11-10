"""Independent deliverable/absence SQL contracts; manufactured metadata only.

No native evaluator or candidate runs here. Credit values are constructed solely
to test evidence constraints and never represent measured model performance.
"""

from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from test_benchmark_pipeline import signed_lab as pipeline_lab
from test_benchmark_scheduler_security import actor_connection, finish, manufactured_capture
from test_benchmark_scheduler_security import frozen as scheduler_frozen
from test_private_storage import connection
from test_private_storage import lab as storage_lab

from anvil.benchmark_storage import bind_private, stage_private
from anvil.domain import get_revision

lab = storage_lab
signed_lab = pipeline_lab
frozen = scheduler_frozen


def absence(c, case, captured, reason="required_output_absent"):
    identifier = uuid4()
    c.execute(
        "INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence,sealed_output_artifact_id,reason_code) VALUES(%s,%s,%s,'collecting','pending',%s,%s,%s)",
        (
            identifier,
            case["lab"]["project"],
            captured["claim"]["attempt_id"],
            captured["claim"]["fence"],
            captured["manifest_artifact_id"],
            reason,
        ),
    )
    return identifier


def output(
    c,
    case,
    captured,
    path,
    data,
    *,
    event=None,
    fence=None,
    classification="benchmark_sealed",
    outcome=None,
):
    prepared = (
        stage_private(case["lab"]["project"], data, classification) if data is not None else None
    )
    identifier = bind_private(c, prepared, created_by=case["lab"]["admin"]) if prepared else None
    row = {
        "artifact": identifier,
        "sha256": prepared.sha256 if prepared else None,
        "size": len(data) if data is not None else None,
    }
    c.execute(
        "INSERT INTO anvil.benchmark_captured_outputs(project_id,attempt_id,path,fence,manifest_artifact_id,required,outcome,artifact_id,sha256,byte_size,absence_event_id) VALUES(%s,%s,%s,%s,%s,true,%s,%s,%s,%s,%s)",
        (
            case["lab"]["project"],
            captured["claim"]["attempt_id"],
            path,
            fence or captured["claim"]["fence"],
            captured["manifest_artifact_id"],
            outcome or ("absent" if data is None else "invalid" if not data else "captured"),
            identifier,
            row["sha256"],
            row["size"],
            event,
        ),
    )
    return row


def evaluator_call(case, captured):
    with connection("anvil_benchmark_evaluator", case["lab"]["project"], case["lab"]["admin"]) as c:
        assert finish(c, case, captured) == captured["job"]
    identifier = uuid4()
    with actor_connection(case) as c:
        c.execute(
            "INSERT INTO anvil.benchmark_evaluator_calls(id,project_id,attempt_id,evaluator_job_id,evaluation_revision,purpose,request_sha256) VALUES(%s,%s,%s,%s,1,'deterministic',%s)",
            (
                identifier,
                case["lab"]["project"],
                captured["claim"]["attempt_id"],
                captured["job"],
                captured["output"],
            ),
        )
        criterion = get_revision(c, captured["claim"]["task_revision_id"], "task")["content"][
            "criteria"
        ][0]["id"]
    return identifier, criterion


def cite(c, case, call, criterion, *, artifact=None, sha=None, end=None, event=None, earned=0):
    c.execute(
        "INSERT INTO anvil.benchmark_criterion_results(id,project_id,evaluator_call_id,criterion_id,earned_points,possible_points,output_artifact_id,output_sha256,evidence_start,evidence_end,absence_event_id) VALUES(%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s)",
        (
            uuid4(),
            case["lab"]["project"],
            call,
            criterion,
            earned,
            artifact,
            sha,
            0 if artifact is not None else None,
            end,
            event,
        ),
    )


def test_nonempty_deliverable_citation_uses_its_file_hash_and_exact_byte_span(frozen):
    captured = manufactured_capture(frozen)
    with actor_connection(frozen) as c:
        file = output(c, frozen, captured, "answers.json", b"{}")
    call, criterion = evaluator_call(frozen, captured)
    with actor_connection(frozen) as c:
        cite(
            c,
            frozen,
            call,
            criterion,
            artifact=file["artifact"],
            sha=file["sha256"],
            end=2,
            earned=1,
        )
        row = c.execute(
            "SELECT output_sha256,evidence_start,evidence_end,absence_event_id FROM anvil.benchmark_criterion_results WHERE evaluator_call_id=%s",
            (call,),
        ).fetchone()
        assert row == {
            "output_sha256": file["sha256"],
            "evidence_start": 0,
            "evidence_end": 2,
            "absence_event_id": None,
        }
        assert file["sha256"] != captured["output"]


@pytest.mark.parametrize(
    "fault", ["wrapper", "wrong_hash", "wrong_output", "outside_span", "unknown_criterion"]
)
def test_wrapper_or_unbound_file_cannot_substitute_for_deliverable_evidence(frozen, fault):
    captured = manufactured_capture(frozen)
    with actor_connection(frozen) as c:
        file = output(c, frozen, captured, "answers.json", b"{}")
        report = output(c, frozen, captured, "report.md", b"Manufactured SQL report")
    call, criterion = evaluator_call(frozen, captured)
    selected = report if fault == "wrong_output" else file
    artifact = captured["manifest_artifact_id"] if fault == "wrapper" else selected["artifact"]
    sha = (
        captured["output"]
        if fault == "wrapper"
        else "0" * 64
        if fault == "wrong_hash"
        else selected["sha256"]
    )
    with actor_connection(frozen) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="actual deliverable span"):
            cite(
                c,
                frozen,
                call,
                "invented-criterion" if fault == "unknown_criterion" else criterion,
                artifact=artifact,
                sha=sha,
                end=selected["size"] + (1 if fault == "outside_span" else 0),
                earned=1,
            )


@pytest.mark.parametrize("data", [None, b""])
def test_absent_or_empty_deliverable_zero_requires_its_typed_event(frozen, data):
    files = {"report.md": b"Manufactured SQL report"}
    if data is not None:
        files["answers.json"] = data
    captured = manufactured_capture(frozen, files=files)
    with actor_connection(frozen) as c:
        event = absence(
            c,
            frozen,
            captured,
            "required_output_absent" if data is None else "output_content_absent",
        )
        output(c, frozen, captured, "answers.json", data, event=event)
    call, criterion = evaluator_call(frozen, captured)
    with actor_connection(frozen) as c:
        cite(c, frozen, call, criterion, event=event)
        row = c.execute(
            "SELECT earned_points,output_artifact_id,output_sha256,evidence_start,evidence_end,absence_event_id FROM anvil.benchmark_criterion_results WHERE evaluator_call_id=%s",
            (call,),
        ).fetchone()
        assert row["earned_points"] == 0 and row["absence_event_id"] == event
        assert all(
            row[key] is None
            for key in ("output_artifact_id", "output_sha256", "evidence_start", "evidence_end")
        )


@pytest.mark.parametrize("fault", ["wrong_fence", "wrong_class", "undeclared_path"])
def test_captured_file_binding_rejects_other_fence_class_or_undeclared_path(frozen, fault):
    captured = manufactured_capture(frozen)
    with actor_connection(frozen) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="exact frozen path"):
            output(
                c,
                frozen,
                captured,
                "undeclared.json" if fault == "undeclared_path" else "answers.json",
                b"{}",
                fence=uuid4() if fault == "wrong_fence" else None,
                classification="benchmark_trace" if fault == "wrong_class" else "benchmark_sealed",
            )


def test_absence_event_cannot_cross_attempt_or_bind_two_output_paths(frozen):
    first = manufactured_capture(frozen, files={})
    second = manufactured_capture(frozen, files={})
    with actor_connection(frozen) as c:
        event = absence(c, frozen, first)
        output(c, frozen, first, "answers.json", None, event=event)
    with actor_connection(frozen) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="absence requires"):
            output(c, frozen, second, "answers.json", None, event=event)
    with actor_connection(frozen) as c:
        with pytest.raises(psycopg.errors.UniqueViolation):
            output(c, frozen, first, "report.md", None, event=event)


def terminal(c, case, captured):
    identifier = uuid4()
    c.execute(
        "INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence,sealed_output_artifact_id) VALUES(%s,%s,%s,'completed','valid',%s,%s)",
        (
            identifier,
            case["lab"]["project"],
            captured["claim"]["attempt_id"],
            captured["claim"]["fence"],
            captured["manifest_artifact_id"],
        ),
    )
    return identifier


def test_omitted_required_report_custody_row_cannot_fake_complete_policy(frozen):
    captured = manufactured_capture(frozen)
    with actor_connection(frozen) as c:
        output(c, frozen, captured, "answers.json", b"{}")
    with pytest.raises(
        psycopg.errors.RaiseException, match="complete declared deliverable custody"
    ):
        with actor_connection(frozen) as c:
            event = terminal(c, frozen, captured)
            c.execute(
                "INSERT INTO anvil.benchmark_attempt_policy_outcomes(project_id,attempt_id,fence,report_artifact_id,terminal_event_id,hard_constraint_ids,unresolved_required_paths) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    frozen["lab"]["project"],
                    captured["claim"]["attempt_id"],
                    captured["claim"]["fence"],
                    captured["report_artifact_id"],
                    event,
                    Jsonb([]),
                    Jsonb([]),
                ),
            )


@pytest.mark.parametrize("outcome", ["captured", "invalid"])
def test_empty_required_report_without_typed_empty_event_is_rejected(frozen, outcome):
    captured = manufactured_capture(frozen, files={"answers.json": b"{}", "report.md": b""})
    with actor_connection(frozen) as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            output(c, frozen, captured, "report.md", b"", outcome=outcome)


def test_terminal_event_without_immutable_policy_outcome_cannot_commit(frozen):
    captured = manufactured_capture(frozen)
    with actor_connection(frozen) as c:
        output(c, frozen, captured, "answers.json", b"{}")
        output(c, frozen, captured, "report.md", b"Manufactured SQL report")
    with pytest.raises(
        psycopg.errors.RaiseException, match="requires an exact frozen policy outcome"
    ):
        with actor_connection(frozen) as c:
            terminal(c, frozen, captured)
