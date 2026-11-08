"""Constrained one-job SQL coordinator; execution is a separate reviewed service.

No Docker, provider SDK or broad worker credential is used here. The executor receives
only the claimed sealed output and policy; never a connection or the vault path.
"""

import json
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from anvil.benchmark_evaluation import implementation_sha256
from anvil.benchmark_evaluator_program import calibration, canonical, sha, validate_report
from anvil.benchmark_storage import read_private_record, stage_private
from anvil.db import one


def _identity(c):
    row = one(c, "SELECT current_user AS role")
    if row["role"] != "anvil_benchmark_evaluator":
        raise PermissionError("Dedicated evaluator identity required")


def claim(c, project, job):
    _identity(c)
    return one(c, "SELECT * FROM anvil.claim_benchmark_evaluation(%s,%s)", (project, job))


def scoped(c, claimed):
    _identity(c)
    c.execute(
        "SELECT set_config('anvil.project',%s,true),set_config('anvil.benchmark_job',%s,true),set_config('anvil.benchmark_fence',%s,true)",
        (str(claimed["project_id"]), str(claimed["id"]), str(claimed["lease_token"])),
    )
    if not one(
        c, "SELECT anvil.benchmark_job_scope(%s,%s) ok", (claimed["project_id"], claimed["id"])
    )["ok"]:
        raise PermissionError("Evaluator fence no longer current")


def prepare_job(connect, claimed):
    with connect() as c:
        scoped(c, claimed)
        registry = one(
            c,
            "SELECT g.* FROM anvil.benchmark_evaluator_registrations g JOIN anvil.benchmark_evaluation_requests q ON q.registry_id=g.id AND q.project_id=g.project_id WHERE q.job_id=%s",
            (claimed["id"],),
        )
        inputs = c.execute(
            "SELECT a.* FROM anvil.artifacts a JOIN anvil.benchmark_evaluator_job_inputs i ON i.artifact_id=a.id AND i.project_id=a.project_id WHERE i.job_id=%s ORDER BY a.id",
            (claimed["id"],),
        ).fetchall()
        request = one(
            c, "SELECT * FROM anvil.benchmark_evaluation_requests WHERE job_id=%s", (claimed["id"],)
        )
    if (
        registry is None
        or registry["implementation_sha256"] != implementation_sha256()
        or registry["calibration_sha256"] != sha(canonical(calibration()))
    ):
        raise ValueError("Evaluator registry source or calibration changed")
    if len(inputs) != 2 or {a["classification"] for a in inputs} != {
        "benchmark_eval",
        "benchmark_sealed",
    }:
        raise ValueError("Unexpected evaluator input projection")
    bodies = {a["classification"]: json.loads(read_private_record(a)) for a in inputs}
    policy, sealed = bodies["benchmark_eval"], bodies["benchmark_sealed"]
    if (
        sealed["sealed_sha256"] != request["sealed_sha256"]
        or policy["task_id"] != request["task_id"]
    ):
        raise ValueError("Sealed task binding changed")
    return {"policy": policy, "sealed": sealed}


def finish(connect, claimed, job, report):
    checked = validate_report(job["policy"], job["sealed"], report)
    # Hashing/staging is outside SQL; the final fence recheck precedes capture.
    prepared = stage_private(
        claimed["project_id"], canonical(checked), "benchmark_trace", "application/json"
    )
    with connect() as c:
        scoped(c, claimed)
        row = one(
            c,
            "SELECT anvil.finish_benchmark_evaluation(%s,%s,%s,%s,%s,%s,%s,%s) ok",
            (
                claimed["project_id"],
                claimed["id"],
                claimed["lease_token"],
                checked["status"],
                checked["safe_code"],
                prepared.artifact_id,
                prepared.sha256,
                prepared.byte_size,
            ),
        )
        return row["ok"]


def process_job(connect, project, job_id, execute):
    """Explicit scoped dispatch only; no lease reclaim or automatic execution retry."""
    with connect() as c:
        claimed = claim(c, project, job_id)
    if claimed is None:
        return {"state": "not_claimed"}
    job = prepare_job(connect, claimed)
    with connect() as c:
        scoped(c, claimed)
    raw = execute(job)
    if type(raw) is not bytes or len(raw) > 2_000_000:
        raise ValueError("Evaluator report bound")
    report = json.loads(raw)
    if not finish(connect, claimed, job, report):
        raise PermissionError("Evaluator completion rejected")
    return {
        "state": "finished" if report["status"] == "evaluated" else "failed",
        "evaluation_state": report["status"],
    }


def connection_factory(dsn):
    @contextmanager
    def connect():
        with psycopg.connect(dsn, row_factory=dict_row) as c:
            _identity(c)
            yield c

    return connect
