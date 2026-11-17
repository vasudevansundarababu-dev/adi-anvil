"""Resumable local build phases, exact profile binding and immutable receipts.

External dispatch is isolated in environment_cloud; this ordinary API module never
discovers credentials or provisions resources. Each successful phase commits once.
"""

from fastapi import HTTPException

from anvil import environment_runtime as runtime
from anvil import environment_validation as validation
from anvil.db import Jsonb, digest, one, uid

PHASES = ("preflight", "load", "validate", "seal")
LOCAL = {"id": "local-reference-v1", "version": "1", "kind": "local", "cloud_enabled": False}


def get(c, identifier):
    row = one(c, "SELECT * FROM anvil.environment_build_jobs WHERE id=%s", (identifier,))
    if not row:
        raise HTTPException(404, "Build job not found in this Project")
    return row | {
        "steps": c.execute(
            "SELECT * FROM anvil.environment_build_steps WHERE job_id=%s ORDER BY created_at,id",
            (identifier,),
        ).fetchall()
    }


def create(c, project, user, environment, profile_id=None):
    version = runtime.get(c, "environment_versions", environment)
    runtime.current_runtime(version)
    if profile_id is not None:
        from anvil.environment_cloud_build import BuildProfile

        profile = one(
            c, "SELECT * FROM anvil.environment_runtime_profiles WHERE id=%s", (profile_id,)
        )
        if not profile or digest(profile["configuration"]) != profile["content_sha256"]:
            raise HTTPException(404, "Exact runtime profile version not found")
        parsed = BuildProfile.model_validate(profile["configuration"]).model_dump()
        return one(
            c,
            "INSERT INTO anvil.environment_build_jobs(id,project_id,environment_id,profile,profile_sha256,state,created_by) VALUES(%s,%s,%s,%s,%s,'waiting_authority',%s) RETURNING *",
            (uid(), project, environment, Jsonb(parsed), digest(parsed), user),
        )
    return one(
        c,
        "INSERT INTO anvil.environment_build_jobs(id,project_id,environment_id,profile,profile_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
        (uid(), project, environment, Jsonb(LOCAL), digest(LOCAL), user),
    )


def advance(c, user, identifier, expected_revision, *, cancel=False):
    row = one(c, "SELECT * FROM anvil.environment_build_jobs WHERE id=%s FOR UPDATE", (identifier,))
    if not row:
        raise HTTPException(404, "Build job not found")
    if row["revision"] != expected_revision:
        raise HTTPException(409, "Build revision changed; reload before resuming")
    if row["state"] in ("completed", "cancelled"):
        return get(c, identifier)
    if cancel and row["state"] == "waiting_authority":
        c.execute(
            "UPDATE anvil.environment_build_jobs SET state='cancelled',cancel_requested=true,revision=revision+1 WHERE id=%s",
            (identifier,),
        )
        return get(c, identifier)
    if digest(row["profile"]) != row["profile_sha256"] or row["profile"] != LOCAL:
        raise HTTPException(
            409, "Exact supported local profile required; cloud dispatch is disabled"
        )
    version = runtime.get(c, "environment_versions", row["environment_id"])
    runtime.current_runtime(version)
    phase = row["phase"]
    if cancel:
        c.execute(
            "UPDATE anvil.environment_build_jobs SET state='cancelled',cancel_requested=true,revision=revision+1 WHERE id=%s",
            (identifier,),
        )
        return get(c, identifier)
    previous = one(
        c,
        "SELECT * FROM anvil.environment_build_steps WHERE job_id=%s AND phase=%s",
        (identifier, phase),
    )
    if previous:
        raise HTTPException(409, "Completed phase cannot be replayed")
    if phase == "preflight":
        content = {
            "environment_manifest_sha256": version["manifest_sha256"],
            "implementation_sha256": runtime.implementation_sha256(),
            "profile_sha256": row["profile_sha256"],
            "provider_calls": 0,
        }
    elif phase == "load":
        instance = runtime.create_instance(c, row["project_id"], user, row["environment_id"])
        content = {
            "instance_id": str(instance["id"]),
            "initial_sha256": instance["initial_sha256"],
            "readback_sha256": digest(runtime.state(c, instance["id"])),
        }
        runtime.close(c, user, instance["id"])
    elif phase == "validate":
        receipt = validation.validate(c, row["project_id"], user, row["environment_id"])
        content = {
            "receipt_id": str(receipt["id"]),
            "receipt_sha256": receipt["content_sha256"],
            "passed": receipt["content"]["passed"],
        }
    else:
        passed = one(
            c,
            "SELECT content FROM anvil.environment_build_steps WHERE job_id=%s AND phase='validate'",
            (identifier,),
        )
        content = {
            "passed": bool(passed and passed["content"]["passed"]),
            "environment_manifest_sha256": version["manifest_sha256"],
            "registration": "explicit_action_required",
            "cloud_provisioned": False,
        }
    c.execute(
        "INSERT INTO anvil.environment_build_steps(id,project_id,job_id,phase,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (uid(), row["project_id"], identifier, phase, Jsonb(content), digest(content), user),
    )
    index = PHASES.index(phase)
    state = (
        "failed"
        if content.get("passed") is False
        else "completed"
        if phase == "seal"
        else "running"
    )
    next_phase = PHASES[min(index + 1, len(PHASES) - 1)]
    c.execute(
        "UPDATE anvil.environment_build_jobs SET state=%s,phase=%s,revision=revision+1 WHERE id=%s",
        (state, next_phase, identifier),
    )
    return get(c, identifier)
