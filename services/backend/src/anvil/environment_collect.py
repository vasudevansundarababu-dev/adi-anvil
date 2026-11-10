"""Host-owned collect-before-close boundary. No client-supplied trusted evidence."""

from time import perf_counter_ns

from anvil import environment_runtime as runtime
from anvil.db import Jsonb, digest, uid


def capture_attempt(c, run, user, member, candidate, repetition):
    attempt_id = uid()
    project = run["project_id"]

    # Commit the attempt before any external dispatch. A lost process may leave
    # a retained running/uncertain attempt, never an invisible native operation.
    def persist():
        c.commit()
        c.execute(
            "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
            (str(project), str(user)),
        )

    from anvil.db import one

    parent = one(
        c,
        "SELECT a.id FROM anvil.environment_run_lineage l JOIN anvil.environment_attempts a ON a.run_id=l.parent_run_id WHERE l.run_id=%s AND a.environment_id=%s AND a.model_key=%s AND a.repetition=%s",
        (run["id"], member["environment_id"], candidate, repetition),
    )

    c.execute(
        "INSERT INTO anvil.environment_attempts(id,project_id,run_id,binding_id,environment_id,model_key,repetition,created_by,parent_attempt_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            attempt_id,
            project,
            run["id"],
            member["binding_id"],
            member["environment_id"],
            candidate,
            repetition,
            user,
            parent["id"] if parent else None,
        ),
    )
    instance = runtime.create_instance(c, project, user, member["environment_id"])
    c.execute(
        "UPDATE anvil.environment_attempts SET state='running',instance_id=%s WHERE id=%s",
        (instance["id"], attempt_id),
    )
    persist()
    started = perf_counter_ns()
    results = []
    installed = None

    def act_and_collect():
        if candidate == "configured-tools-v1":
            for action in member["actions"]:
                from anvil.environment_execution import cancelled

                if cancelled(c, run["id"]):
                    raise ValueError("environment_run_cancelled")
                if installed is not None:
                    result = installed.step(action["operation"], action["arguments"], 0)
                elif run["snapshot"]["harness"] == "openenv-local-v1":
                    from anvil.environment_openenv import LocalEpisode, Step

                    result = LocalEpisode(c, user, instance["id"]).step(
                        Step(
                            operation=action["operation"],
                            arguments=action["arguments"],
                            expected_generation=0,
                        )
                    )["observation"]
                else:
                    result = runtime.execute(
                        c, user, instance["id"], action["operation"], action["arguments"], 0
                    )
                results.append(result)
                import json

                if len(json.dumps(results, allow_nan=False).encode()) > 65536:
                    raise ValueError("Bounded agent output exceeded64KiB; no silent truncation")
                persist()
        captured = runtime.export_evidence(c, user, instance["id"])
        persist()
        return {"tool_results": results}, captured

    native = None
    try:
        if run["snapshot"]["harness"] == "openenv-0.12-local-v1":
            from anvil.environment_openenv import InstalledEpisode

            installed = InstalledEpisode(
                project,
                user,
                member["environment_id"],
                instance["id"],
                member["environment_manifest_sha256"],
                member["pack_sha256"],
            )
        if run["snapshot"]["harness"] == "harbor-host-mediated-v1":
            import os

            from anvil.config import ROOT
            from anvil.environment_harbor import execute
            from anvil.environment_temp import workspace

            home = workspace("anvil-env-native-")
            native = execute(
                home / "attempt",
                {
                    "task_id": member["task_id"],
                    "environment_manifest_sha256": member["environment_manifest_sha256"],
                    "origin": "explicit_software_tool_script",
                },
                act_and_collect,
                host=os.environ.get("ANVIL_HARBOR_DOCKER_HOST", ""),
                python=os.environ.get(
                    "ANVIL_ENVIRONMENT_HARBOR_PYTHON", str(ROOT / ".local/harbor-venv/bin/python")
                ),
            )
            receipt = native["trusted_receipt"]
        else:
            _, receipt = act_and_collect()
    except Exception as exc:
        c.rollback()
        c.execute(
            "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
            (str(project), str(user)),
        )
        partial = runtime.export_evidence(c, user, instance["id"])
        c.execute(
            "UPDATE anvil.environment_attempts SET state=%s,evidence_receipt_id=%s,error_code=%s WHERE id=%s",
            (
                "uncertain"
                if run["snapshot"]["harness"]
                in ("harbor-host-mediated-v1", "openenv-0.12-local-v1")
                else "cancelled"
                if str(exc) == "environment_run_cancelled"
                else "failed",
                partial["id"],
                "environment_attempt_incomplete",
                attempt_id,
            ),
        )
        runtime.close(c, user, instance["id"])
        persist()
        raise ValueError("environment_attempt_incomplete; retained evidence available") from exc
    finally:
        if installed is not None:
            installed.close()
    verify_receipt(receipt, member, instance["id"])
    capture = {
        "attempt_id": attempt_id,
        "instance_id": str(instance["id"]),
        "trusted_evidence_receipt_id": str(receipt["id"]),
        "trusted_evidence_sha256": receipt["content_sha256"],
        "environment_manifest_sha256": member["environment_manifest_sha256"],
        "pack_sha256": member["pack_sha256"],
        "task_payload_sha256": member["task_payload_sha256"],
        "output": {"tool_results": results},
        "events": receipt["content"]["events"],
        "facts": {},
        "complete_trace": True,
        "attack_present": False,
        "duration_ms": (perf_counter_ns() - started) / 1000000,
        "origin": "environment_software_tool_execution",
        "provider_calls": 0,
        "model_performance": False,
        "native_isolation": False,
        "collector_version": "environment-collector-v1",
        "harness": run["snapshot"]["harness"],
        "native_harbor": {k: v for k, v in native.items() if k != "trusted_receipt"}
        if native
        else None,
        "openenv_adapter": installed.metadata if installed else None,
    }
    c.execute(
        "INSERT INTO anvil.benchmark_run_cells(id,project_id,run_id,model_key,task_key,environment_key,repetition,capture,capture_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            uid(),
            project,
            run["id"],
            candidate,
            member["task_id"],
            member["environment_id"],
            repetition,
            Jsonb(capture),
            digest(capture),
        ),
    )
    c.execute(
        "UPDATE anvil.environment_attempts SET state='captured',evidence_receipt_id=%s WHERE id=%s",
        (receipt["id"], attempt_id),
    )
    runtime.close(c, user, instance["id"])
    persist()
    return capture


def verify_receipt(receipt, member, instance):
    import base64
    import hashlib

    content = receipt["content"]
    if (
        receipt["content_sha256"] != digest(content)
        or str(receipt["instance_id"]) != str(instance)
        or content["environment_manifest_sha256"] != member["environment_manifest_sha256"]
        or content["pack_sha256"] != member["pack_sha256"]
    ):
        raise ValueError("collector_scope_or_hash_mismatch")
    for artifact in content["artifacts"]:
        raw = base64.b64decode(artifact["bytes_base64"], validate=True)
        if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
            raise ValueError("artifact_hash_mismatch")
    return {
        "status": "collected",
        "artifact_count": len(content["artifacts"]),
        "receipt_sha256": receipt["content_sha256"],
    }


def harbor_collection(manifest, *, required):
    """Validate Harbor's actual collection entries, not merely trial success.

    Normalized input is constructed by environment_harbor from the pinned native
    manifest. Missing/failed/skipped/empty required artifacts fail closed.
    """
    if not isinstance(manifest, list) or len(manifest) > 100:
        raise ValueError("invalid_collection_manifest")
    entries = {}
    for item in manifest:
        if not isinstance(item, dict) or set(item) - {
            "name",
            "status",
            "byte_size",
            "sha256",
            "service",
        }:
            raise ValueError("invalid_collection_entry")
        if item["name"] in entries:
            raise ValueError("duplicate_collection_entry")
        entries[item["name"]] = item
    gaps = [
        name
        for name in required
        if name not in entries
        or entries[name].get("status") != "collected"
        or type(entries[name].get("byte_size")) is not int
        or entries[name]["byte_size"] <= 0
        or not __import__("re").fullmatch("[a-f0-9]{64}", entries[name].get("sha256", ""))
    ]
    return {"complete": not gaps, "missing_or_failed": gaps, "entries": manifest}
