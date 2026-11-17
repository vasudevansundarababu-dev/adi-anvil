"""Closed candidate API-stop bridge; never a physical stop/capture acknowledgment.

Targets the independently reviewed 3a48430 fence-v1/drain-v2 source contract.
Operating facade pins remain unchanged. Actual SQL/transport/runtime custody,
whole-actor shutdown and capture producers are still prerequisites, not supplied
by valid receipt hashes or by this bridge's local retained records.
"""

import hashlib
import json
import os
import time

from anvil.marketing_native_attempt import _write_at
from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical, marketing_native_gate

CANDIDATE_CONTRACT = {
    "base_contract_commit": "3a484308e0faddb7cc0f0dd25ea1dd81e06f31a9",
    "base_contract_manifest_sha256": "53fc275bc293c6a03a8a65e3f04d15bcafc046d15f00412892479a77469ef299",
    "phase_source_manifest_sha256": "5f0c762406a7181f1a9569cd0cac61ca66f11747f113e264774fe1f16dca61ce",
    "work_source_manifest_sha256": "79818b50d1789ff29a84696b2785e16617f8a997f1251aea6b0872d2173f50c2",
    "facade_sha256": "3037bac7d80271727f882b00369ad0e597ec7f32accd42b85501ceaa2d388750",
    "transport_sha256": "10a1ad6bbd7858cf2c1d3dfe7c54f87a5763f73c3fa80d5cdd2779519b6fdc85",
    "base_receipt_source_sha256": "10ef6757c55d329a9bfefa949b653222402e088b196947a2cb185cb1e882bb26",
    "receipt_source_sha256": "ae75846bcfc96c27975ce330413a452f673f132fbf8004bc94eebb1cd9949d91",
}


def _remaining(deadline):
    if type(deadline) not in (int, float) or not time.monotonic() < deadline < float("inf"):
        raise TimeoutError("marketing_world_stop_original_deadline_required")


def _status(raw, expected, original_fence=None):
    from anvil.marketing_world_quiescence import Scope, Status

    # Bound bytes are retained separately. Neither a coercible scalar scope nor
    # a self-consistent foreign receipt may be adopted from an API response.
    if type(expected) is not dict or set(expected) != set(Scope.model_fields):
        raise ValueError("marketing_independent_exact_stop_scope_required")
    bound = Scope.model_validate(expected).model_dump(mode="json")
    value = Status.model_validate(raw).model_dump(mode="json")
    fence = value["fence"]
    if any(fence[key] != bound[key] for key in bound):
        raise ValueError("marketing_stop_response_foreign_scope")
    if original_fence is not None and fence != original_fence:
        raise ValueError("marketing_stop_original_fence_changed")
    return value


def _retain(store, root, name, value, deadline):
    raw = _bounded_canonical(value, DOCUMENT_CAP)
    _remaining(deadline)
    _write_at(root, name, raw)
    if store._read(root, name) != raw:
        raise ValueError("marketing_world_stop_retained_bytes_changed")
    _remaining(deadline)
    return hashlib.sha256(raw).hexdigest()


def _candidate_fence_and_drain(store, root, world, expected, *, deadline, phase_deadline):
    """Internal candidate stage: one explicit fence and at most one explicit drain.

    Caller must have independently admitted this exact existing world, bound the
    original same-boot deadline and sealed the candidate source/runtime. There is
    no attach, prepare, graph execution, mutation retry or physical acknowledgment.
    Bounded status-only observations may wait for already-admitted work. Caller
    MUST attempt separate physical cleanup in finally even if this stage fails.
    An existing/partial intent makes a second invocation fail before dispatch.
    """
    from anvil.marketing_paid_world import QualifiedWorld
    from anvil.marketing_world_quiescence import Scope

    if type(world) is not QualifiedWorld:
        raise ValueError("marketing_exact_existing_world_for_stop_required")
    if type(expected) is not dict or set(expected) != set(Scope.model_fields):
        raise ValueError("marketing_independent_exact_stop_scope_required")
    bound = Scope.model_validate(expected).model_dump(mode="json")
    for key in (
        "project_id", "job_id", "plan_id", "world_binding_id", "world_binding_sha256",
        "episode_id", "generation", "execution_sha256",
    ):
        actual = getattr(world._bound, key)
        if (actual if key == "generation" else str(actual)) != bound[key]:
            raise ValueError("marketing_existing_world_stop_scope_changed")
    if (hashlib.sha256(str(world._job["lease_token"]).encode()).hexdigest()
            != bound["lease_sha256"] or deadline != world._deadline):
        raise ValueError("marketing_original_world_lease_and_deadline_required")
    if type(phase_deadline) not in (int, float) or not phase_deadline < deadline:
        raise ValueError("marketing_reserved_cleanup_phase_required")
    _remaining(phase_deadline)
    _retain(store, root, "world-stop-intent.json", {
        "schema_version": "anvil.marketing-candidate-world-stop-intent.v1",
        "scope": bound, "candidate_contract": CANDIDATE_CONTRACT,
        "original_deadline_monotonic": deadline,
        "api_phase_deadline_monotonic": phase_deadline,
        "operations": ["fence", "bounded_readonly_status", "drain_after_zero_pending"],
        "native_qualified": False,
    }, phase_deadline)
    _remaining(phase_deadline)
    fenced = _status(world.fence(phase_deadline=phase_deadline), bound)
    fence_pin = _retain(store, root, "world-fence-status.json", fenced, phase_deadline)
    final = fenced
    if fenced["state"] != "api_quiescent":
        current = fenced
        for observation in range(65):
            pending = current["pending"]
            if pending["sdk_unknown"] or pending["workflow_unknown"]:
                raise RuntimeError("marketing_world_stop_unknown_no_drain")
            if not any(pending.values()):
                break
            if observation == 64:
                raise TimeoutError("marketing_world_stop_readonly_observation_bound")
            _remaining(phase_deadline)
            time.sleep(min(0.1, max(0, phase_deadline - time.monotonic())))
            _remaining(phase_deadline)
            current = _status(world.quiescence(phase_deadline=phase_deadline), bound, fenced["fence"])
            _retain(store, root, f"world-status-observation-{observation:02d}.json",
                    current, phase_deadline)
        if current["state"] == "api_quiescent":
            # Another authorized transaction may already have retained it. A
            # readback never authorizes a redundant mutation or receipt rewrite.
            final = current
        else:
            final = _candidate_drain_once(store, root, world, bound, fenced,
                                          fence_pin, deadline, phase_deadline)
    final_pin = _retain(store, root, "world-final-status.json", final, phase_deadline)
    # A hold is not task completion. Even recorded_done + API zero counters is
    # not whole-process/container shutdown or a physical capture seal.
    return {
        "schema_version": "anvil.marketing-candidate-world-stop-result.v1",
        "fence_status_sha256": fence_pin, "final_status_sha256": final_pin,
        "api_quiescent": final["state"] == "api_quiescent",
        "terminal_status": (final["quiescence"]["terminal_status"]
                            if final["quiescence"] is not None else None),
        "physical_stop_verified": False, "capture_ready": False,
        "native_qualified": False, "replay_permitted": False,
    }


def _candidate_drain_once(store, root, world, bound, fenced, fence_pin, deadline, phase_deadline):
    # Distinct write intent BEFORE the sole drain dispatch; a lost response
    # cannot turn readback, process recovery or another callback into replay.
    _retain(store, root, "world-drain-intent.json", {
        "schema_version": "anvil.marketing-candidate-world-drain-intent.v1",
        "scope": bound, "fence_status_sha256": fence_pin,
        "original_deadline_monotonic": deadline,
        "api_phase_deadline_monotonic": phase_deadline,
    }, phase_deadline)
    _remaining(phase_deadline)
    return _status(world.drain(phase_deadline=phase_deadline), bound, fenced["fence"])


def candidate_fence_and_drain(store, root, world, expected, *, deadline, phase_deadline):
    marketing_native_gate()
    return _candidate_fence_and_drain(store, root, world, expected, deadline=deadline,
                                     phase_deadline=phase_deadline)


async def _candidate_stop_and_observe(store, request, world, expected, *, deadline, opening=False, phase_bounds=None, private=False):
    """Connect API stop to owned-container cleanup, without a whole-actor ack.

    Once the independent request/world/attempt binding is validated, physical
    cleanup is attempted even if the API stage fails or is cancelled. Both use
    the original context deadline; no new timeout, shielded task or grace period
    is created. A second cancellation may still interrupt cleanup: that remains
    Unknown, never an acknowledgment. Actual whole-process cleanup is separate.
    """
    from anvil.marketing_native_boundary import MarketingCampaignRequestV1
    from anvil.marketing_native_mounts import _context_version
    from anvil.marketing_native_reconcile import _context_status_version
    from anvil.marketing_native_records import _parse_record
    from anvil.marketing_native_stop import _stop

    if type(request) is not MarketingCampaignRequestV1:
        raise ValueError("marketing_exact_stop_request_required")
    value = json.loads(request.canonical_bytes)
    if type(expected) is not dict or any(expected.get(key) != value[key] for key in (
        "project_id", "job_id", "plan_id", "episode_id", "generation", "execution_sha256",
    )):
        raise ValueError("marketing_stop_world_request_scope_required")
    root, claim, plan = _context_version(store, request, opening=opening)
    try:
        retained = _context_status_version(store, root, claim, plan, opening=opening)
        if (retained["same_boot_observed"] is not True
                or retained["deadline_elapsed_observed"] is not False):
            raise ValueError("marketing_current_original_context_required_before_api")
        context = _parse_record(store._read(root, "component-context.json"))
        if (context["deadline_monotonic"] != deadline
                or claim["request_sha256"] != hashlib.sha256(request.canonical_bytes).hexdigest()):
            raise ValueError("marketing_original_stop_attempt_deadline_required")
        cleanup = plan["bounds"]["cleanup_seconds"]
        if type(cleanup) is not int or not 1 <= cleanup <= 600:
            raise ValueError("marketing_existing_cleanup_reserve_required")
        phase_deadline = deadline - cleanup
        container_deadline = deadline
        if opening:
            from anvil.marketing_native_actor_timing import opening_phases

            owner_intent = _parse_record(store._read(root, 'original-world-owner-intent.json'))
            actor_intent = _parse_record(store._read(root, 'opening-actor-control-intent.json'))
            # Recompute against the original start and plan. Use start as the
            # arithmetic clock here; expiry is checked separately below.
            canonical_phases = opening_phases(plan['bounds'], deadline=deadline,
                                             started=actor_intent['actor_started_monotonic'],
                                             now=actor_intent['actor_started_monotonic'],
                                             request_timeout=value['request_timeout_seconds'], private=private)
            if (phase_bounds != canonical_phases or owner_intent['phase_bounds'] != canonical_phases):
                raise ValueError('marketing_original_opening_stop_partitions_changed')
            phase_deadline = canonical_phases['api_stop_deadline_monotonic']
            container_deadline = canonical_phases['actor_container_stop_deadline_monotonic']
        try:
            # Too little API time deliberately raises before fence/intent, then
            # takes the same independent owned cleanup path below. Original
            # world deadline stays unchanged; the transport gets an earlier cap.
            if phase_deadline - time.monotonic() < 1:
                raise TimeoutError("marketing_api_phase_skipped_preserve_cleanup")
            api = _candidate_fence_and_drain(store, root, world, expected, deadline=deadline,
                                             phase_deadline=phase_deadline)
        except BaseException as original:
            try:
                await _stop(store, request, "environment", opening=opening, phase_deadline=container_deadline, private=private)
            except BaseException as cleanup:
                # Preserve original cancellation/failure, with failed cleanup as
                # its cause; neither error is replaced by a fabricated receipt.
                raise original from cleanup
            raise
        observed = await _stop(store, request, "environment", opening=opening, phase_deadline=container_deadline, private=private)
        return {
            "schema_version": "anvil.marketing-candidate-api-container-stop.v1",
            "api": api, "container_observation": observed,
            "whole_actor_stopped": False, "physical_stop_verified": False,
            "capture_ready": False, "native_qualified": False,
            "replay_permitted": False,
        }
    finally:
        os.close(root)


async def candidate_stop_and_observe(request, world, expected, *, deadline):
    marketing_native_gate()
    from anvil.marketing_native_attempt import MarketingAttemptStore

    with MarketingAttemptStore() as store:
        return await _candidate_stop_and_observe(store, request, world, expected, deadline=deadline)
