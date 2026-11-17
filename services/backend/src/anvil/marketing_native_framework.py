"""Closed once-recorded framework entry from the bound child control connection.

Retains child-reported SDK UUID against root bindings. It does not qualify loaded
SDK code, create a trial, admit native work or fabricate a framework result.
"""

import hashlib
import os
from time import monotonic
from uuid import UUID

from anvil.marketing_native_attempt import MarketingAttemptStore, _write_at
from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical, marketing_native_gate
from anvil.marketing_native_collector import EVENT_FIELDS
from anvil.marketing_native_mounts import _context, _context_version
from anvil.marketing_native_reconcile import _context_status_version
from anvil.marketing_native_records import _parse_record


def _record(store, request, raw, *, opening=False):
    if type(raw) is not bytes or not 0 < len(raw) <= 4096:
        raise ValueError("marketing_framework_event_capacity")
    event = _parse_record(raw)
    root, claim, plan = _context_version(store, request, opening=opening)
    try:
        retained = _context_status_version(store, root, claim, plan, opening=opening)
        if retained["same_boot_observed"] is not True or retained["deadline_elapsed_observed"] is not False:
            raise ValueError("marketing_current_framework_context_required")
        context_raw = store._read(root, "component-context.json")
        context = _parse_record(context_raw)
        binding = _parse_record(store._read(root, "host-control-binding.json"))
        if (set(event) != EVENT_FIELDS or event.get("schema_version") != "anvil.marketing-component-event.v1"
                or event.get("event") != "framework_entry" or event.get("role") != "environment"
                or event.get("session_id") != claim["trial_name"] + "__env"
                or any(event.get(key) != claim[key] for key in ("job_id", "request_sha256", "plan_sha256"))
                or event.get("operation_nonce") != context["operation_nonce"]
                or type(event.get("framework_trial_id")) is not str
                or str(UUID(event["framework_trial_id"])) != event["framework_trial_id"]
                or binding.get("schema_version") != ("anvil.marketing-host-control-binding.v2" if opening
                                                       else "anvil.marketing-host-control-binding.v1")
                or binding.get("context_sha256") != hashlib.sha256(context_raw).hexdigest()
                or any(binding.get(key) != claim[key] for key in ("job_id", "request_sha256", "plan_sha256", "scope"))):
            raise ValueError("marketing_once_bound_framework_identity_required")
        if opening and binding.get('operator_program_sha256') != plan['operator_program_sha256']:
            raise ValueError('marketing_opening_framework_program_changed')
        entry = {"schema_version": "anvil.marketing-framework-entry.v1",
                 **{key: claim[key] for key in ("request_sha256", "plan_sha256", "trial_name", "job_id", "scope")},
                 "framework_trial_id": event["framework_trial_id"], "operation_nonce": context["operation_nonce"]}
        if monotonic() >= context["deadline_monotonic"]:
            raise TimeoutError("marketing_framework_entry_deadline")
        _write_at(root, "framework-entry-intent.json", _bounded_canonical({
            "schema_version": "anvil.marketing-framework-entry-intent.v1",
            "entry_sha256": hashlib.sha256(_bounded_canonical(entry, DOCUMENT_CAP)).hexdigest(),
            "host_binding_sha256": hashlib.sha256(store._read(root, "host-control-binding.json")).hexdigest(),
            "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
        }, DOCUMENT_CAP))
        entry_raw = _bounded_canonical(entry, DOCUMENT_CAP)
        _write_at(root, "framework-entry.json", entry_raw)
        if store._read(root, "framework-entry.json") != entry_raw or monotonic() >= context["deadline_monotonic"]:
            raise RuntimeError("marketing_framework_entry_unknown_no_replay")
        return {**event, "status": "recorded"}
    finally:
        os.close(root)


def record_framework_entry(request, raw_event, writer):
    marketing_native_gate()
    from anvil.marketing_native_control import _binding

    with MarketingAttemptStore() as store:
        root, claim, _ = _context(store, request)
        try:
            _binding(store, root, claim, writer)
        finally:
            os.close(root)
        return _record(store, request, raw_event)
