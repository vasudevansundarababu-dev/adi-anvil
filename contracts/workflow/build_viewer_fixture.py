"""Deterministic draft software-only viewer controls; no approval/Run/score claim."""

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

from anvil.praxis_contract import PraxisTask
from anvil.workflow_contract import WorkflowBinding, WorkflowGraph, graph_hash


def build():
    project = {
        "id": "anvil-graph-viewer-software-controls",
        "version": "1",
        "name": "Graph viewer software controls — draft, not human reviewed",
    }
    entries, files = [], {}
    for identifier, fixture, title in [
        ("GRAPH-CORRECTION", "correction-loop", "Bounded correction loop"),
        ("GRAPH-PARALLEL", "parallel-join", "Parallel definition and join"),
        ("GRAPH-HUMAN-FIXTURE", "scripted-human", "Scripted business-human response"),
    ]:
        definition = WorkflowGraph.model_validate(
            json.loads((Path(__file__).parent / f"{fixture}.fixture.json").read_text())["graph"]
        )
        task = PraxisTask.model_validate(
            {
                "schema_version": "praxis.anvil.task.v1",
                "task_id": identifier,
                "task_version": "1",
                "revision_id": identifier + "-r1",
                "title": "Software control · " + title,
                "objective": "Inspect the explicitly supplied graph. Draft software control, not an authentic Praxis benchmark task or model result.",
                "evidence": [],
                "constraints": [],
                "environment": {"binding": "structured-decision-v1", "initial_state": {}},
                "actions": [
                    {
                        "id": "submit-control",
                        "description": "Declare a software fixture output; native execution is unavailable",
                    }
                ],
                "stages": [
                    {
                        "id": "legacy-control-envelope",
                        "instruction": "Read-only viewer control. Inspect the explicit sidecar graph; no graph was inferred from this text. No native execution or human approval is asserted.",
                        "evidence_ids": [],
                        "completion": "Inspection only; no Run",
                    }
                ],
                "deliverables": [
                    {
                        "id": "control-output",
                        "path": "output.json",
                        "description": "Nonexecuted fixture deliverable",
                    }
                ],
                "rubric": {
                    "criteria": [
                        {
                            "id": "control-complete",
                            "description": "Software control only; not measured",
                            "weight_bps": 10000,
                            "binding": {"kind": "json_equals", "field": "complete", "value": True},
                        }
                    ],
                    "reference_output": {"complete": True},
                },
                "provenance": {
                    "classification": "synthetic",
                    "source": "Explicit repository-authored graph viewer software control",
                    "rights": {
                        "status": "declared",
                        "basis": "Repository-authored software test definition; not reviewed for benchmark execution",
                    },
                    "review": {
                        "status": "draft",
                        "reviewer_ref": "Not human reviewed",
                        "reviewed_revision_id": identifier + "-r1",
                    },
                },
            }
        )
        payload = json.dumps(
            task.model_dump(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        sha = hashlib.sha256(payload.encode()).hexdigest()
        binding = WorkflowBinding(
            schema_version="praxis.anvil.workflow-binding.v1",
            task_id=identifier,
            task_version="1",
            revision_id=task.revision_id,
            payload_sha256=sha,
            graph_sha256=graph_hash(definition),
            graph=definition,
        )
        binding.bind_task(task, sha)
        task_path, graph_path = f"tasks/{identifier}.json", f"workflows/{identifier}.json"
        files[task_path] = {
            "schema_version": "praxis.anvil.export.v1",
            "source": {
                "record_id": identifier,
                "record_hash": sha,
                "project_id": project["id"],
                "client_id": "anvil-software-viewer-control",
                "submission_time": "2026-11-10T00:00:00Z",
                "reviewer_id": None,
                "review_decision_time": None,
            },
            "payload_json": payload,
            "payload_sha256": sha,
        }
        files[graph_path] = binding.model_dump()
        entries.append(
            {"path": task_path, "workflow_path": graph_path, "environment_ids": ["viewer-only"]}
        )
    files["project.json"] = {
        "schema_version": "anvil.task-group-import.v1",
        "source_project": project,
        "environments": [
            {
                "id": "viewer-only",
                "name": "Read-only software viewer control — no execution",
                "version": "1",
                "kind": "software_viewer_control",
                "enforce": False,
            }
        ],
        "tasks": entries,
    }
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, value in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100600 << 16
            archive.writestr(
                info,
                json.dumps(
                    value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode(),
            )
    return result.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    target = parser.parse_args().output
    target.parent.mkdir(parents=True, exist_ok=True)
    data = build()
    target.write_bytes(data)
    print(
        f"Software-only draft viewer fixture: {len(data)} bytes; SHA256 {hashlib.sha256(data).hexdigest()}"
    )
