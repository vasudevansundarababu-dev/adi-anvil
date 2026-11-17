"""Closed role-directory and bounded sealed-capture handoff source.

Owned stop/capture records are consistency inputs, not actual Docker stop or
collection qualification. No container/process/API is launched by this module.
"""

import hashlib
import json
import os
from uuid import UUID

from anvil.marketing_native_attempt import MarketingAttemptStore, _owned, _write_at
from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical, marketing_native_gate
from anvil.marketing_native_records import _parse_record
from anvil.marketing_native_renderer import LIFECYCLE_PHASES

ROLE_UID = ROLE_GID = 10001


def _context(store, request):
    return _context_version(store, request, opening=False)


def _opening_context(store, request):
    return _context_version(store, request, opening=True)


def _context_version(store, request, *, opening):
    if type(opening) is not bool:
        raise ValueError('marketing_explicit_context_version_required')
    read_status = store.read_opening_status if opening else store.read_status
    if read_status(request)["status"] != "files_sealed_ONLY":
        raise ValueError("marketing_known_file_custody_required")
    value = json.loads(request.canonical_bytes)
    job = value["job_id"]
    claim = _parse_record(store._read(store.fd, job + ".materialization-intent.json"))
    root = store._dir(store.fd, claim["trial_name"])
    try:
        try:
            store._read(root, "role-handoff-unknown.json")
        except FileNotFoundError:
            pass
        else:
            raise ValueError("marketing_role_handoff_unknown_no_replay")
        plan = _parse_record(store._read(root, "lifecycle-plan.json"))
        if plan.get("phases") != list(LIFECYCLE_PHASES):
            raise ValueError("marketing_current_prepare_once_lifecycle_required")
        if opening:
            from anvil.marketing_native_opening import validate_opening_program

            if (plan['schema_version'] != 'anvil.marketing-native-lifecycle-plan.v2'
                    or claim['schema_version'] != 'anvil.marketing-materialization-intent.v2'
                    or validate_opening_program(request, plan['operator_program']) != claim['operator_program_sha256']
                    or plan['operator_program_sha256'] != claim['operator_program_sha256']):
                raise ValueError('marketing_exact_opening_materialized_context_required')
        return root, claim, plan
    except BaseException:
        os.close(root)
        raise


def _unknown(root, claim):
    try:
        _write_at(root, "role-handoff-unknown.json", _bounded_canonical({
            "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
            "scope": claim["scope"], "status": "role_handoff_unknown_no_replay",
        }, DOCUMENT_CAP))
    except OSError:
        pass


def _claim_role(root, claim, role):
    _write_at(root, role + "-mount-intent.json", _bounded_canonical({
        "schema_version": "anvil.marketing-role-mount-intent.v1", "role": role,
        "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
        "trial_name": claim["trial_name"], "scope": claim["scope"],
    }, DOCUMENT_CAP))


def _handoff_logs(store, root, claim, role):
    # No recursive ownership, no private parent/attempt/task/control path change.
    names = ("agent", "artifacts/logs/artifacts") if role == "environment" else ("verifier",)
    for name in names:
        fd = store._walk(root, ["trials", claim["trial_name"], *name.split("/")])
        try:
            _owned(os.fstat(fd), store.owner, directory=True, private=True)
            os.fchown(fd, ROLE_UID, ROLE_GID)
            os.fchmod(fd, 0o700)
            info = os.fstat(fd)
            _owned(info, ROLE_UID, directory=True, private=True)
            if info.st_gid != ROLE_GID:
                raise ValueError("marketing_exact_role_group_required")
            os.fsync(fd)
        finally:
            os.close(fd)


def _ready(root, claim, role, extra):
    receipt = {
        "schema_version": "anvil.marketing-role-mount-receipt.v1", "role": role,
        "scope": claim["scope"], "request_sha256": claim["request_sha256"],
        "plan_sha256": claim["plan_sha256"], "trial_name": claim["trial_name"],
        "uid": ROLE_UID, "gid": ROLE_GID, "log_mode": "0700",
        "role_started_by_handoff": False, "native_qualification_granted": False,
        **extra,
    }
    _write_at(root, role + "-mount-receipt.json", _bounded_canonical(receipt, DOCUMENT_CAP))
    return receipt


def _handoff_actor(store, request, *, opening=False):
    root, claim, _ = _context_version(store, request, opening=opening)
    try:
        # Duplicate/partial role claim never enters the mutation handler.
        _claim_role(root, claim, "environment")
        try:
            _handoff_logs(store, root, claim, "environment")
            return _ready(root, claim, "environment", {})
        except BaseException:
            _unknown(root, claim)
            raise
    finally:
        os.close(root)


def _capture_inputs(store, root, claim, plan, *, opening=False):
    actor = _parse_record(store._read(root, "environment-mount-receipt.json"))
    if (actor.get("schema_version") != "anvil.marketing-role-mount-receipt.v1"
            or actor.get("role") != "environment" or actor.get("uid") != ROLE_UID
            or actor.get("gid") != ROLE_GID or actor.get("log_mode") != "0700"
            or actor.get("role_started_by_handoff") is not False
            or actor.get("native_qualification_granted") is not False
            or any(actor.get(key) != claim[key] for key in ("request_sha256", "plan_sha256", "trial_name", "scope"))):
        raise ValueError("marketing_prior_actor_mount_handoff_required")
    entry = _parse_record(store._read(root, "framework-entry.json"))
    stop = _parse_record(store._read(root, "actor-stop.json"))
    identity = {key: claim[key] for key in ("request_sha256", "plan_sha256", "trial_name", "job_id", "scope")}
    if (set(entry) != set(identity) | {"schema_version", "framework_trial_id", "operation_nonce"}
            or entry["schema_version"] != "anvil.marketing-framework-entry.v1"
            or any(entry[key] != value for key, value in identity.items())
            or type(entry["framework_trial_id"]) is not str
            or str(UUID(entry["framework_trial_id"])) != entry["framework_trial_id"]):
        raise ValueError("marketing_exact_framework_entry_required")
    nonce = entry["operation_nonce"]
    if type(nonce) is not str or len(nonce) != 64 or any(c not in "0123456789abcdef" for c in nonce):
        raise ValueError("marketing_exact_operation_nonce_required")
    fields = {"schema_version", "request_sha256", "plan_sha256", "framework_trial_id",
              "operation_nonce", "state", "native_stop_receipt_sha256", "actor_output_sha256", "collection_receipt_sha256"}
    if opening:
        fields |= {'scope_kind', 'operator_program_sha256', 'source_nomination_sha256'}
    if (set(stop) != fields
            or stop["schema_version"] != ('anvil.marketing-actor-stop.v2' if opening else 'anvil.marketing-actor-stop.v1')
            or stop["state"] != "actor_stopped_observed"
            or any(stop[key] != entry[key] for key in ("request_sha256", "plan_sha256", "framework_trial_id", "operation_nonce"))):
        raise ValueError("marketing_bound_actor_stop_record_required")
    if opening:
        from anvil.marketing_native_actor_capture import KIND, validate_actor_capture_files
        from anvil.marketing_native_world_binding import retained_source_nomination

        if (stop['scope_kind'] != KIND or stop['operator_program_sha256'] != plan['operator_program_sha256']
                or stop['source_nomination_sha256'] != retained_source_nomination(store, root)
                or hashlib.sha256(validate_actor_capture_files(store, root, claim, plan)).hexdigest()
                != stop['native_stop_receipt_sha256']):
            raise ValueError('marketing_original_opening_actor_capture_changed')
    for key in ("native_stop_receipt_sha256", "actor_output_sha256", "collection_receipt_sha256"):
        pin = stop[key]
        if type(pin) is not str or len(pin) != 64 or any(c not in "0123456789abcdef" for c in pin):
            raise ValueError("marketing_exact_capture_pin_required")
    output = store._read(root, "captured-actor-output.json")
    receipt = store._read(root, "captured-collection-receipt.json")
    if (not 0 < len(output) <= plan["bounds"]["output_bytes"]
            or not 0 < len(receipt) <= plan["bounds"]["receipt_bytes"]
            or hashlib.sha256(output).hexdigest() != stop["actor_output_sha256"]
            or hashlib.sha256(receipt).hexdigest() != stop["collection_receipt_sha256"]):
        raise ValueError("marketing_exact_bounded_capture_required")
    public = _parse_record(output)
    if (not {"outcome", "weekly_review_refs", "evidence_refs"} <= set(public)
            or set(public) - {"outcome", "weekly_review_refs", "evidence_refs", "closeout_report_ref", "hold_reason"}
            or public["outcome"] not in {"campaign_closed", "awaiting_authority"}
            or any(type(public[key]) is not str or len(public[key]) > 2000
                   for key in ("closeout_report_ref", "hold_reason") if key in public)
            or any(type(public[key]) is not list or any(type(ref) is not str or len(ref) > 2000 for ref in public[key])
                   for key in ("weekly_review_refs", "evidence_refs"))):
        raise ValueError("marketing_public_capture_projection_required")
    metadata = _parse_record(receipt)
    if (set(metadata) != {"schema_version", "request_sha256", "framework_trial_id", "operation_nonce",
                          "actor_output_sha256", "graph_receipt_sha256", "diagnostic_only"}
            or metadata["schema_version"] != "anvil.marketing-collection-capture.v1"
            or metadata["diagnostic_only"] is not True
            or any(metadata[key] != entry[key] for key in ("request_sha256", "framework_trial_id", "operation_nonce"))
            or metadata["actor_output_sha256"] != stop["actor_output_sha256"]
            or type(metadata["graph_receipt_sha256"]) is not str
            or len(metadata["graph_receipt_sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in metadata["graph_receipt_sha256"])):
        raise ValueError("marketing_bound_diagnostic_collection_required")
    return output, receipt, stop


def _handoff_verifier(store, request, *, opening=False):
    root, claim, plan = _context_version(store, request, opening=opening)
    try:
        # All immutable capture checks before the one-way permission claim.
        output, receipt, stop = _capture_inputs(store, root, claim, plan, opening=opening)
        _claim_role(root, claim, "tests")
        try:
            sealed = store._walk(root, ["sealed"])
            try:
                _owned(os.fstat(sealed), store.owner, directory=True, private=True)
                if os.listdir(sealed):
                    raise ValueError("marketing_fresh_sealed_capture_required")
                _write_at(sealed, "actor-output.json", output, mode=0o444)
                _write_at(sealed, "collection-receipt.json", receipt, mode=0o444)
                os.fchmod(sealed, 0o555)
                os.fsync(sealed)
            finally:
                os.close(sealed)
            _handoff_logs(store, root, claim, "tests")
            return _ready(root, claim, "tests", {
                "actor_output_sha256": stop["actor_output_sha256"],
                "collection_receipt_sha256": stop["collection_receipt_sha256"],
                "native_stop_receipt_sha256": stop["native_stop_receipt_sha256"],
                "sealed_mode": "0555", "sealed_files_mode": "0444",
            })
        except BaseException:
            _unknown(root, claim)
            raise
    finally:
        os.close(root)


def handoff_actor_mounts(request):
    marketing_native_gate()
    with MarketingAttemptStore() as store:
        return _handoff_actor(store, request)


def handoff_verifier_mounts(request):
    marketing_native_gate()
    with MarketingAttemptStore() as store:
        return _handoff_verifier(store, request)
