"""Dedicated import worker: durable no-retry generation, validation and publication."""

import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import SecretStr

from anvil import artifacts, auth, providers, workspace_dispatch, workspace_secrets
from anvil.config import ROOT
from anvil.db import Jsonb, audit, digest, one, project_fence, transaction, uid
from anvil.import_codegen import Bundle, generation_prompt, package, validate_bundle
from anvil.import_generation import processing_authorized, source_task


def guarded(c, job, user):
    from anvil.harbor_worker import lease

    project_fence(c, job["project_id"])
    lease(c, job)
    auth.require(auth.project_roles(c, job["project_id"], user), "admin", "rl-engineer")
    revision = one(
        c,
        "SELECT * FROM anvil.executable_import_revisions WHERE id=%s FOR UPDATE",
        (job["target_id"],),
    )
    if not revision or revision["cancel_requested"]:
        raise RuntimeError("cancelled")
    return revision


def finish(job, user, state, report, *, bundle=None, package_data=None):
    from anvil.harbor_worker import lease

    with transaction(job["project_id"], user, worker=state != "ready") as c:
        project_fence(c, job["project_id"])
        lease(c, job)
        row = one(
            c,
            "SELECT * FROM anvil.executable_import_revisions WHERE id=%s FOR UPDATE",
            (job["target_id"],),
        )
        if row["state"] not in {"queued", "generating", "validating"}:
            return
        if row["cancel_requested"] and state == "ready":
            state = "cancelled"
            package_data = None
        if state == "outcome_unknown":
            c.execute(
                "UPDATE anvil.import_generation_calls SET state='unknown' WHERE revision_id=%s AND state='intent'",
                (row["id"],),
            )
        aid = row["bundle_artifact_id"]
        if bundle and not aid and state == "ready":
            aid = artifacts.store(
                c, job["project_id"], json.dumps(bundle.model_dump()).encode(), "hidden_reference"
            )
        pid = None
        if package_data:
            manifest, data = package_data
            family = one(
                c,
                "SELECT * FROM anvil.executable_imports WHERE id=%s FOR UPDATE",
                (row["import_id"],),
            )
            pid = uid()
            artifact_id = artifacts.store(
                c, job["project_id"], data, "hidden_reference", mime="application/zip"
            )
            c.execute(
                "INSERT INTO anvil.harbor_packages(id,project_id,source_id,package_sha256,package_artifact_id,manifest,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    pid,
                    job["project_id"],
                    family["source_id"],
                    hashlib.sha256(data).hexdigest(),
                    artifact_id,
                    Jsonb(manifest),
                    user,
                ),
            )
            c.execute(
                "UPDATE anvil.executable_imports SET ready_revision_id=%s WHERE id=%s",
                (row["id"], row["import_id"]),
            )
        c.execute(
            "UPDATE anvil.executable_import_revisions SET state=%s,report=%s,bundle_artifact_id=%s,package_id=%s,finished_at=now() WHERE id=%s",
            (state, Jsonb(report), aid, pid, row["id"]),
        )
        c.execute(
            "UPDATE anvil.jobs SET status=%s,error_code=%s WHERE id=%s AND lease_token=%s",
            (
                "succeeded"
                if state == "ready"
                else "cancelled"
                if state == "cancelled"
                else "failed",
                None if state == "ready" else state,
                job["id"],
                job["lease_token"],
            ),
        )
        audit(
            c,
            job["project_id"],
            user,
            "import." + state,
            row["id"],
            {"package_id": pid, "model_performance": False},
        )


def native_smoke(task, bundle, revision_id):
    """Actual pinned Harbor Docker trial, no candidate/model/secret access."""
    from anvil.harbor_worker import argv, child_environment

    _, data = package(task, bundle, {}, revision_id)
    with tempfile.TemporaryDirectory(prefix="anvil-import-smoke-") as folder:
        root = Path(folder)
        target = root / "task"
        target.mkdir()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive.extractall(target)  # Only deterministic compiler-owned paths.
        (target / "tests/test.sh").chmod(0o755)
        home = root / "home"
        home.mkdir()
        executable = Path(
            os.environ.get("ANVIL_HARBOR_EXECUTABLE", ROOT / ".local/harbor-venv/bin/harbor")
        )
        if not executable.is_file():
            raise RuntimeError("Pinned Harbor worker is not installed")
        version = subprocess.run(
            [str(executable), "--version"],
            env=child_environment(home),
            capture_output=True,
            timeout=15,
        )
        if version.returncode or "0.25.0" not in version.stdout.decode():
            raise RuntimeError("harbor_version_mismatch")
        result = subprocess.run(
            argv(executable, target, root / "jobs", "empty_output")
            + ["--ek", "auto_mounting=true"],
            env=child_environment(home),
            capture_output=True,
            timeout=120,
        )
        if result.returncode:
            raise RuntimeError("Pinned Harbor package smoke failed")
        trials = list((root / "jobs").glob("check/*/result.json"))
        if len(trials) != 1:
            raise RuntimeError("Harbor smoke trial result is missing")
        observed = json.loads(trials[0].read_text())
        if (
            observed.get("exception_info")
            or observed.get("verifier_result", {}).get("rewards", {}).get("reward") != 0
        ):
            evidence = ROOT / "artifacts/test-runs/import-smoke-failures"
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / (str(revision_id) + ".json")).write_text(json.dumps(observed, indent=2))
            shutil.copytree(root / "jobs", evidence / str(revision_id), dirs_exist_ok=True)
            (evidence / (str(revision_id) + "-runner.txt")).write_bytes(
                (result.stdout + result.stderr)[:65536]
            )
            for log in (root / "jobs").rglob("test-stdout.txt"):
                (evidence / (str(revision_id) + ".txt")).write_bytes(log.read_bytes()[:65536])
            raise RuntimeError("Harbor smoke verifier/output collection failed")
    return {"status": "passed", "adapter": "harbor-0.25.0", "candidate": "nop", "model_calls": 0}


def process(job, *, transport=None):
    """MockTransport is test-only, never configurable from any API request."""
    with transaction(job["project_id"], worker=True) as c:
        owner = one(
            c,
            "SELECT created_by FROM anvil.executable_import_revisions WHERE id=%s",
            (job["target_id"],),
        )
    if not owner:
        raise RuntimeError("Import owner unavailable")
    user = owner["created_by"]
    stopped = threading.Event()
    lease_error = []
    bundle = None
    stage = "validate_source"

    def progress(step):
        with transaction(job["project_id"], user) as c:
            row = guarded(c, job, user)
            c.execute(
                "UPDATE anvil.executable_import_revisions SET report=report || %s WHERE id=%s",
                (Jsonb({"stage": step}), row["id"]),
            )

    def heartbeat():
        with transaction(job["project_id"], user) as c:
            guarded(c, job, user)
            c.execute(
                "UPDATE anvil.jobs SET lease_until=now()+interval '60 seconds' WHERE id=%s AND lease_token=%s",
                (job["id"], job["lease_token"]),
            )
        if lease_error:
            raise RuntimeError("lease_lost")

    def renewal():
        while not stopped.wait(10):
            try:
                heartbeat()
            except Exception:
                lease_error.append(True)
                return

    renewal_thread = threading.Thread(target=renewal, daemon=True)
    renewal_thread.start()
    try:
        progress("validate_source")
        with transaction(job["project_id"], user) as c:
            revision = guarded(c, job, user)
            if revision["state"] not in {"queued", "generating", "validating"}:
                return
            family = one(
                c,
                "SELECT * FROM anvil.executable_imports WHERE id=%s FOR UPDATE",
                (revision["import_id"],),
            )
            source, task = source_task(c, family)
            settings = one(
                c,
                "SELECT * FROM anvil.import_generation_settings WHERE id=%s",
                (revision["settings_id"],),
            )
            config = settings["config"]
            if revision["bundle_artifact_id"]:
                bundle = validate_bundle(
                    task, json.loads(artifacts.read(c, revision["bundle_artifact_id"]))
                )
                c.execute(
                    "UPDATE anvil.executable_import_revisions SET state='validating' WHERE id=%s",
                    (revision["id"],),
                )
            elif one(
                c,
                "SELECT 1 FROM anvil.import_generation_calls WHERE revision_id=%s",
                (revision["id"],),
            ):
                # Restart after durable dispatch intent is always unknown, never re-invoked.
                raise RuntimeError("dispatch_outcome_unknown")
        if bundle is None:
            stage = "generate"
            progress(stage)
            prompt = generation_prompt(task)
            if len(prompt.encode()) > 100000:
                raise ValueError("Generation source exceeds bounded prompt size; split the task")
            reservation = (
                (len(prompt.encode()) + 1024) * config["input_micro_usd_per_million_tokens"]
                + config["max_output_tokens"] * config["output_micro_usd_per_million_tokens"]
                + 999999
            ) // 1000000
            with transaction(job["project_id"], user) as c:
                revision = guarded(c, job, user)
                family = one(
                    c,
                    "SELECT * FROM anvil.executable_imports WHERE id=%s FOR UPDATE",
                    (family["id"],),
                )
                settings = one(
                    c,
                    "SELECT * FROM anvil.import_generation_settings WHERE id=%s",
                    (revision["settings_id"],),
                )
                if settings["revoked_at"]:
                    raise RuntimeError("generation_configuration_revoked")
                if not transport and (
                    os.environ.get("ANVIL_IMPORT_GENERATION_ENABLED") != "true"
                    or not config["enable_paid_generation"]
                ):
                    raise RuntimeError("paid_generation_not_enabled")
                if transport is None and not processing_authorized(
                    c, family, source["source_sha256"]
                ):
                    raise RuntimeError("project_admin_processing_permission_required")
                if datetime.fromisoformat(
                    config["pricing_expires_at"].replace("Z", "+00:00")
                ) <= datetime.now(timezone.utc):
                    raise RuntimeError("generation_pricing_expired")
                count = one(
                    c,
                    "SELECT count(*) n FROM anvil.import_generation_calls WHERE import_id=%s",
                    (family["id"],),
                )["n"]
                if (
                    count >= config["max_calls"]
                    or family["charged_micro_usd"] + family["reserved_micro_usd"] + reservation
                    > family["cap_micro_usd"]
                ):
                    raise RuntimeError("whole_import_cap_exhausted")
                secret = SecretStr(
                    workspace_secrets.load(
                        str(settings["secret_reference"]),
                        {
                            "scope": "installation_import_generation",
                            "settings_id": str(settings["id"]),
                            "provider": config["provider"],
                        },
                    )
                )
                call_id = uid()
                c.execute(
                    "INSERT INTO anvil.import_generation_calls(id,project_id,import_id,revision_id,reservation_micro_usd,state,request_sha256) VALUES(%s,%s,%s,%s,%s,'intent',%s)",
                    (
                        call_id,
                        job["project_id"],
                        family["id"],
                        revision["id"],
                        reservation,
                        digest({"prompt": prompt, "settings_id": str(settings["id"])}),
                    ),
                )
                c.execute(
                    "UPDATE anvil.executable_imports SET reserved_micro_usd=reserved_micro_usd+%s WHERE id=%s",
                    (reservation, family["id"]),
                )
                c.execute(
                    "UPDATE anvil.executable_import_revisions SET state='generating' WHERE id=%s",
                    (revision["id"],),
                )
                audit(
                    c,
                    job["project_id"],
                    user,
                    "import.generation_intent",
                    call_id,
                    {"reservation_micro_usd": reservation, "settings_id": str(settings["id"])},
                )
            # Intent committed BEFORE the sole network attempt. No SDK or application retries.
            result = workspace_dispatch.execute(
                {
                    "provider": config["provider"],
                    "model_id": config["model_id"],
                    "destination": providers.PROVIDERS[config["provider"]][2],
                    "max_output_tokens": config["max_output_tokens"],
                },
                secret,
                providers.ActorRequest(
                    model=config["model_id"],
                    actor_text=prompt,
                    max_output_tokens=config["max_output_tokens"],
                    timeout_seconds=90,
                ),
                transport=transport,
                generation=True,
            )
            usage = result.usage or {}
            from anvil.workspace_execution import billed_usage

            try:
                tokens_in, tokens_out = billed_usage(config["provider"], usage)
                known = (
                    result.model_returned == config["model_id"]
                    and tokens_in <= len(prompt.encode()) + 1024
                    and tokens_out <= config["max_output_tokens"]
                )
            except ValueError:
                known = False
            actual = (
                (
                    tokens_in * config["input_micro_usd_per_million_tokens"]
                    + tokens_out * config["output_micro_usd_per_million_tokens"]
                    + 999999
                )
                // 1000000
                if known
                else None
            )
            known = known and actual <= reservation and result.status != "execution_unknown"
            with transaction(job["project_id"], worker=True) as c:
                from anvil.harbor_worker import lease

                project_fence(c, job["project_id"])
                lease(c, job)
                if known:
                    c.execute(
                        "UPDATE anvil.import_generation_calls SET state='completed',charged_micro_usd=%s,usage=%s WHERE id=%s",
                        (actual, Jsonb(usage), call_id),
                    )
                    c.execute(
                        "UPDATE anvil.executable_imports SET reserved_micro_usd=reserved_micro_usd-%s,charged_micro_usd=charged_micro_usd+%s WHERE id=%s",
                        (reservation, actual, family["id"]),
                    )
                else:
                    c.execute(
                        "UPDATE anvil.import_generation_calls SET state='unknown',usage=%s WHERE id=%s",
                        (Jsonb(usage), call_id),
                    )
            if result.status == "completed" and result.text:
                with transaction(job["project_id"], user) as c:
                    guarded(c, job, user)
                    # Store untrusted raw output privately before parsing; audit never contains code/keys.
                    raw_aid = artifacts.store(
                        c, job["project_id"], result.text.encode(), "hidden_reference"
                    )
                    audit(
                        c,
                        job["project_id"],
                        user,
                        "import.generation_response_retained",
                        revision["id"],
                        {"artifact_id": raw_aid, "dispatch_origin": usage.get("dispatch_origin")},
                    )
            if not known:
                raise RuntimeError("dispatch_outcome_unknown")
            if result.status != "completed" or not result.text:
                raise RuntimeError("generation_" + result.status)
            from anvil.task_parser import json_value

            value = json_value(result.text.encode())
            bundle = Bundle.model_validate(value)
            with transaction(job["project_id"], user) as c:
                revision = guarded(c, job, user)
                aid = artifacts.store(
                    c,
                    job["project_id"],
                    json.dumps(bundle.model_dump()).encode(),
                    "hidden_reference",
                )
                c.execute(
                    "UPDATE anvil.executable_import_revisions SET bundle_artifact_id=%s,state='validating' WHERE id=%s",
                    (aid, revision["id"]),
                )
            # Retain typed but invalid code/mappings for a user to inspect and fix.
            bundle = validate_bundle(task, value)
        stage = "validate_environment_tools_and_grading"
        progress(stage)
        heartbeat()
        from anvil.import_sandbox import validate

        report = validate(task, bundle, heartbeat)
        stage = "package_smoke"
        progress(stage)
        report["harbor_smoke"] = native_smoke(task, bundle, revision["id"])
        heartbeat()
        manifest, data = package(task, bundle, report, revision["id"])
        manifest["source_sha256"] = source["source_sha256"]
        finish(job, user, "ready", report, bundle=bundle, package_data=(manifest, data))
    except Exception as exc:
        code = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
        state = (
            "outcome_unknown"
            if code == "dispatch_outcome_unknown"
            else "cancelled"
            if code == "cancelled"
            else "budget_paused"
            if code == "whole_import_cap_exhausted"
            else "needs_clarification"
            if code.startswith("Needs clarification")
            else "generation_failed"
            if stage == "generate"
            else "environment_unavailable"
            if stage == "validate_environment_tools_and_grading"
            and isinstance(exc, (OSError, subprocess.SubprocessError))
            else "validation_failed"
        )
        # Error strings are our bounded validation diagnostics only; no SDK raw exceptions.
        finish(
            job,
            user,
            state,
            {"stage": stage, "error": code[:2000], "model_performance": False},
            bundle=bundle,
        )
    finally:
        stopped.set()
        renewal_thread.join(timeout=12)


def tick():
    with transaction(worker=True) as c:
        job = one(c, "SELECT * FROM anvil.claim_import_job()")
    if not job:
        return False
    process(job)
    return True
