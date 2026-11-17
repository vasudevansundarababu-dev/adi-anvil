"""Closed read-only context/copy reconciliation; never recovery/retry authority."""

import hashlib
import math
import os
import re
import stat
from time import monotonic

from anvil.marketing_native_attempt import MarketingAttemptStore, _owned
from anvil.marketing_native_boundary import _bounded_canonical, marketing_native_gate
from anvil.marketing_native_collector import EVENT_FIELDS
from anvil.marketing_native_context import _trial_config
from anvil.marketing_native_mounts import _capture_inputs, _context_version, _opening_context
from anvil.marketing_native_records import _parse_record


def _unknown():
    return {"status": "unknown_or_incomplete_no_replay", "native_qualified": False,
            "replay_permitted": False, "execution_permitted": False}


def _context_status(store, root, claim, plan):
    return _context_status_version(store, root, claim, plan, opening=False)


def _opening_context_status(store, root, claim, plan):
    return _context_status_version(store, root, claim, plan, opening=True)


def _context_status_version(store, root, claim, plan, *, opening):
    intent = _parse_record(store._read(root, "component-context-intent.json"))
    receipt = _parse_record(store._read(root, "component-context-receipt.json"))
    raw = store._read(root, "component-context.json")
    context = _parse_record(raw)
    trial = store._read(root, "trial.json")
    identity = {key: claim[key] for key in ("job_id", "request_sha256", "plan_sha256", "scope")}
    context_fields = {"schema_version", "purpose", "request_sha256", "plan_sha256", "job_id", "operation_nonce",
                      "trial_name", "attempt_root", "image_digest", "expected_files", "expected_effective_services",
                      "trial_config_sha256", "deadline_monotonic", "lifecycle_seconds", "output_bytes",
                      "control_socket", "control_token", "boot_id"}
    extra = {'operator_program_sha256'} if opening else set()
    private = opening and intent.get('schema_version') == 'anvil.marketing-component-context-intent.v3'
    if private:
        extra.add('private_program_sha256')
        from anvil.marketing_native_verifier_renderer import validate_private_program

        program = store._read(root, 'private-verifier-program.json')
        if (validate_private_program(_parse_record(program)) != program
                or hashlib.sha256(program).hexdigest() != intent['private_program_sha256']):
            raise ValueError('marketing_original_private_context_program_changed')
    if opening:
        context_fields |= {'operator_program', 'operator_program_sha256'}
        if (plan.get('schema_version') != 'anvil.marketing-native-lifecycle-plan.v2'
                or claim.get('schema_version') != 'anvil.marketing-materialization-intent.v2'
                or hashlib.sha256(_bounded_canonical(plan, 1048576)).hexdigest() != claim['plan_sha256']
                or context.get('operator_program') != plan['operator_program']
                or hashlib.sha256(_bounded_canonical(plan['operator_program'], 1048576)).hexdigest()
                != plan['operator_program_sha256']
                or any(item.get('operator_program_sha256') != plan['operator_program_sha256']
                       for item in (claim, context, intent, receipt))):
            raise ValueError('marketing_opening_context_program_reconciliation_mismatch')
    if (set(context) != context_fields or context["schema_version"] != (
            'anvil.marketing-component-context.v2' if opening else 'anvil.marketing-component-context.v1')
            or context["purpose"] != "marketing_campaign_graph_v1"
            or type(context["deadline_monotonic"]) not in (int, float)
            or not math.isfinite(context["deadline_monotonic"])
            or type(context["lifecycle_seconds"]) is not int or not 1 <= context["lifecycle_seconds"] <= 600
            or type(context["output_bytes"]) is not int or context["output_bytes"] != plan["bounds"]["output_bytes"]
            or any(type(context[key]) is not str or not re.fullmatch(r"[a-f0-9]{64}", context[key])
                   for key in ("operation_nonce", "control_token"))
            or context["control_socket"] != "/run/anvil-marketing/" + context["operation_nonce"][:20] + "/control.sock"
            or set(intent) != set(identity) | {"schema_version", "deadline_monotonic", "lifecycle_seconds"} | extra
            or intent["schema_version"] != ('anvil.marketing-component-context-intent.v3' if private else
                                            'anvil.marketing-component-context-intent.v2' if opening
                                            else 'anvil.marketing-component-context-intent.v1')
            or any(intent[key] != value for key, value in identity.items())
            or intent["lifecycle_seconds"] != plan["bounds"]["lifecycle_seconds"]
            or any(context.get(key) != intent[key] for key in ("deadline_monotonic", "lifecycle_seconds"))
            or any(context.get(key) != claim[key] for key in ("job_id", "request_sha256", "plan_sha256", "trial_name"))
            or context.get("attempt_root") != str(store.parent / claim["trial_name"])
            or context.get("expected_files") != plan["expected_files"]
            or context.get("expected_effective_services") != plan["expected_effective_services"]
            or context.get("trial_config_sha256") != hashlib.sha256(trial).hexdigest()
            or trial != _bounded_canonical(_trial_config(store.parent / claim["trial_name"], claim, private=private), 65536)):
        raise ValueError("marketing_context_reconciliation_mismatch")
    expected = {"schema_version": "anvil.marketing-component-context-receipt.v1", **identity,
                "context_sha256": hashlib.sha256(raw).hexdigest(),
                "trial_config_sha256": hashlib.sha256(trial).hexdigest(),
                "native_admitted": False, "framework_launched": False, "paid_calls": False}
    if opening:
        expected['schema_version'] = 'anvil.marketing-component-context-receipt.v2'
        expected['operator_program_sha256'] = plan['operator_program_sha256']
    if private:
        expected['schema_version'] = 'anvil.marketing-component-context-receipt.v3'
        expected['private_program_sha256'] = intent['private_program_sha256']
    if _bounded_canonical(receipt, 65536) != _bounded_canonical(expected, 65536):
        raise ValueError("marketing_context_receipt_reconciliation_mismatch")
    # Report custody only. Expiry/boot observations can invalidate reuse, never
    # make this configuration an executable/admitted launch candidate.
    with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as stream:
        boot = stream.read(64).strip()
    return {**_unknown(), "status": "context_bytes_retained_ONLY",
            "context_sha256": expected["context_sha256"],
            "trial_config_sha256": expected["trial_config_sha256"],
            "same_boot_observed": context.get("boot_id") == boot,
            "deadline_elapsed_observed": monotonic() >= context["deadline_monotonic"]}


def _copy_status(store, root, claim, plan, *, opening=False):
    intent = _parse_record(store._read(root, "copy-output-intent.json"))
    receipt = _parse_record(store._read(root, "copy-output-receipt.json"))
    entry = _parse_record(store._read(root, "framework-entry.json"))
    output, _, _ = _capture_inputs(store, root, claim, plan, opening=opening)
    fields = EVENT_FIELDS - {"schema_version", "event"}
    identity = {key: intent.get(key) for key in fields}
    if (set(intent) != fields | {"schema_version", "actor_output_sha256", "scope"}
            or intent["schema_version"] != "anvil.marketing-output-copy-intent.v1"
            or any(identity[key] != claim[key] for key in ("job_id", "request_sha256", "plan_sha256"))
            or any(identity[key] != entry[key] for key in ("operation_nonce", "framework_trial_id"))
            or identity["role"] != "environment" or identity["session_id"] != claim["trial_name"] + "__env"
            or intent["scope"] != claim["scope"]
            or intent["actor_output_sha256"] != hashlib.sha256(output).hexdigest()
            or not re.fullmatch(r"[a-f0-9]{64}", intent["actor_output_sha256"])):
        raise ValueError("marketing_copy_intent_reconciliation_mismatch")
    expected = {"schema_version": "anvil.marketing-output-copy-receipt.v1", **identity,
                "actor_output_sha256": intent["actor_output_sha256"], "scope": claim["scope"],
                "status": "exclusive_retained_bytes_copied", "native_qualified": False}
    if _bounded_canonical(receipt, 65536) != _bounded_canonical(expected, 65536):
        raise ValueError("marketing_copy_receipt_reconciliation_mismatch")
    target = store._walk(root, ["trials", claim["trial_name"], "artifacts"])
    try:
        info = os.fstat(target)
        _owned(info, store.owner, directory=True, private=True)
        if stat.S_IMODE(info.st_mode) != 0o700 or store._read(target, "agent-output.json") != output:
            raise ValueError("marketing_copied_output_reconciliation_mismatch")
    finally:
        os.close(target)
    return {**_unknown(), "status": "copied_bytes_retained_ONLY", "artifact_sha256": intent["actor_output_sha256"]}


def _status(store, request, *, opening=False):
    root, claim, plan = _context_version(store, request, opening=opening)
    try:
        result = {"context": _unknown(), "copy": _unknown(), "scope": claim["scope"]}
        for name, operation in (("context", _context_status_version), ("copy", _copy_status)):
            try:
                result[name] = operation(store, root, claim, plan, opening=opening)
            except (OSError, ValueError, TypeError, KeyError, OverflowError):
                pass  # Preserve unknown. Never mutate/complete/retry partial state.
        return result
    finally:
        os.close(root)


def read_component_file_status(request):
    marketing_native_gate()
    with MarketingAttemptStore() as store:
        try:
            return _status(store, request)
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            return {"context": _unknown(), "copy": _unknown(), "scope": store.scope}


def read_opening_component_file_status(request):
    marketing_native_gate()
    with MarketingAttemptStore() as store:
        try:
            return _status(store, request, opening=True)
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            return {"context": _unknown(), "copy": _unknown(), "scope": store.scope}


def read_opening_component_context_status(request):
    marketing_native_gate()
    with MarketingAttemptStore() as store:
        root = None
        try:
            root, claim, plan = _opening_context(store, request)
            return _opening_context_status(store, root, claim, plan)
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            return _unknown()
        finally:
            if root is not None:
                os.close(root)
