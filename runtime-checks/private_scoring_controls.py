"""Actual private queue/grader/coordinator controls; no production qualification.

Modes run in separate containers. The grader gets only its restricted SQL config
and private bridge; the coordinator gets only that bridge and Docker. Submitted
code gets neither. Case verdicts stay in the grader's control config, never the
executor request. Ambiguous effects are retained, never replayed.
"""

import argparse
import hashlib
import json
import os
import signal
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID


class ControlDeadline(BaseException):
    pass


def private_json(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("Canonical private control config required")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        info = os.fstat(stream.fileno())
        if info.st_uid != os.geteuid() or os.geteuid() not in {0, 10001} or info.st_mode & 0o077 or not stat.S_ISREG(info.st_mode) or info.st_size > 131072:
            raise ValueError("Bounded root-owned control config required")
        return json.load(stream)


def grade(config_path, index):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    from psycopg.rows import dict_row

    from anvil import custom_python_grading as grading
    from anvil.db import digest
    from anvil.golden_kyc_evaluators import CRITERIA, score
    from anvil.private_scoring_control import ControlReference

    config = private_json(config_path)
    if config["schema_version"] != "anvil.synthetic-private-scoring-driver.v1" or not 0 <= index < len(config["cases"]):
        raise ValueError("Fixed private scoring control required")
    item = config["cases"][index]
    ref = ControlReference(UUID(item["reference"]["id"]), item["reference"]["sha256"])
    params = conninfo_to_dict(config["grader_dsn"])
    host = Path(params["host"])
    if (not host.is_absolute() or host.resolve() != host or not (host / ".s.PGSQL.5432").is_socket()
            or not params["dbname"].startswith("anvil_golden_kyc_component_")
            or set(params) - {"host", "port", "dbname", "user", "password", "sslmode"}):
        raise ValueError("Exact isolated Unix SQL target required")

    @contextmanager
    def connections():
        with psycopg.connect(**params, connect_timeout=2, row_factory=dict_row,
                             options="-c statement_timeout=5000 -c lock_timeout=500") as c:
            identity = c.execute("SELECT current_database() AS database,inet_server_addr() AS address").fetchone()
            if identity["database"] != params["dbname"] or identity["address"] is not None:
                raise ValueError("Actual Unix database identity required")
            c.execute("SET LOCAL ROLE anvil_golden_grader")
            c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (config["project_id"], config["user_id"]))
            yield c

    def collect(c, technical=True):
        return grading.collect_or_queue(c, config["project_id"], item["execution"], item["trial"]["trial_id"], item["trial"]["generation"],
            item["state"], item["expectation"], item["checks"], **({"_technical": ref} if technical else {}))

    with connections() as c:
        try:
            collect(c, technical=False)
        except RuntimeError as error:
            if str(error) != "custom_grading_current_qualification_required":
                raise
        else:
            raise ValueError("Synthetic admission granted production qualification")
        first = collect(c)
        if not first["pending"] or first["receipts"]:
            raise ValueError("Actual queued private job required")
        before = c.execute("SELECT * FROM banking_private.python_grading_jobs WHERE id=%s", (item["context"]["job_id"],)).fetchone()
        if before["state"] != "queued" or digest(before["request"]) != before["request_sha256"]:
            raise ValueError("Immutable real private queue input required")
        if any("expected_status" in before["request"][key] for key in ("actual", "expected")):
            raise ValueError("Host verdict entered private runtime input")
    # Operator starts the independent coordinator only after this committed
    # claim publishes request.json. It never sees grader_dsn or this case file.
    observed = grading.grader_once(connections, config["bridge_root"], seconds=120)
    if not observed or observed.get("id") != item["context"]["job_id"]:
        raise ValueError("Actual once-only grader completion required")
    with connections() as c:
        final = collect(c)
        if final["pending"] or len(final["receipts"]) != 1:
            raise ValueError("Consumed private SQL result required")
        receipt = final["receipts"][0]
        if receipt["status"] != item["expected_status"]:
            raise ValueError("Actual isolated status differs from reviewed control")
        baseline = score(dict.fromkeys(CRITERIA, 5), correct_decision=True, mandatory=True, critical_failures=[])
        result = grading.apply_overrides(baseline, item["expectation"], final["receipts"], _technical=ref)
        if result["checks"]["profile"] != grading.ANCHORS[item["expected_status"]]:
            raise ValueError("Actual anchor or unscored error changed")
        for critical in (False, True):
            veto = score(dict.fromkeys(CRITERIA, 5), correct_decision=True, mandatory=False,
                         critical_failures=["synthetic_veto"] if critical else [])
            value = grading.apply_overrides(veto, item["expectation"], final["receipts"], _technical=ref)
            if value["overall_result"] != ("critical_fail" if critical else "not_evaluated" if item["expected_status"] in {"error", "unscored"} else "fail"):
                raise ValueError("Original mandatory/critical veto changed")
        try:
            grading.apply_overrides(baseline, {"independent_expectation_review": "approved"}, final["receipts"])
        except RuntimeError:
            pass
        else:
            raise ValueError("Production consumed synthetic control result")
        stored = c.execute("SELECT request_sha256,result_sha256,state,result FROM banking_private.python_grading_jobs WHERE id=%s", (observed["id"],)).fetchone()
        if stored["state"] not in {"completed", "error"}:
            raise ValueError("Actual terminal private SQL state required")
        measured = stored["result"].get("execution_observation")
        from anvil.custom_python_executor import source_hash as executor_source
        from anvil.native_image_profile import IMAGE, IMAGE_ID

        if (not isinstance(measured, dict) or digest(measured) != stored["result"].get("execution_sha256")
                or stored["result"].get("execution_error") or measured.get("source_sha256") != executor_source()
                or measured.get("image") != IMAGE or measured.get("image_id") != IMAGE_ID
                or measured.get("container_retained_stopped") is not True or measured.get("network") != "none"
                or measured.get("readonly_root") is not True or len(measured.get("cases", [])) != 1
                or measured["cases"][0].get("actual_status") != item["expected_status"]):
            raise ValueError("Actual clean physical executor report required")
        if item["id"] == "exception" and (measured["cases"][0].get("error_type"), measured["cases"][0].get("line")) != ("ValueError", 14):
            raise ValueError("Reviewed program exception required; infrastructure errors cannot pass")
    print(json.dumps({"schema_version": "anvil.synthetic-private-scoring-observation.v1", "control_case": item["id"],
        "status": "passed", "observed_status": receipt["status"], "job_id": observed["id"], "request_sha256": stored["request_sha256"],
        "result_sha256": stored["result_sha256"], "code_sha256": item["context"]["code_sha256"], "review_sha256": item["context"]["review_receipt_sha256"],
        "source_sha256": grading.source_hash(), "task_score": None, "qualification_granted": False,
        "executor_container": measured["container_name"], "execution_sha256": stored["result"]["execution_sha256"],
        "model_performance": False, "model_calls_authorized": 0, "actual_model_calls": None,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    grader = sub.add_parser("grader")
    grader.add_argument("--config", required=True)
    grader.add_argument("--case", type=int, required=True)
    coordinator = sub.add_parser("coordinator")
    coordinator.add_argument("--root", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--root", required=True)
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError("Installed isolated interpreter required")
    signal.signal(signal.SIGALRM, lambda *unused: (_ for _ in ()).throw(ControlDeadline()))
    signal.alarm(180)
    if args.mode == "grader":
        grade(args.config, args.case)
    elif args.mode == "preflight":
        from anvil.custom_python_grading import coordinator_request, grading_root
        from anvil.environment_harbor import private_json as write_private
        from anvil.golden_native_bridge import publish_ipc

        root = grading_root(args.root, coordinator=True)
        if os.geteuid() != 0 or root.stat().st_uid != 10001:
            raise ValueError("Actual root/grader ownership boundary required")
        list(root.iterdir())
        folder = root / "permission-preflight"
        folder.mkdir(mode=0o700)
        os.chown(folder, 10001, 10001)
        value = {"schema_version": "anvil.private-coordinator-permission-control.v1", "purpose": "technical_only"}
        write_private(folder / "request.json", value)
        os.chown(folder / "request.json", 10001, 10001)
        os.link(folder / "request.json", folder / "claimed.json", follow_symlinks=False)
        if coordinator_request(folder) != value:
            raise ValueError("Actual claimed bytes changed")
        publish_ipc(folder / "result.json", value, 10001)
        info = (folder / "result.json").stat()
        if info.st_uid != 10001 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Actual grader-owned private result required")
        print(json.dumps({"status": "permissions_observed_not_qualified", "qualification_granted": False}))
    else:
        from anvil.custom_python_grading import coordinator_once

        value = coordinator_once(args.root, host="unix:///run/docker.sock")
        if value is None:
            raise ValueError("Fresh committed private request required")
        print(json.dumps({"status": "observed_not_qualified", "result_sha256": value.get("result_sha256"), "model_calls_authorized": 0}))


if __name__ == "__main__":
    try:
        main()
    except (Exception, ControlDeadline) as error:
        import traceback

        print(json.dumps({"status": "blocked_or_unknown_no_replay", "error_type": type(error).__name__,
            "frames": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                       for frame in traceback.extract_tb(error.__traceback__)[-8:]], "qualification_granted": False,
            "model_calls_authorized": 0, "actual_model_calls": None}))
        raise SystemExit(1) from None
