"""Golden physical-request claims use the existing071 group ledger and broker.

No provider execution, key resolution or independently spendable budget exists here.
"""

import os
from datetime import datetime, timezone

from anvil.db import Jsonb, one
from anvil.golden_kyc_paid_contract import PaidKYCManifest
from anvil.praxis_generic_contract import digest


def request_matches_plan(plan, item):
    """A manifest describes existing immutable slots; it cannot add authority."""
    from anvil import workspace_costs

    config = plan["config"]
    model = config["workspace_model"]
    native = config.get("golden_native_binding") or {}
    price = workspace_costs.managed(model["provider"], model["model_id"])
    if not price or not workspace_costs.current(price):
        return False
    return (
        config.get("golden_kyc_paid") is True
        and item.plan_id == str(plan["id"])
        and item.purpose == "actor"
        and item.case_id == native.get("application_id")
        and (item.provider, item.model_id, item.model_version) == (model["provider"], model["model_id"], model["model_id"])
        and item.credential_version_ref == (model.get("credential") or {}).get("version_id")
        and item.input_tokens == 33792
        and item.output_tokens == config["max_output_tokens"]
        and item.input_micro_usd_per_million == workspace_costs.input_bound(price)
        and item.output_micro_usd_per_million == price["output_micro_usd_per_million_tokens"]
        and item.extra_bound_micro_usd == 0
        and item.rate_verification_sha256 == digest(price)
        and datetime.fromisoformat(item.rate_expires_at.replace("Z", "+00:00")) <= datetime.fromisoformat(price["expires_at"].replace("Z", "+00:00"))
        and item.parameters_sha256 == digest({"model": model["model_id"], "max_output_tokens": config["max_output_tokens"], "timeout_seconds": config["request_timeout_seconds"]})
    )


def register(c, group, user, raw):
    manifest = PaidKYCManifest.model_validate(raw)
    if (manifest.group_id, manifest.project_id) != (str(group["id"]), str(group["project_id"])):
        raise ValueError("Exact shared workspace group required")
    if group["state"] != "draft":
        raise ValueError("Bind manifest before admission/launch")
    if manifest.preflight(datetime.now(timezone.utc))["missing"]:
        raise ValueError("Current verified rate/pilot bounds required")
    preparation = group["snapshot"]["preparation"]
    if manifest.aggregate_cap_micro_usd != preparation["aggregate_cap_micro_usd"]:
        raise ValueError("One exact aggregate group cap required")
    if not one(c, "SELECT anvil.benchmark_is_admin(%s,%s) AS allowed", (group["project_id"], user))[
        "allowed"
    ]:
        raise ValueError("Real active project Admin required")
    imported = one(
        c,
        "SELECT * FROM banking.anvil_imports WHERE project_id=%s AND manifest_sha256=%s",
        (group["project_id"], manifest.import_sha256),
    )
    if not imported:
        raise ValueError("Actual Golden import required")
    from anvil.golden_kyc_anvil import validate

    validate(c, imported)
    from anvil.golden_kyc_anvil import source_hash

    if manifest.runtime_sha256 != source_hash() or manifest.evaluator_sha256 != digest(
        imported["manifest"]["evaluators"]
    ):
        raise ValueError("Exact installed runtime and all evaluator bindings required")
    plans = c.execute("SELECT p.* FROM anvil.workspace_execution_models m JOIN anvil.harbor_agent_plans p ON p.id=m.plan_id AND p.project_id=m.project_id WHERE m.group_id=%s AND m.project_id=%s ORDER BY m.ordinal", (group["id"], group["project_id"])).fetchall()
    if not plans or {r.plan_id for r in manifest.requests} != {str(p["id"]) for p in plans}:
        raise ValueError("Manifest must cover exactly this group's existing plans")
    from anvil.golden_kyc_paid_session import task_context

    for plan in plans:
        native = plan["config"].get("golden_native_binding") or {}
        if native.get("import_sha256") != manifest.import_sha256 or native.get("runtime_sha256") != manifest.runtime_sha256:
            raise ValueError("Exact native import and runtime binding required")
        task_context(c, group["project_id"], native.get("resolved_task_id"), native.get("application_id"),
                     execution_data=native.get("execution_data"), resolved_input=native.get("resolved_input"))
        requests = [r for r in manifest.requests if r.plan_id == str(plan["id"])]
        if sorted(r.stage_index for r in requests) != list(range(plan["config"]["max_calls"])) or any(not request_matches_plan(plan, r) for r in requests):
            raise ValueError("Each existing actor slot must match its exact model, case, credential, parameters and managed rate")
    fingerprint = digest(raw)
    old = one(c, "SELECT * FROM anvil.golden_paid_manifests WHERE group_id=%s", (group["id"],))
    if old:
        if old["manifest_sha256"] != fingerprint:
            raise ValueError("Immutable paid manifest conflict")
        return old
    return c.execute(
        "INSERT INTO anvil.golden_paid_manifests(project_id,group_id,subject_hash,manifest,manifest_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
        (group["project_id"], group["id"], group["subject_hash"], Jsonb(raw), fingerprint, user),
    ).fetchone()


def issues(c, plan):
    """Additional admission checks; never turns an unready workspace plan ready."""
    if not plan["config"].get("golden_kyc_paid"):
        return []
    missing = []
    if os.environ.get("ANVIL_GOLDEN_KYC_PAID_ENABLED") != "true":
        missing.append("golden_paid_admission_disabled")
    from anvil.golden_kyc_paid_qualification import installed

    missing.extend(installed()["missing"])
    row = one(
        c,
        "SELECT * FROM anvil.golden_paid_manifests WHERE group_id=%s AND project_id=%s",
        (plan["config"]["workspace_execution_group"], plan["project_id"]),
    )
    if not row or digest(row["manifest"]) != row["manifest_sha256"]:
        return missing + ["golden_paid_manifest_missing_or_changed"]
    pinned = plan["config"].get("golden_paid_manifest_sha256")
    if pinned is not None and row["manifest_sha256"] != pinned:
        missing.append("golden_paid_plan_manifest_changed")
    group = one(c, "SELECT subject_hash FROM anvil.workspace_execution_groups WHERE id=%s AND project_id=%s", (plan["config"]["workspace_execution_group"], plan["project_id"]))
    if not group or row["subject_hash"] != group["subject_hash"]:
        missing.append("golden_paid_group_manifest_binding_changed")
    try:
        manifest = PaidKYCManifest.model_validate(row["manifest"])
        missing.extend(manifest.preflight(datetime.now(timezone.utc))["missing"])
        imported = one(
            c,
            "SELECT * FROM banking.anvil_imports WHERE project_id=%s AND manifest_sha256=%s",
            (plan["project_id"], manifest.import_sha256),
        )
        if not imported:
            missing.append("golden_import_unavailable")
        else:
            from anvil.golden_kyc_anvil import source_hash, validate

            try:
                validate(c, imported)
                if manifest.runtime_sha256 != source_hash() or manifest.evaluator_sha256 != digest(
                    imported["manifest"]["evaluators"]
                ):
                    missing.append("golden_runtime_or_evaluator_binding_changed")
            except Exception:
                missing.append("golden_import_or_evaluator_qualification_invalid")
        slots = sorted(r.stage_index for r in manifest.requests if r.plan_id == str(plan["id"]))
        if any(not request_matches_plan(plan, r) for r in manifest.requests if r.plan_id == str(plan["id"])):
            missing.append("golden_paid_request_configuration_changed")
        if any(r.purpose != "actor" for r in manifest.requests):
            missing.append("golden_initial_run_supports_actor_plus_deterministic_evaluators_only")
        if slots != list(range(plan["config"]["max_calls"])):
            missing.append("golden_all_physical_call_slots_must_be_priced")
    except (ValueError, TypeError, KeyError):
        missing.append("golden_paid_manifest_invalid")
    return sorted(set(missing))


def claim(c, group, plan, invocation, binding, request):
    if os.environ.get("ANVIL_GOLDEN_KYC_PAID_ENABLED") != "true":
        return False
    from anvil.golden_kyc_paid_qualification import installed

    if not installed()["ready"]:
        return False
    record = one(
        c,
        "SELECT * FROM anvil.golden_paid_manifests WHERE group_id=%s AND project_id=%s",
        (group["id"], group["project_id"]),
    )
    if not record or digest(record["manifest"]) != record["manifest_sha256"]:
        return False
    pinned = plan["config"].get("golden_paid_manifest_sha256")
    if record["subject_hash"] != group["subject_hash"] or (pinned is not None and pinned != record["manifest_sha256"]):
        return False
    try:
        manifest = PaidKYCManifest.model_validate(record["manifest"])
        if manifest.preflight(datetime.now(timezone.utc))["missing"]:
            return False
        candidates = [
            r
            for r in manifest.requests
            if r.plan_id == str(plan["id"]) and r.stage_index == invocation["stage_index"]
        ]
        if len(candidates) != 1:
            return False
        item = candidates[0]
        if not request_matches_plan(plan, item):
            return False
        if item.purpose != "actor":
            # Initial KYC grading uses the already separate deterministic engine.
            # No paid judge/retry route is inferred from a priced spare slot.
            return False
        if (item.provider, item.model_id) != (binding["provider"], binding["model_id"]):
            return False
        if request.max_output_tokens != item.output_tokens:
            return False
        # Reuse the existing broker's worst-case input envelope, not a caller's
        # optimistic prompt estimate. Its SDK wrapper may add bounded overhead.
        if item.input_tokens < 32768 + 1024:
            return False
        if str(binding.get("credential", {}).get("version_id")) != item.credential_version_ref:
            return False
        from anvil.workspace_costs import current, input_bound, managed

        price = managed(item.provider, item.model_id)
        if not current(price) or digest(price) != item.rate_verification_sha256:
            return False
        if (item.input_micro_usd_per_million, item.output_micro_usd_per_million) != (
            input_bound(price),
            price["output_micro_usd_per_million_tokens"],
        ):
            return False
        if item.parameters_sha256 != digest(
            {
                "model": request.model,
                "max_output_tokens": request.max_output_tokens,
                "timeout_seconds": request.timeout_seconds,
            }
        ):
            return False
        if item.maximum_micro_usd > invocation["reserved_micro_usd"]:
            return False
    except (ValueError, KeyError, TypeError):
        return False
    return one(
        c,
        "SELECT anvil.claim_golden_paid_call(%s,%s,%s,%s,%s,%s) AS allowed",
        (
            group["id"],
            plan["id"],
            invocation["id"],
            item.id,
            record["manifest_sha256"],
            item.maximum_micro_usd,
        ),
    )["allowed"]
