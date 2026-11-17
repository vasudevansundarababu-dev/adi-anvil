"""Closed owned-container stop observation producer, not whole-actor shutdown.

The start/identity producer and native admission remain unqualified. This never emits
the component stopped acknowledgment or actor-stop/capture record: graph/session
revocation and complete bounded capture need their own qualified producers.
"""

import hashlib
import math
import os
import re
from time import monotonic

from anvil.marketing_native_attempt import MarketingAttemptStore, _write_at
from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    _bounded_canonical,
    _digest,
    marketing_native_gate,
)
from anvil.marketing_native_control import _remaining
from anvil.marketing_native_engine import _request
from anvil.marketing_native_mounts import _context_version
from anvil.marketing_native_reconcile import _context_status_version
from anvil.marketing_native_records import _parse_record
from anvil.marketing_native_start import _framework_entry, _profile


def _validate_container_binding(store, root, claim, plan, role, binding):
    if role not in {"environment", "tests"}:
        raise ValueError("marketing_exact_stop_role_required")
    _framework_entry(store, root, claim)
    entry = _parse_record(store._read(root, "framework-entry.json"))
    fields = {"schema_version", "job_id", "request_sha256", "plan_sha256", "framework_trial_id",
              "operation_nonce", "role", "session_id", "container_id", "image_id", "inspect_config_sha256"}
    if (set(binding) != fields or binding.get("schema_version") != "anvil.marketing-owned-container.v1"
            or any(binding.get(key) != claim[key] for key in ("job_id", "request_sha256", "plan_sha256"))
            or any(binding.get(key) != entry.get(key) for key in ("framework_trial_id", "operation_nonce"))
            or binding.get("role") != role or binding.get("session_id") != claim["trial_name"] + (
                "__env" if role == "environment" else "__verifier__trial")
            or type(binding.get("container_id")) is not str or not re.fullmatch(r"[a-f0-9]{64}", binding["container_id"])
            or type(binding.get("image_id")) is not str or not re.fullmatch(r"sha256:[a-f0-9]{64}", binding["image_id"])
            or type(binding.get("inspect_config_sha256")) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", binding["inspect_config_sha256"])):
        raise ValueError("marketing_owned_container_binding_required")
    before = _profile(store, root, claim, plan, role, "preflight")
    started = _profile(store, root, claim, plan, role, "start")
    if _bounded_canonical(before, DOCUMENT_CAP) != _bounded_canonical(started, DOCUMENT_CAP):
        raise ValueError("marketing_stop_actual_profile_changed")
    return binding


def _container_binding(store, root, claim, plan, role):
    if role not in {"environment", "tests"}:
        raise ValueError("marketing_exact_stop_role_required")
    return _validate_container_binding(store, root, claim, plan, role,
                                       _parse_record(store._read(root, role + "-container.json")))


def _inspect(value, binding, *, stopped, allow_created=False):
    keys = ("Id", "Image", "Name", "Config", "HostConfig", "Mounts")
    if (any(key not in value for key in keys) or value["Id"] != binding["container_id"]
            or value["Image"] != binding["image_id"]
            or _digest({key: value[key] for key in keys}) != binding["inspect_config_sha256"]
            or type(value.get("State")) is not dict or type(value.get("RestartCount")) is not int
            or value["RestartCount"] != 0):
        raise ValueError("marketing_actual_container_identity_changed")
    if type(value["Config"]) is not dict:
        raise ValueError("marketing_actual_container_config_required")
    labels = value["Config"].get("Labels")
    if (type(labels) is not dict or labels.get("com.docker.compose.project") != binding["session_id"]
            or labels.get("com.docker.compose.service") != "main"):
        raise ValueError("marketing_actual_container_ownership_changed")
    state = value["State"]
    if (type(state.get("Running")) is not bool or state.get("Paused") is not False
            or state.get("Restarting") is not False or state.get("Dead") is not False
            or type(state.get("Pid")) is not int or state["Pid"] < 0):
        raise ValueError("marketing_container_state_unknown")
    terminal = {"created", "exited"} if allow_created else {"exited"}
    if stopped and (state["Running"] is not False or state["Pid"] != 0 or state.get("Status") not in terminal):
        raise ValueError("marketing_container_not_observed_stopped")
    return state


def _created_binding(store, root, claim, plan, role):
    if role not in {"environment", "tests"}:
        raise ValueError("marketing_exact_recovery_role_required")
    proof = _parse_record(store._read(root, role + "-container-before-start.json"))
    if (set(proof) != {"schema_version", "binding", "created_inspect_sha256", "state", "native_qualified"}
            or proof["schema_version"] != "anvil.marketing-created-container-binding.v1"
            or proof["state"] != "created_observed_NOT_start_success" or proof["native_qualified"] is not False
            or type(proof["binding"]) is not dict):
        raise ValueError("marketing_exact_created_ownership_required")
    binding = _validate_container_binding(store, root, claim, plan, role, proof["binding"])
    raw = store._read(root, role + "-created-engine-inspect.json")
    if hashlib.sha256(raw).hexdigest() != proof["created_inspect_sha256"]:
        raise ValueError("marketing_actual_created_observation_changed")
    created = _parse_record(raw)
    state = _inspect(created, binding, stopped=True, allow_created=True)
    if state["Status"] != "created":
        raise ValueError("marketing_original_unstarted_observation_required")
    intent = _parse_record(store._read(root, role + "-physical-start-intent.json"))
    context = _parse_record(store._read(root, "component-context.json"))
    private = intent.get('schema_version') == 'anvil.marketing-physical-start-intent.v3'
    work_deadline = context['deadline_monotonic'] - plan['bounds']['cleanup_seconds']
    if private:
        # The caller has already reconciled the independently pinned context.
        # A start-file version alone cannot select private timing rules.
        private_context = _parse_record(store._read(root, 'component-context-intent.json'))
        if (private_context.get('schema_version') != 'anvil.marketing-component-context-intent.v3'
                or private_context.get('private_program_sha256') != hashlib.sha256(
                    store._read(root, 'private-verifier-program.json')).hexdigest()):
            raise ValueError('marketing_private_original_start_program_required')
        work_deadline -= plan['bounds']['verifier_seconds'] if role == 'environment' else 8
    if (set(intent) != {"schema_version", "role", "job_id", "framework_trial_id", "request_sha256", "plan_sha256",
                        "resolver_sha256", "operation_nonce", "deadline_monotonic", "scope", "work_deadline_monotonic",
                        "cleanup_reserve_seconds"}
            or intent.get("schema_version") != ('anvil.marketing-physical-start-intent.v3' if private else
                                                'anvil.marketing-physical-start-intent.v2')
            or any(intent.get(key) != binding[key] for key in ("job_id", "request_sha256", "plan_sha256", "framework_trial_id",
                                                               "operation_nonce", "role"))
            or intent.get("scope") != claim["scope"]
            or type(intent.get("cleanup_reserve_seconds")) is not int
            or intent["cleanup_reserve_seconds"] != plan["bounds"]["cleanup_seconds"]
            or intent.get("deadline_monotonic") != context["deadline_monotonic"]
            or intent.get("work_deadline_monotonic") != work_deadline):
        raise ValueError("marketing_original_bounded_start_intent_required")
    # Never reads/promotes the possibly absent or partial final startup binding.
    return binding


async def _stop(store, request, role, *, created_only=False, opening=False, phase_deadline=None, private=False):
    if type(private) is not bool or private and not opening:
        raise ValueError('marketing_explicit_private_owned_stop_required')
    root, claim, plan = _context_version(store, request, opening=opening)
    try:
        retained = _context_status_version(store, root, claim, plan, opening=opening)
        if retained["same_boot_observed"] is not True or retained["deadline_elapsed_observed"] is not False:
            raise ValueError("marketing_current_original_context_required")
        binding = (_created_binding if created_only else _container_binding)(store, root, claim, plan, role)
        context = _parse_record(store._read(root, "component-context.json"))
        receipt = _parse_record(store._read(root, "component-context-receipt.json"))
        if (receipt.get("context_sha256") != hashlib.sha256(store._read(root, "component-context.json")).hexdigest()
                or any(context.get(key) != claim[key] for key in ("job_id", "request_sha256", "plan_sha256"))
                or context.get("operation_nonce") != binding["operation_nonce"]):
            raise ValueError("marketing_stop_context_binding_required")
        with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as stream:
            boot = stream.read(64).strip()
        if context.get("boot_id") != boot:
            raise ValueError("marketing_stop_same_boot_required")
        if phase_deadline is not None:
            if (type(phase_deadline) not in (int, float) or not math.isfinite(phase_deadline)
                    or phase_deadline > context['deadline_monotonic']):
                raise ValueError('marketing_original_container_stop_phase_required')
            context = {**context, 'deadline_monotonic': phase_deadline}
        _remaining(context)
        cleanup = plan["bounds"]["cleanup_seconds"]
        if type(cleanup) is not int or not 1 <= cleanup <= 600:
            raise ValueError("marketing_explicit_stop_bound_required")
        # Source proposal consumes only the existing aggregate deadline, never
        # an added cleanup allowance. Asset values still need real qualification.
        before = await _request("inspect", binding["container_id"], deadline=context["deadline_monotonic"], private=private)
        state = _inspect(before, binding, stopped=False)
        # Inspection may consume nearly the entire lifecycle. Recompute only
        # after it, keeping at least one second inside the existing deadline for
        # post-stop observation/receipt. No new cleanup allowance is added.
        remaining = _remaining(context)
        if remaining <= 1:
            raise TimeoutError("marketing_stop_observation_reserve_exhausted")
        seconds = min(cleanup, max(0, int(remaining) - 1))
        intent = {**binding, "schema_version": "anvil.marketing-container-stop-intent.v1",
                  "deadline_monotonic": context["deadline_monotonic"], "stop_seconds": seconds,
                  "observation_reserve_seconds": 1}
        _write_at(root, role + "-container-stop-intent.json", _bounded_canonical(intent, DOCUMENT_CAP))
        _write_at(root, role + "-container-inspect-before.json", _bounded_canonical(before, DOCUMENT_CAP))
        if state["Running"]:
            # Exactly one mutation; ambiguous status/timeout/cancellation leaves
            # the exclusive intent and never dispatches stop again.
            await _request("stop", binding["container_id"], deadline=context["deadline_monotonic"], stop_seconds=seconds, private=private)
        after = await _request("inspect", binding["container_id"], deadline=context["deadline_monotonic"], private=private)
        _inspect(after, binding, stopped=True, allow_created=created_only)
        _remaining(context)
        observed = {"schema_version": "anvil.marketing-container-stop-observed.v2",
                    "binding_sha256": _digest(binding), "inspect_before_sha256": _digest(before),
                    "inspect_after_sha256": _digest(after), "container_id": binding["container_id"],
                    "role": role, "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
                    "framework_trial_id": binding["framework_trial_id"], "operation_nonce": binding["operation_nonce"],
                    "boot_id": boot, "observed_monotonic": monotonic(),
                    "container_stopped_observed": True, "whole_actor_stopped": False,
                    "native_qualified": False, "replay_permitted": False,
                    "binding_origin": "created_before_start" if created_only else "completed_start",
                    "startup_outcome": "unknown_not_promoted" if created_only else "complete_binding_retained",
                    "late_start_effects_unqualified": created_only}
        # Retain bounded actual engine bytes privately, not just fabricated hashes.
        _write_at(root, role + "-container-inspect-after.json", _bounded_canonical(after, DOCUMENT_CAP))
        _write_at(root, role + "-container-stop-observed.json", _bounded_canonical(observed, DOCUMENT_CAP))
        return observed
    finally:
        os.close(root)


async def observe_owned_role_stop(request, role):
    marketing_native_gate()
    with MarketingAttemptStore() as store:
        return await _stop(store, request, role)


async def reconcile_created_role_stop(request, role):
    marketing_native_gate()
    with MarketingAttemptStore() as store:
        return await _stop(store, request, role, created_only=True)
