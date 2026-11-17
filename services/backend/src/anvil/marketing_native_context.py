"""Closed exclusive component-config producer; no launcher/native admission.

Context tokens/clock/file pins are private configuration, not operating rights.
Physical lifecycle, source/import qualification and host binding remain missing.
"""

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from time import monotonic
from uuid import UUID

from anvil.marketing_native_attempt import MarketingAttemptStore, _write_at
from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    PURPOSE,
    _bounded_canonical,
    marketing_native_gate,
)
from anvil.marketing_native_mounts import _context, _opening_context
from anvil.marketing_native_records import (
    STOP,
    MarketingRecordBytesV1,
    _parse_record,
    resolve_marketing_opening_records,
    resolve_marketing_records,
)


def _trial_config(root, claim, *, private=False):
    return {"task": {"path": str(root / "task")}, "trial_name": claim["trial_name"],
            "job_id": claim["job_id"], "trials_dir": str(root / "trials"),
            "agent": {"import_path": "anvil_harbor.marketing:MarketingAgent"},
            "environment": {"import_path": "anvil_harbor.marketing:MarketingEnvironment", "delete": False,
                            "kwargs": {"auto_mounting": False}},
            "verifier": {"import_path": ("anvil_harbor.marketing_private_sdk:MarketingPrivateVerifier" if private
                                           else "anvil_harbor.marketing:MarketingVerifier")}}


def _produce(store, request, records, *, opening=False, private=False):
    if type(records) is not MarketingRecordBytesV1:
        raise ValueError("marketing_exact_root_record_bytes_required")
    value = json.loads(request.canonical_bytes)
    if (records.request_sha256 != hashlib.sha256(request.canonical_bytes).hexdigest()
            or records.manifest_sha256 != value["asset_manifest_sha256"]):
        raise ValueError("marketing_current_context_request_records_required")
    root, claim, plan = (_opening_context if opening else _context)(store, request)
    try:
        task = _parse_record(dict(records.records)["task"])["payload"]["render_assets"]
        if private:
            if not opening:
                raise ValueError('marketing_private_context_requires_explicit_opening')
            from anvil.marketing_native_verifier_renderer import (
                private_context_assets,
                validate_private_program,
            )

            task, private_program = private_context_assets(records)
            program_raw = validate_private_program(private_program)
            if store._read(root, 'private-verifier-program.json') != program_raw:
                raise ValueError('marketing_original_private_program_materialization_required')
        if opening:
            from anvil.marketing_native_opening import validate_opening_program

            if (task['schema_version'] != 'anvil.marketing-render-assets.v2'
                    or validate_opening_program(request, task['operator_program']) != plan['operator_program_sha256']
                    or _bounded_canonical(task['operator_program'], DOCUMENT_CAP)
                    != _bounded_canonical(plan['operator_program'], DOCUMENT_CAP)):
                raise ValueError('marketing_independent_opening_context_program_changed')
        # Current bytes must match the independently resolved renderer inputs,
        # not values supplied by the component or socket peer.
        for key in ("attempt_root", "trial_name", "expected_files", "expected_effective_services", "bounds", "runtime"):
            if _bounded_canonical(task[key], DOCUMENT_CAP) != _bounded_canonical(plan[key], DOCUMENT_CAP):
                raise ValueError("marketing_independent_context_plan_changed")
        operation = _parse_record(records.operation_bytes)
        if (operation.get("request_sha256") != claim["request_sha256"]
                or operation.get("job_id") != claim["job_id"]
                or operation.get("manifest_sha256") != records.manifest_sha256
                or operation.get("purpose") != PURPOSE
                or operation.get("origin") != "independent_operator"
                or datetime.fromisoformat(operation["stop_at"]) != STOP):
            raise ValueError("marketing_bound_context_operation_required")
        lifecycle = plan["bounds"]["lifecycle_seconds"]
        if (type(lifecycle) is not int or not 1 <= lifecycle <= 600
                or lifecycle != value["episode_timeout_seconds"]
                or type(plan["bounds"]["output_bytes"]) is not int
                or not 1 <= plan["bounds"]["output_bytes"] <= DOCUMENT_CAP):
            raise ValueError("marketing_existing_context_bounds_required")
        started = monotonic()
        now = datetime.now(timezone.utc)
        expires = datetime.fromisoformat(operation["expires_at"])
        if expires.tzinfo is None:
            raise ValueError("marketing_context_aware_expiry_required")
        remaining = min(lifecycle, (min(expires, STOP) - now).total_seconds())
        if remaining <= 0:
            raise ValueError("marketing_context_expired")
        deadline = started + remaining
        if private:
            original_control = _parse_record(dict(records.records)['host'])['payload']['control_process']
            control_cutoff = original_control['input_deadline_monotonic']
            if (type(control_cutoff) not in (int, float) or not started < control_cutoff < float('inf')
                    or control_cutoff - started > 600):
                raise ValueError('marketing_original_prestarted_control_cutoff_required')
            deadline = min(deadline, control_cutoff)  # Narrow only, never restart or extend.
        # Per-attempt exclusive claim, before token/config generation and writes.
        # Partial writes retain this claim. No resume can create a new deadline.
        intent = {
            "schema_version": "anvil.marketing-component-context-intent.v1",
            "job_id": claim["job_id"], "request_sha256": claim["request_sha256"],
            "plan_sha256": claim["plan_sha256"], "scope": claim["scope"],
            "deadline_monotonic": deadline, "lifecycle_seconds": lifecycle,
        }
        if opening:
            intent['schema_version'] = 'anvil.marketing-component-context-intent.v2'
            intent['operator_program_sha256'] = plan['operator_program_sha256']
        if private:
            intent['schema_version'] = 'anvil.marketing-component-context-intent.v3'
            intent['private_program_sha256'] = hashlib.sha256(program_raw).hexdigest()
        _write_at(root, "component-context-intent.json", _bounded_canonical(intent, DOCUMENT_CAP))
        with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as stream:
            boot = stream.read(64).strip()
        if str(UUID(boot)) != boot:
            raise ValueError("marketing_context_actual_boot_UUID_required")
        trial = _bounded_canonical(_trial_config(store.parent / claim["trial_name"], claim, private=private), 65536)
        nonce = secrets.token_hex(32)
        context = {
            "schema_version": "anvil.marketing-component-context.v1", "purpose": PURPOSE,
            "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
            "job_id": claim["job_id"], "operation_nonce": nonce, "trial_name": claim["trial_name"],
            "attempt_root": str(store.parent / claim["trial_name"]),
            "image_digest": task["image"]["digest"], "expected_files": plan["expected_files"],
            "expected_effective_services": plan["expected_effective_services"],
            "trial_config_sha256": hashlib.sha256(trial).hexdigest(),
            "deadline_monotonic": deadline, "lifecycle_seconds": lifecycle,
            "output_bytes": plan["bounds"]["output_bytes"],
            "control_socket": "/run/anvil-marketing/" + nonce[:20] + "/control.sock",
            "control_token": secrets.token_hex(32), "boot_id": boot,
        }
        if opening:
            context['schema_version'] = 'anvil.marketing-component-context.v2'
            context['operator_program'] = plan['operator_program']
            context['operator_program_sha256'] = plan['operator_program_sha256']
        raw = _bounded_canonical(context, 65536)
        _write_at(root, "trial.json", trial)
        _write_at(root, "component-context.json", raw)
        if (store._read(root, "trial.json") != trial or store._read(root, "component-context.json") != raw
                or monotonic() >= deadline):
            raise RuntimeError("marketing_context_write_unknown_no_replay")
        receipt = {
            "schema_version": "anvil.marketing-component-context-receipt.v1",
            "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
            "job_id": claim["job_id"], "scope": claim["scope"],
            "context_sha256": hashlib.sha256(raw).hexdigest(),
            "trial_config_sha256": context["trial_config_sha256"],
            "native_admitted": False, "framework_launched": False, "paid_calls": False,
        }
        if opening:
            receipt['schema_version'] = 'anvil.marketing-component-context-receipt.v2'
            receipt['operator_program_sha256'] = plan['operator_program_sha256']
        if private:
            receipt['schema_version'] = 'anvil.marketing-component-context-receipt.v3'
            receipt['private_program_sha256'] = hashlib.sha256(program_raw).hexdigest()
        _write_at(root, "component-context-receipt.json", _bounded_canonical(receipt, DOCUMENT_CAP))
        return receipt  # No token/context bytes returned to a public response.
    finally:
        os.close(root)


def prepare_component_context(request):
    marketing_native_gate()
    records = resolve_marketing_records(request)
    with MarketingAttemptStore() as store:
        return _produce(store, request, records)


def prepare_opening_component_context(request):
    marketing_native_gate()
    records = resolve_marketing_opening_records(request)
    with MarketingAttemptStore() as store:
        return _produce(store, request, records, opening=True)


def prepare_private_component_context(request):
    marketing_native_gate()
    from anvil.marketing_native_private_records import resolve_private_marketing_records

    records = resolve_private_marketing_records(request)
    with MarketingAttemptStore() as store:
        return _produce(store, request, records, opening=True, private=True)
