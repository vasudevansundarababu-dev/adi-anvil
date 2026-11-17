"""Checksum-gated draft SEED handoff adapter; never approval or live admission.

Original files remain in custody. Proposed policy sidecars are retained, not
silently converted into installed evaluator profiles or component-world bindings.
"""

import hashlib
import io
import json
import re
import zipfile

from anvil.benchmark_project_import import parse, safe_path
from anvil.db import digest
from anvil.praxis_contract import PraxisTask


def verify(status, manifest, files):
    if not re.search(rb"^\*\*Status: READY(?:[ .(*]|$)", status, re.M):
        raise ValueError("Published handoff is not READY")
    if len(status) > 65536 or len(manifest) > 65536 or not 1 <= len(files) <= 100:
        raise ValueError("Handoff exceeds bounds")
    expected = {}
    for line in manifest.decode("ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (seed-export/[A-Za-z0-9_./-]+)", line)
        if not match:
            raise ValueError("Invalid handoff manifest")
        checksum, path = match.groups()
        safe_path(path)
        if path in expected:
            raise ValueError("Duplicate manifest path")
        expected[path] = checksum
    if set(files) != set(expected) or sum(map(len, files.values())) > 8388608:
        raise ValueError("Handoff file set differs from manifest")
    for path, body in files.items():
        if len(body) > 2097152 or hashlib.sha256(body).hexdigest() != expected[path]:
            raise ValueError("Handoff checksum mismatch")
    return expected


def packages(status, manifest, files, *, commit):
    verify(status, manifest, files)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Immutable handoff commit required")
    index = json.loads(files["seed-export/index.json"])
    if (
        index.get("fictional") is not True
        or index.get("schema") != "praxis.seed-anvil-handoff.v1-proposed"
    ):
        raise ValueError("Unsupported source index")
    output = []
    for project in index["projects"]:
        folder = safe_path(project["folder"])
        group_id = "seed-" + folder
        entries, wrapped = [], {}
        for item in project["tasks"]:
            path = "seed-export/" + safe_path(item["task"])
            raw = files[path]
            task = PraxisTask.model_validate_json(raw)
            if (
                task.task_id != item["task_id"]
                or digest(json.loads(raw)) != item["task_payload_sha256"]
                or item["review_status"] != "draft"
                or task.provenance.review.status != "draft"
            ):
                raise ValueError("Draft task identity or digest differs")
            destination = "tasks/" + task.task_id + ".json"
            if destination in wrapped:
                raise ValueError("Duplicate task")
            wrapped[destination] = {
                "schema_version": "praxis.anvil.export.v1",
                "source": {
                    "record_id": item["praxis_task_instance_id"],
                    "record_hash": item["task_payload_sha256"],
                    "project_id": group_id,
                    "client_id": "published-fictional-seed-handoff",
                    "submission_time": index["generated_at"],
                    "reviewer_id": None,
                    "review_decision_time": None,
                },
                "payload_json": raw.decode("utf-8"),
                "payload_sha256": hashlib.sha256(raw).hexdigest(),
            }
            entries.append({"path": destination, "environment_ids": ["structured-decision-v1"]})
        proposal = {
            "schema_version": "anvil.task-group-import.v1",
            "source_project": {"id": group_id, "version": "1.0.0", "name": project["project"]},
            "environments": [
                {
                    "id": "structured-decision-v1",
                    "name": "Published structured decision contract",
                    "version": "1.0.0",
                    "kind": "structured-decision",
                }
            ],
            "tasks": entries,
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.json", json.dumps(proposal))
            for name, body in wrapped.items():
                archive.writestr(name, json.dumps(body))
        raw_package = buffer.getvalue()
        content, _ = parse(raw_package)
        output.append(
            {
                "folder": folder,
                "archive": raw_package,
                "content": content,
                "policy_status": "proposed_not_installed",
                "commit": commit,
            }
        )
    return output
