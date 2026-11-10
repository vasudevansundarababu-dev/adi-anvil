"""Explicit one-trial offline operator; no daemon, credentials or paid SDK calls.

Uses real SDK mapping at the controlled vendor boundary, actual actor tools and
the existing separate reviewed per-case native evaluator. It does not label that
fixture evaluator as the distinct T06 numeric/semantic judge service.
"""

import argparse
import json
import os
import re
import stat
from uuid import UUID

from fastapi import HTTPException

from anvil import auth
from anvil import benchmark_scheduler as scheduler
from anvil.benchmark_compiler import FIXTURE_IMAGE, CompiledTask
from anvil.benchmark_evaluator_program import canonical, seal, seal_checked
from anvil.benchmark_evaluator_worker import connection_factory
from anvil.benchmark_execution import protocol_gates, version
from anvil.benchmark_offline_actor import driver
from anvil.benchmark_pipeline import checksum, policy_status, private_metadata, source_snapshot
from anvil.benchmark_qualification import NativeDocker, native_trial
from anvil.benchmark_results import publish as publish_scores
from anvil.benchmark_storage import bind_private, read_private_record, stage_private, vault_root
from anvil.config import ROOT, setting
from anvil.db import Jsonb, one, transaction, uid
from anvil.domain import get_revision


def record_outputs(
    c, project, user, claimed, manifest_id, declarations, prepared_files, *, invalid_paths=()
):
    """Register each actual file or an exact per-path absence after actor stop."""
    if set(prepared_files) - {output["path"] for output in declarations}:
        raise ValueError("Unexpected captured output path")
    for output in declarations:
        prepared = prepared_files.get(output["path"])
        artifact = bind_private(c, prepared, created_by=user) if prepared else None
        absence = None
        if prepared is None or prepared.byte_size == 0:
            absence = uid()
            c.execute(
                "INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence,sealed_output_artifact_id,reason_code) VALUES(%s,%s,%s,'collecting','pending',%s,%s,%s)",
                (
                    absence,
                    project,
                    claimed["attempt_id"],
                    claimed["fence"],
                    manifest_id,
                    "required_output_absent"
                    if prepared is None and output["required"]
                    else "output_content_absent",
                ),
            )
        outcome = (
            "absent"
            if prepared is None
            else "invalid"
            if output["path"] in invalid_paths or (output["required"] and prepared.byte_size == 0)
            else "captured"
        )
        c.execute(
            "INSERT INTO anvil.benchmark_captured_outputs(project_id,attempt_id,path,fence,manifest_artifact_id,required,outcome,artifact_id,sha256,byte_size,absence_event_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                project,
                claimed["attempt_id"],
                output["path"],
                claimed["fence"],
                manifest_id,
                output["required"],
                outcome,
                artifact,
                prepared.sha256 if prepared else None,
                prepared.byte_size if prepared else None,
                absence,
            ),
        )


def operator(c, project, user):
    auth.require(auth.project_roles(c, project, user), "admin", "rl-engineer")
    if not one(
        c, "SELECT anvil.benchmark_private_access(%s,'benchmark_trace',%s) ok", (project, uid())
    )["ok"]:
        raise HTTPException(403, "Current individual evaluation assignment is required")


def inputs(project, user, claimed):
    frozen = claimed["protocol"]
    with transaction(project, user) as c:
        operator(c, project, user)
        bound = version(c, frozen.benchmark_revision_id)
        row = one(
            c,
            """SELECT t.*,p.package_sha256,p.package_artifact_id FROM anvil.benchmark_build_tasks t
            JOIN anvil.harbor_packages p ON p.project_id=t.project_id AND p.id=t.package_id
            JOIN anvil.benchmark_version_tasks v ON v.project_id=t.project_id AND v.package_id=t.package_id
            AND v.source_id=t.source_id WHERE t.build_id=%s AND v.task_revision_id=%s""",
            (bound["build_id"], claimed["task_revision_id"]),
        )
        build = one(
            c, "SELECT receipt_id FROM anvil.benchmark_builds WHERE id=%s", (bound["build_id"],)
        )
        if row is None:
            raise HTTPException(409, "Frozen compiled package is unavailable")
        package_metadata = private_metadata(c, row["package_artifact_id"])
        binding_metadata = private_metadata(c, row["bindings_artifact_id"])
    _, blockers = policy_status(project, user, bound["build_id"])
    if blockers:
        raise HTTPException(409, "Frozen build policy is no longer current")
    _, _, parsed, _ = source_snapshot(project, user, build["receipt_id"])
    task = next(t for t in parsed.parsed.manifest.tasks if t.id == row["task_id"])
    package, bindings = read_private_record(package_metadata), read_private_record(binding_metadata)
    if checksum(package) != row["package_sha256"] or checksum(bindings) != row["binding_sha256"]:
        raise ValueError("Compiled package or binding bytes changed")
    compiled = CompiledTask(
        row["package_sha256"], len(package), row["binding_sha256"], json.loads(bindings)
    )
    runtime = vault_root() / "offline-runtime"
    runtime.mkdir(mode=0o700, exist_ok=True)
    info = runtime.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError("Native trial roots must be owned private directories")
    folder = runtime / uid()
    folder.mkdir(mode=0o700)
    preflight_home = folder / "preflight-home"
    preflight_home.mkdir(mode=0o700)
    docker = NativeDocker(preflight_home)
    images = json.loads(docker.run(["image", "inspect", FIXTURE_IMAGE]))
    if (
        len(images) != 1
        or images[0]["Os"] != "linux"
        or FIXTURE_IMAGE.split("@")[1]
        not in [ref.split("@")[1] for ref in images[0].get("RepoDigests", [])]
    ):
        raise ValueError("The exact preloaded native image is absent; no image pull is permitted")
    path = folder / "actor.zip"
    with path.open("xb") as stream:
        stream.write(package)
    path.chmod(0o600)
    return task, compiled, path, folder


def capture(project, user, claimed, task, folder, report):
    if (
        report.get("mode") != "offline_conversation"
        or report.get("conversation", {}).get("measured_model_performance") is not False
    ):
        raise ValueError("Only the declared offline native conformance receipt is accepted")
    slot = claimed["protocol"].slots[claimed["slot"]]
    frozen_task = next(
        t for t in claimed["protocol"].tasks if t.task_revision_id == claimed["task_revision_id"]
    )
    if (
        (report["conversation"].get("provider"), report["conversation"].get("model_id"))
        != (slot.binding.provider, slot.binding.model_id)
        or report.get("compiled_archive_sha256") != frozen_task.package_sha256
        or report.get("task_id") != task.id
    ):
        raise ValueError("Native receipt differs from the frozen task/model binding")
    if (
        report.get("candidate_stopped_before_evaluation") is not True
        or report.get("candidate_mounts_private") is not False
        or report.get("evaluator_mounts_actor") is not False
        or report.get("forbidden_access_attempts_denied") != 4
    ):
        raise ValueError("Native boundary evidence is incomplete")
    if (
        any(
            not re.fullmatch(r"[a-f0-9]{64}", report.get(field, ""))
            for field in ("candidate_container", "evaluator_container")
        )
        or report["candidate_container"] == report["evaluator_container"]
    ):
        raise ValueError("Separate retained native actors/evaluators are required")
    criteria = report.get("criteria")
    expected = {criterion.id for criterion in task.criteria}
    if (
        not isinstance(criteria, dict)
        or set(criteria) != expected
        or any(type(v) is not int or v not in (0, 1) for v in criteria.values())
    ):
        raise ValueError("Native evaluator criterion membership is invalid")
    if (
        any(criterion.possible_points != 1 for criterion in task.criteria)
        or sum(criteria.values()) != report["points"]
    ):
        raise ValueError("Native evaluator points do not bind the initial profile")
    body = {key: value for key, value in report.items() if key != "native_receipt_sha256"}
    if (
        checksum(json.dumps(body, sort_keys=True, allow_nan=False).encode())
        != report["native_receipt_sha256"]
    ):
        raise ValueError("Native receipt hash changed")
    if type(report.get("duration_ms")) is not int or report["duration_ms"] < 0:
        raise ValueError("Measured native duration is required")
    files, missing = {}, []
    for output in task.outputs:
        path = folder / "captured" / output.path
        if path.exists():
            data = path.read_bytes()
            if len(data) > output.max_bytes:
                raise ValueError("Captured output exceeds frozen declaration")
            files[output.path] = data
        else:
            missing.append(output.path)
    sealed = seal(files, missing, task_id=task.id)
    prepared_output = stage_private(
        project, canonical(sealed), "benchmark_sealed", "application/json"
    )
    prepared_report = stage_private(
        project, canonical(report), "benchmark_trace", "application/json"
    )
    prepared_files = {
        output.path: stage_private(
            project, files[output.path], "benchmark_sealed", output.media_type
        )
        for output in task.outputs
        if output.path in files
    }
    with transaction(project, user) as c:
        operator(c, project, user)
        scheduler.current(
            c, project, claimed["run_id"], claimed["attempt_id"], claimed["fence"], {"intent"}
        )
        output = bind_private(c, prepared_output, created_by=user)
        trace = bind_private(c, prepared_report, created_by=user)
        c.execute(
            "UPDATE anvil.benchmark_offline_runtime SET state='captured',output_artifact_id=%s,report_artifact_id=%s,duration_ms=%s,updated_at=now() WHERE attempt_id=%s",
            (output, trace, report["duration_ms"], claimed["attempt_id"]),
        )
        c.execute(
            "INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence,sealed_output_artifact_id) VALUES(%s,%s,%s,'collecting','pending',%s,%s)",
            (uid(), project, claimed["attempt_id"], claimed["fence"], output),
        )
        record_outputs(
            c,
            project,
            user,
            claimed,
            output,
            [declaration.model_dump(mode="json") for declaration in task.outputs],
            prepared_files,
            invalid_paths=("answers.json",) if report.get("invalid_output") else (),
        )
    return finalize(project, user, claimed)


def finalize(project, user, claimed, *, evaluator_connect=None):
    """Capture is durable; restart finishes it without another actor/SDK request."""
    with transaction(project, user) as c:
        operator(c, project, user)
        current = scheduler.current(
            c, project, claimed["run_id"], claimed["attempt_id"], claimed["fence"], {"captured"}
        )
        report_metadata = private_metadata(c, current["report_artifact_id"])
        output_metadata = private_metadata(c, current["output_artifact_id"])
    report = json.loads(read_private_record(report_metadata))
    manifest = json.loads(read_private_record(output_metadata))
    seal_checked(manifest)
    evaluator_connect = evaluator_connect or connection_factory(
        setting("ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL")
    )
    with transaction(project, user) as c:
        operator(c, project, user)
        current = scheduler.current(
            c, project, claimed["run_id"], claimed["attempt_id"], claimed["fence"], {"captured"}
        )
        protocol_id = one(
            c, "SELECT protocol_revision_id FROM anvil.runs WHERE id=%s", (claimed["run_id"],)
        )["protocol_revision_id"]
        projection, blockers = protocol_gates(c, protocol_id)
        if blockers:
            raise HTTPException(409, "Captured evidence awaits current policy; no actor retry")
        task_content = get_revision(c, claimed["task_revision_id"], "task")["content"]
        outputs = c.execute(
            "SELECT * FROM anvil.benchmark_captured_outputs WHERE attempt_id=%s",
            (claimed["attempt_id"],),
        ).fetchall()
        by_path = {output["path"]: output for output in outputs}
        if (
            set(by_path) != {output["path"] for output in task_content["outputs"]}
            or manifest["task_id"] != task_content["task_id"]
        ):
            raise HTTPException(409, "Exact frozen deliverable custody is required")
        sealed_files = {file["path"]: file for file in manifest["files"]}
        for path, captured in by_path.items():
            file = sealed_files.get(path)
            if file is None:
                if captured["artifact_id"] is not None or path not in manifest["missing"]:
                    raise HTTPException(409, "Captured absence differs from the immutable manifest")
            elif captured["sha256"] != file["sha256"] or captured["byte_size"] != file["byte_size"]:
                raise HTTPException(409, "Deliverable bytes differ from the immutable manifest")
        task_binding = next(
            t
            for t in projection["protocol"]["tasks"]
            if t["task_revision_id"] == str(claimed["task_revision_id"])
        )
        custody = one(
            c,
            "SELECT job_id FROM anvil.benchmark_native_evaluator_custody WHERE attempt_id=%s",
            (claimed["attempt_id"],),
        )
        if custody is None:
            job = uid()
            c.execute(
                "INSERT INTO anvil.benchmark_evaluator_jobs(id,project_id,binding_id,sealed_output_artifact_id,created_by,state) VALUES(%s,%s,%s,%s,%s,'queued')",
                (
                    job,
                    project,
                    task_binding["evaluator_binding_id"],
                    current["output_artifact_id"],
                    user,
                ),
            )
            c.execute(
                "INSERT INTO anvil.benchmark_native_evaluator_custody(project_id,attempt_id,job_id,fence,output_sha256,report_sha256) VALUES(%s,%s,%s,%s,%s,%s)",
                (
                    project,
                    claimed["attempt_id"],
                    job,
                    claimed["fence"],
                    output_metadata["sha256"],
                    report_metadata["sha256"],
                ),
            )
        else:
            job = custody["job_id"]
    with evaluator_connect() as c:
        if one(c, "SELECT current_user role")["role"] != "anvil_benchmark_evaluator":
            raise PermissionError("Dedicated evaluator SQL identity required")
        c.execute("SELECT set_config('anvil.project',%s,true)", (str(project),))
        finished = one(
            c,
            "SELECT anvil.finish_native_benchmark_capture(%s,%s,%s,%s,%s) job_id",
            (
                project,
                claimed["attempt_id"],
                claimed["fence"],
                output_metadata["sha256"],
                report_metadata["sha256"],
            ),
        )
        if finished is None or finished["job_id"] is None or str(finished["job_id"]) != str(job):
            raise PermissionError("Independent native evaluator completion was rejected")
    with transaction(project, user) as c:
        operator(c, project, user)
        current = scheduler.current(
            c, project, claimed["run_id"], claimed["attempt_id"], claimed["fence"], {"captured"}
        )
        _, blockers = protocol_gates(c, protocol_id)
        completed_job = one(
            c, "SELECT state FROM anvil.benchmark_evaluator_jobs WHERE id=%s", (job,)
        )
        if blockers or completed_job is None or completed_job["state"] != "finished":
            raise HTTPException(409, "Independent evaluator evidence or current policy is required")
        call = uid()
        c.execute(
            "INSERT INTO anvil.benchmark_evaluator_calls(id,project_id,attempt_id,evaluator_job_id,evaluation_revision,purpose,request_sha256) VALUES(%s,%s,%s,%s,1,'deterministic',%s)",
            (call, project, claimed["attempt_id"], job, output_metadata["sha256"]),
        )
        definitions = {criterion["id"]: criterion for criterion in task_content["criteria"]}
        if set(report["criteria"]) != set(definitions):
            raise HTTPException(409, "Evaluator criterion membership differs from the frozen task")
        for criterion, earned in report["criteria"].items():
            captured = by_path[definitions[criterion]["output_path"]]
            if captured["artifact_id"] is not None and captured["byte_size"] > 0:
                c.execute(
                    "INSERT INTO anvil.benchmark_criterion_results(id,project_id,evaluator_call_id,criterion_id,earned_points,possible_points,output_artifact_id,output_sha256,evidence_start,evidence_end) VALUES(%s,%s,%s,%s,%s,1,%s,%s,0,%s)",
                    (
                        uid(),
                        project,
                        call,
                        criterion,
                        earned,
                        captured["artifact_id"],
                        captured["sha256"],
                        captured["byte_size"],
                    ),
                )
            else:
                if earned != 0 or captured["absence_event_id"] is None:
                    raise HTTPException(
                        409, "Absent deliverables require zero and their exact typed absence event"
                    )
                c.execute(
                    "INSERT INTO anvil.benchmark_criterion_results(id,project_id,evaluator_call_id,criterion_id,earned_points,possible_points,absence_event_id) VALUES(%s,%s,%s,%s,0,1,%s)",
                    (uid(), project, call, criterion, captured["absence_event_id"]),
                )
        violated = report.get("violated_constraint_ids", [])
        declared = {
            constraint["id"]: constraint["hard_failure"]
            for constraint in task_content["constraints"]
        }
        if (
            not isinstance(violated, list)
            or any(type(value) is not str for value in violated)
            or len(set(violated)) != len(violated)
            or not set(violated) <= set(declared)
        ):
            raise HTTPException(
                409, "Constraint violations must bind exact explicitly frozen declarations"
            )
        hard_ids = sorted(value for value in violated if declared[value])
        bad_required = {
            output["path"]
            for output in outputs
            if output["required"] and output["outcome"] != "captured"
        }
        unresolved = sorted(
            bad_required - {criterion["output_path"] for criterion in definitions.values()}
        )
        failed = bool(bad_required or hard_ids)
        terminal_event = uid()
        c.execute(
            "INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence,sealed_output_artifact_id,reason_code) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                terminal_event,
                project,
                claimed["attempt_id"],
                "model_failed" if failed else "completed",
                "unresolved" if unresolved else "valid",
                claimed["fence"],
                current["output_artifact_id"],
                "required_output_rule_missing"
                if unresolved
                else "hard_safety_constraint"
                if hard_ids
                else "required_deliverable_failure"
                if failed
                else None,
            ),
        )
        c.execute(
            "INSERT INTO anvil.benchmark_attempt_policy_outcomes(project_id,attempt_id,fence,report_artifact_id,terminal_event_id,hard_constraint_ids,unresolved_required_paths) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (
                project,
                claimed["attempt_id"],
                claimed["fence"],
                current["report_artifact_id"],
                terminal_event,
                Jsonb(hard_ids),
                Jsonb(unresolved),
            ),
        )
        c.execute(
            "UPDATE anvil.benchmark_offline_runtime SET state='completed',updated_at=now() WHERE attempt_id=%s",
            (claimed["attempt_id"],),
        )
        c.execute(
            "UPDATE anvil.benchmark_capacity_claims SET state='released' WHERE attempt_id=%s AND state='held'",
            (claimed["attempt_id"],),
        )
        c.execute(
            "UPDATE anvil.jobs SET status='succeeded' WHERE target_id=%s AND kind='benchmark_offline_trial'",
            (claimed["attempt_id"],),
        )
        publish_scores(c, project, user, claimed["run_id"])
    return "completed"


def process(project, run_id, user):
    if (
        os.environ.get("ANVIL_BENCHMARK_OFFLINE_ENABLED") != "true"
        or os.environ.get("ANVIL_TEST_HARBOR") != "1"
    ):
        raise RuntimeError("Explicit offline native operator activation required")
    with transaction(project, user) as c:
        operator(c, project, user)
        captured = one(
            c,
            "SELECT rt.*,cell.task_revision_id FROM anvil.benchmark_offline_runtime rt JOIN anvil.benchmark_cell_attempts a ON a.project_id=rt.project_id AND a.id=rt.attempt_id JOIN anvil.benchmark_cells cell ON cell.project_id=a.project_id AND cell.id=a.cell_id WHERE rt.run_id=%s AND rt.state='captured' ORDER BY rt.created_at LIMIT 1",
            (run_id,),
        )
        claimed = None if captured else scheduler.claim(c, project, run_id)
    if captured:
        return finalize(project, user, captured)
    if claimed is None:
        return "not_claimed"
    try:
        task, compiled, package, folder = inputs(project, user, claimed)
        with transaction(project, user) as c:
            operator(c, project, user)
            scheduler.intent(c, project, claimed)
    except Exception:
        with transaction(project, user) as c:
            c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
            row = one(
                c,
                "SELECT state,fence FROM anvil.benchmark_offline_runtime WHERE attempt_id=%s FOR UPDATE",
                (claimed["attempt_id"],),
            )
            if row and row["state"] == "claimed" and row["fence"] == claimed["fence"]:
                c.execute(
                    "UPDATE anvil.benchmark_offline_runtime SET state='operational_failed',reason_code='pre_dispatch_blocked',updated_at=now() WHERE attempt_id=%s",
                    (claimed["attempt_id"],),
                )
                c.execute(
                    "UPDATE anvil.benchmark_capacity_claims SET state='released' WHERE attempt_id=%s AND state='held'",
                    (claimed["attempt_id"],),
                )
                c.execute(
                    "UPDATE anvil.jobs SET status='failed',error_code='pre_dispatch_blocked' WHERE target_id=%s AND kind='benchmark_offline_trial'",
                    (claimed["attempt_id"],),
                )
                c.execute(
                    "INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence,reason_code) VALUES(%s,%s,%s,'operational_failed','invalid',%s,'pre_dispatch_blocked')",
                    (uid(), project, claimed["attempt_id"], claimed["fence"]),
                )
        raise
    try:
        slot = claimed["protocol"].slots[claimed["slot"]]

        def dispatch_check():
            with transaction(project, user) as c:
                operator(c, project, user)
                scheduler.current(
                    c, project, run_id, claimed["attempt_id"], claimed["fence"], {"intent"}
                )
                row = one(c, "SELECT cancel_requested FROM anvil.runs WHERE id=%s", (run_id,))
                _, blockers = protocol_gates(
                    c,
                    one(c, "SELECT protocol_revision_id FROM anvil.runs WHERE id=%s", (run_id,))[
                        "protocol_revision_id"
                    ],
                )
                if row["cancel_requested"] or blockers:
                    raise HTTPException(409, "Comparison cancellation or policy precedes this turn")

        report = native_trial(
            package,
            compiled,
            task,
            ROOT / "fixtures/benchmark-bundle/fictional-points-v1/eval_pack" / task.id,
            folder,
            mode="offline_conversation",
            actor_driver=driver(
                slot.binding, claimed["protocol"].limits, dispatch_check=dispatch_check
            ),
        )
        return capture(project, user, claimed, task, folder, report)
    except Exception:
        # Ambiguous work is retained and never silently retried or relabeled zero.
        with transaction(project, user) as c:
            row = one(
                c,
                "SELECT state FROM anvil.benchmark_offline_runtime WHERE attempt_id=%s FOR UPDATE",
                (claimed["attempt_id"],),
            )
            if row and row["state"] == "intent":
                c.execute(
                    "UPDATE anvil.benchmark_offline_runtime SET state='dispatch_unknown',reason_code='operator_interrupted',updated_at=now() WHERE attempt_id=%s",
                    (claimed["attempt_id"],),
                )
                c.execute(
                    "UPDATE anvil.benchmark_capacity_claims SET state='dispatch_unknown' WHERE attempt_id=%s AND state='held'",
                    (claimed["attempt_id"],),
                )
                c.execute(
                    "INSERT INTO anvil.benchmark_attempt_events(id,project_id,attempt_id,state,validity,fence,reason_code) VALUES(%s,%s,%s,'dispatch_unknown','unresolved',%s,'operator_interrupted')",
                    (uid(), project, claimed["attempt_id"], claimed["fence"]),
                )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=UUID, required=True)
    parser.add_argument("--run", type=UUID, required=True)
    parser.add_argument("--operator", type=UUID, required=True)
    parser.add_argument("--max-trials", type=int, default=1, choices=range(1, 19))
    args = parser.parse_args()
    statuses = []
    try:
        for _ in range(args.max_trials):
            status = process(args.project, args.run, args.operator)
            statuses.append(status)
            if status == "not_claimed":
                break
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_kind": type(exc).__name__,
                    "paid_calls": False,
                    "retained": True,
                }
            )
        )
        raise SystemExit(1) from None
    print(json.dumps({"statuses": statuses, "paid_calls": False}))


if __name__ == "__main__":
    main()
