"""Closed fixed collector handlers over retained, identity-bound capture bytes.

These handlers neither stop containers nor produce a physical capture. Existing
root-owned stop/capture metadata is consistency evidence only; actual producer
admission, transport authentication and runtime qualification remain missing.
"""

import hashlib
import os
import stat

from anvil.marketing_native_attempt import MarketingAttemptStore, _owned, _write_at
from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical, marketing_native_gate
from anvil.marketing_native_mounts import _capture_inputs, _context_version
from anvil.marketing_native_records import _parse_record
from anvil.marketing_native_start import _check

EVENT_FIELDS = frozenset({
    "schema_version", "event", "job_id", "request_sha256", "plan_sha256",
    "operation_nonce", "framework_trial_id", "session_id", "role",
})


def _bound_event(store, root, claim, raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 4096:
        raise ValueError("marketing_fixed_collector_event_capacity")
    event = _parse_record(raw)
    entry = _parse_record(store._read(root, "framework-entry.json"))
    expected_role = {"artifact_stat": "environment", "copy_output": "environment", "collect": "tests"}
    if (set(event) != EVENT_FIELDS or event.get("schema_version") != "anvil.marketing-component-event.v1"
            or event.get("event") not in expected_role
            or any(event.get(key) != claim[key] for key in ("job_id", "request_sha256", "plan_sha256"))
            or any(event.get(key) != entry.get(key) for key in ("operation_nonce", "framework_trial_id"))
            or event.get("role") != expected_role[event["event"]]
            or event.get("session_id") != claim["trial_name"] + (
                "__env" if event["role"] == "environment" else "__verifier__trial")):
        raise ValueError("marketing_bound_fixed_collector_event_required")
    return event


def _copy_output(store, root, claim, output, event):
    # Exclusive intent precedes destination creation. A lost response or partial
    # write never authorizes another copy; read-only reconciliation stays separate.
    identity = {key: event[key] for key in EVENT_FIELDS - {"schema_version", "event"}}
    pin = hashlib.sha256(output).hexdigest()
    _write_at(root, "copy-output-intent.json", _bounded_canonical({
        "schema_version": "anvil.marketing-output-copy-intent.v1", **identity,
        "actor_output_sha256": pin, "scope": claim["scope"],
    }, DOCUMENT_CAP))
    target = None
    try:
        target = store._walk(root, ["trials", claim["trial_name"], "artifacts"])
        info = os.fstat(target)
        _owned(info, store.owner, directory=True, private=True)
        if stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("marketing_private_sdk_artifact_parent_required")
        _write_at(target, "agent-output.json", output)
        if store._read(target, "agent-output.json") != output:
            raise ValueError("marketing_actual_artifact_copy_changed")
        _write_at(root, "copy-output-receipt.json", _bounded_canonical({
            "schema_version": "anvil.marketing-output-copy-receipt.v1", **identity,
            "actor_output_sha256": pin, "scope": claim["scope"],
            "status": "exclusive_retained_bytes_copied", "native_qualified": False,
        }, DOCUMENT_CAP))
    finally:
        if target is not None:
            os.close(target)
    return {"artifact_sha256": pin}


def _handle(store, request, raw, *, opening=False):
    root, claim, plan = _context_version(store, request, opening=opening)
    try:
        event = _bound_event(store, root, claim, raw)
        # Validates framework identity, exact public capture schema, bounded bytes,
        # and matching actor-stop/capture hashes. It cannot certify physical stop.
        output, receipt, _ = _capture_inputs(store, root, claim, plan, opening=opening)
        if event["event"] == "artifact_stat":
            extra = {"artifact_kind": "file"}
        elif event["event"] == "copy_output":
            extra = _copy_output(store, root, claim, output, event)
        else:
            # Both actual profile records, current verifier permissions and exact
            # sealed bytes must agree before diagnostic custody can be reported.
            _check(store, request, role="tests", stage="before_collection", opening=opening)
            extra = {"diagnostic_reward": 1,
                     "collection_sha256": hashlib.sha256(receipt).hexdigest(),
                     "model_performance_validated": False}
        return {**event, "status": "recorded", **extra}
    finally:
        os.close(root)


def handle_retained_collection(request, raw_event):
    """Fixed root handler only; no caller-selected source, target or callback."""
    marketing_native_gate()
    with MarketingAttemptStore() as store:
        return _handle(store, request, raw_event)
