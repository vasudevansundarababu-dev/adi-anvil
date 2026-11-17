"""Bounded public actor evidence inside private, hash-bound qualification reports."""

import hashlib
import json
import math
import os
import re
import stat
from decimal import Decimal, InvalidOperation
from pathlib import Path

import rfc8785
from fastapi import HTTPException

from anvil import benchmark_pipeline as pipeline
from anvil.benchmark_storage import read_private_record
from anvil.benchmark_trust import load_trust_policy
from anvil.db import one

MAX_FILE = 65536
MAX_TOTAL = 131072


def _read_at(root, name, limit):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
        raise ValueError("Invalid public output leaf")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.getuid()
            or before.st_size > limit
        ):
            raise ValueError("Invalid sealed public file")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if (
            len(data) > limit
            or len(data) != before.st_size
            or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        ):
            raise ValueError("Sealed public file changed")
        return data


def capture_public(folder, task, evaluation, expected_seal):
    """Worker-only: read exact already-sealed actor files, never evaluator inputs."""
    root = os.open(Path(folder), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        raw = _read_at(root, "seal.json", MAX_FILE)
        if hashlib.sha256(raw).hexdigest() != expected_seal:
            raise ValueError("Public seal changed")
        manifest = json.loads(raw)
        if rfc8785.dumps(manifest) != raw or set(manifest) != {"files", "missing"}:
            raise ValueError("Invalid public seal")
        declarations = {output.path: output for output in task.outputs}
        files, missing = manifest["files"], manifest["missing"]
        paths = [item["path"] for item in files]
        if (
            len(paths) != len(set(paths))
            or len(missing) != len(set(missing))
            or set(paths) & set(missing)
            or set(paths) | set(missing) != set(declarations)
            or set(os.listdir(root)) != set(paths) | {"seal.json"}
        ):
            raise ValueError("Public seal membership changed")
        outputs, total = [], 0
        for item in files:
            if set(item) != {"path", "sha256", "byte_size"}:
                raise ValueError("Unsupported public seal entry")
            path = item["path"]
            data = _read_at(root, path, min(MAX_FILE, declarations[path].max_bytes))
            total += len(data)
            if (
                total > MAX_TOTAL
                or len(data) != item["byte_size"]
                or hashlib.sha256(data).hexdigest() != item["sha256"]
            ):
                raise ValueError("Public output binding changed")
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            outputs.append({**item, "text": text})
        observed = evaluation["criteria"]
        if set(observed) != {criterion.id for criterion in task.criteria}:
            raise ValueError("Public criterion membership changed")
        criteria = []
        for criterion in task.criteria:
            earned = observed[criterion.id]
            if type(earned) not in (int, float) or not 0 <= earned <= criterion.possible_points:
                raise ValueError("Invalid public criterion observation")
            criteria.append(
                {
                    "criterion_id": criterion.id,
                    "earned_points": str(earned),
                    "possible_points": str(criterion.possible_points),
                }
            )
        return {"outputs": outputs, "missing": missing, "criteria": criteria}
    finally:
        os.close(root)


def metadata(c, operation_id):
    op = pipeline.record(c, "benchmark_qualification_operations", operation_id)
    build = pipeline.record(c, "benchmark_builds", op["build_id"])
    review = pipeline.record(c, "benchmark_source_reviews", build["review_id"])
    if pipeline.review_status(c, review, build["receipt_id"]):
        raise HTTPException(409, "Qualification source or evaluator review is no longer current")
    if pipeline.current_dependencies(load_trust_policy()) != build["dependencies"]:
        raise HTTPException(409, "Qualification source or runtime binding is no longer current")
    if not one(
        c,
        "SELECT anvil.benchmark_private_access(%s,'benchmark_trace',%s) AS allowed",
        (op["project_id"], op["report_artifact_id"] or op["id"]),
    )["allowed"]:
        raise HTTPException(403, "A current individual evaluation duty is required")
    rows = c.execute(
        "SELECT q.*,r.task_id,t.binding_sha256 FROM anvil.benchmark_operation_results r "
        "JOIN anvil.benchmark_qualifications q ON q.project_id=r.project_id AND q.id=r.qualification_id "
        "JOIN anvil.benchmark_build_tasks t ON t.project_id=r.project_id AND t.build_id=r.build_id AND t.task_id=r.task_id "
        "WHERE r.operation_id=%s ORDER BY r.task_id",
        (operation_id,),
    ).fetchall()
    artifacts = []
    for row in rows:
        if one(
            c,
            "SELECT 1 FROM anvil.benchmark_qualification_events WHERE qualification_id=%s",
            (row["id"],),
        ):
            raise HTTPException(409, "Individual qualification is no longer current")
        artifact = pipeline.private_metadata(c, row["report_artifact_id"])
        if artifact["classification"] != "benchmark_trace":
            raise HTTPException(409, "Invalid qualification evidence class")
        artifacts.append((row, artifact))
    return op, build, artifacts


def project_report(row, artifact, build):
    if type(artifact.get("byte_size")) is not int or not 0 <= artifact["byte_size"] <= 1048576:
        raise ValueError("Qualification evidence exceeds bound")
    raw = read_private_record(artifact)
    if len(raw) > 1048576:
        raise ValueError("Qualification evidence exceeds bound")
    report = json.loads(raw)
    if (
        report.get("origin") != "original_synthetic_software_conformance"
        or report.get("subject_sha256") != build["subject_sha256"]
        or report.get("binding_sha256") != row["binding_sha256"]
    ):
        raise ValueError("Qualification report binding changed")
    trials = []
    for trial in report["native_trials"]:
        for field in (
            "seal_sha256",
            "native_receipt_sha256",
            "qualification_sha256",
            "compiler_source_sha256",
            "adapter_sha256",
        ):
            if not isinstance(trial[field], str) or not re.fullmatch(r"[a-f0-9]{64}", trial[field]):
                raise ValueError("Invalid individual evidence digest")
        for field in ("non_root_readonly_no_egress_cgroups", "fresh_actor"):
            if type(trial["control_checks"][field]) is not bool:
                raise ValueError("Invalid individual evidence control")
        if (
            any(
                type(trial[field]) not in (int, float) or not math.isfinite(trial[field])
                for field in ("points", "possible_points")
            )
            or not 0 <= trial["points"] <= trial["possible_points"]
            or trial["possible_points"] <= 0
            or type(trial["provider_calls"]) is not int
        ):
            raise ValueError("Invalid individual evidence measurement")
        receipt = {k: v for k, v in trial.items() if k != "native_receipt_sha256"}
        if (
            hashlib.sha256(
                json.dumps(receipt, sort_keys=True, allow_nan=False).encode()
            ).hexdigest()
            != trial["native_receipt_sha256"]
        ):
            raise ValueError("Native receipt changed")
        if (
            trial["task_id"] != row["task_id"]
            or trial["binding_sha256"] != row["binding_sha256"]
            or trial["compiled_archive_sha256"] != row["package_sha256"]
            or trial["provider_calls"] != 0
        ):
            raise ValueError("Native trial binding changed")
        public = public_projection(trial.get("public_capture"))
        if public is not None:
            manifest = {
                "files": [
                    {k: item[k] for k in ("path", "sha256", "byte_size")}
                    for item in public["outputs"]
                ],
                "missing": public["missing"],
            }
            if hashlib.sha256(rfc8785.dumps(manifest)).hexdigest() != trial["seal_sha256"]:
                raise ValueError("Public capture seal changed")
        trials.append(
            {
                k: trial[k]
                for k in (
                    "mode",
                    "points",
                    "possible_points",
                    "seal_sha256",
                    "native_receipt_sha256",
                    "provider_calls",
                )
            }
            | {
                "source_hashes": {
                    k: trial[k]
                    for k in ("qualification_sha256", "compiler_source_sha256", "adapter_sha256")
                },
                "controls": {
                    k: trial["control_checks"][k]
                    for k in ("non_root_readonly_no_egress_cgroups", "fresh_actor")
                },
                "public_capture": public,
            }
        )
    if len(trials) != 3 or {trial["mode"] for trial in trials} != {
        "positive",
        "empty",
        "guardrail",
    }:
        raise ValueError("Incomplete individual trial evidence")
    return {
        "qualification_id": str(row["id"]),
        "task_id": row["task_id"],
        "outcome": row["outcome"],
        "report_sha256": artifact["sha256"],
        "subject_sha256": build["subject_sha256"],
        "binding_sha256": row["binding_sha256"],
        "trials": trials,
    }


def public_projection(value):
    """Never spread stored report dictionaries into the public response."""
    if value is None:
        return None
    if set(value) != {"outputs", "missing", "criteria"}:
        raise ValueError("Invalid public capture projection")
    outputs, total = [], 0
    for item in value["outputs"]:
        if (
            set(item) != {"path", "sha256", "byte_size", "text"}
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", item["path"])
            or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])
            or type(item["byte_size"]) is not int
            or not 0 <= item["byte_size"] <= MAX_FILE
        ):
            raise ValueError("Invalid public output projection")
        text = item["text"]
        if text is not None and (
            not isinstance(text, str)
            or len(text.encode()) != item["byte_size"]
            or hashlib.sha256(text.encode()).hexdigest() != item["sha256"]
        ):
            raise ValueError("Public output text changed")
        total += item["byte_size"]
        outputs.append({k: item[k] for k in ("path", "sha256", "byte_size", "text")})
    if (
        total > MAX_TOTAL
        or len(outputs) > 32
        or len(value["missing"]) > 32
        or len(value["criteria"]) > 128
    ):
        raise ValueError("Public capture exceeds bound")
    if any(
        not isinstance(p, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", p)
        for p in value["missing"]
    ):
        raise ValueError("Invalid missing output path")
    criteria = []
    for item in value["criteria"]:
        if set(item) != {"criterion_id", "earned_points", "possible_points"}:
            raise ValueError("Invalid public criterion projection")
        if not isinstance(item["criterion_id"], str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", item["criterion_id"]
        ):
            raise ValueError("Invalid public criterion identity")
        try:
            earned, possible = Decimal(item["earned_points"]), Decimal(item["possible_points"])
            if not earned.is_finite() or not possible.is_finite() or not 0 <= earned <= possible:
                raise ValueError("Invalid public criterion points")
        except (InvalidOperation, TypeError):
            raise ValueError("Invalid public criterion points") from None
        criteria.append({k: item[k] for k in ("criterion_id", "earned_points", "possible_points")})
    paths = [item["path"] for item in outputs]
    ids = [item["criterion_id"] for item in criteria]
    if (
        len(paths) != len(set(paths))
        or len(value["missing"]) != len(set(value["missing"]))
        or set(paths) & set(value["missing"])
        or len(ids) != len(set(ids))
    ):
        raise ValueError("Duplicate or overlapping public capture membership")
    return {"outputs": outputs, "missing": list(value["missing"]), "criteria": criteria}
