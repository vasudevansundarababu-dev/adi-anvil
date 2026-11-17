"""Marketing-specific immutable preparation; all operational entries stay closed.

Pure validation proves byte consistency only. Independent operator custody,
qualified world construction and native lifecycle admission remain unavailable.
No provider SDK, database, graph runner or runtime is imported by preparation.
"""

import hashlib
import json
import re
from dataclasses import dataclass

import rfc8785

PURPOSE = "marketing_campaign_graph_v1"  # Proposed, NOT registered/admitted.
SCHEMA = "anvil.marketing-native-request.v1"
DOCUMENT_CAP = 1048576  # Existing per-document ceiling, not a campaign allowance.
HASH_FIELDS = frozenset({
    "source_manifest_sha256", "dataset_qualification_sha256", "native_binding_sha256",
    "execution_sha256", "workflow_graph_sha256", "role_policy_sha256", "public_actor_sha256",
    "schedule_sha256", "membership_sha256", "asset_manifest_sha256",
})
IDENTITY_FIELDS = frozenset({
    "deployment_id", "job_id", "check_id", "plan_id", "group_id", "project_id", "actor_id",
    "campaign_id", "episode_id", "model_config_ref", "key_version_ref", "pricing_ref",
    "rights_ref", "candidate_id",
})
INTEGER_FIELDS = frozenset({
    "generation", "repetition", "max_calls", "request_timeout_seconds", "episode_timeout_seconds",
})
REQUEST_FIELDS = HASH_FIELDS | IDENTITY_FIELDS | INTEGER_FIELDS | {
    "schema_version", "purpose", "environment", "case_assignment",
}


@dataclass(frozen=True, slots=True)
class MarketingCampaignRequestV1:
    canonical_bytes: bytes


def marketing_native_gate():
    """Unconditional gate; no caller flag or environment setting opens it."""
    raise RuntimeError("marketing_native_operator_world_and_lifecycle_not_admitted")


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("marketing_duplicate_request_field")
        value[key] = item
    return value


def _canonical(value):
    try:
        return rfc8785.dumps(value)
    except (ValueError, TypeError, RecursionError):
        raise ValueError("marketing_canonical_document_required") from None


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


class _BoundedCanonicalSink:
    def __init__(self, limit):
        self.limit = limit
        self.buffer = bytearray()

    def write(self, chunk):
        if type(chunk) is not bytes or len(chunk) > self.limit - len(self.buffer):
            raise ValueError("marketing_graph_result_capacity")
        self.buffer.extend(chunk)
        return len(chunk)


def _bounded_json_shape(value, limit):
    # Bound strings/container sorting inputs before the serializer can allocate
    # an escaped string or copied/sorted container. Stack space stays depth-bound.
    def children(current):
        if type(current) is dict:
            for key, item in current.items():
                if type(key) is not str:
                    raise ValueError("marketing_exact_json_key_required")
                yield key
                yield item
        else:
            yield from current

    stack = [(iter((value,)), 0)]
    used = 0
    while stack:
        iterator, depth = stack[-1]
        try:
            current = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        used += 1
        kind = type(current)
        if kind is str:
            used += len(current)
        elif kind in (dict, list):
            if len(current) > limit or depth >= 64:
                raise ValueError("marketing_bounded_json_shape_required")
            stack.append((children(current), depth + 1))
        elif kind not in (int, float, bool, type(None)):
            raise ValueError("marketing_exact_json_value_required")
        if used > limit:
            raise ValueError("marketing_graph_result_capacity")


def _bounded_canonical(value, limit):
    _bounded_json_shape(value, limit)
    sink = _BoundedCanonicalSink(limit)
    try:
        rfc8785.dump(value, sink)
    except (ValueError, TypeError, RecursionError):
        raise ValueError("marketing_bounded_canonical_result_required") from None
    return bytes(sink.buffer)


def _identifier(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}", value)


def prepare_marketing_request(raw):
    """Pure structural validation, no preparation API call or invocation claim."""
    if type(raw) is not bytes or not 0 < len(raw) <= DOCUMENT_CAP:
        raise ValueError("marketing_bounded_request_bytes_required")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("marketing_strict_request_json_required") from None
    if type(value) is not dict or set(value) != REQUEST_FIELDS or _canonical(value) != raw:
        raise ValueError("marketing_exact_canonical_request_required")
    if (
        value["schema_version"] != SCHEMA or value["purpose"] != PURPOSE
        or value["environment"] != "qa"
        or any(not _identifier(value[key]) for key in IDENTITY_FIELDS)
        or any(type(value[key]) is not str or not re.fullmatch(r"[a-f0-9]{64}", value[key]) for key in HASH_FIELDS)
        or any(type(value[key]) is not int or value[key] < 1
               for key in INTEGER_FIELDS - {"generation"})
        or type(value["generation"]) is not int
        or not 0 <= value["generation"] <= 9007199254740991
        or value["repetition"] > 9007199254740991
        or not 1 <= value["max_calls"] <= 1000
        or not 1 <= value["request_timeout_seconds"] <= value["episode_timeout_seconds"] <= 600
    ):
        raise ValueError("marketing_exact_public_request_binding_required")
    case = value["case_assignment"]
    if (
        type(case) is not dict or set(case) != {"case_id", "snapshot_sha256", "locale"}
        or not _identifier(case["case_id"]) or not _identifier(case["locale"])
        or type(case["snapshot_sha256"]) is not str
        or not re.fullmatch(r"[a-f0-9]{64}", case["snapshot_sha256"])
    ):
        raise ValueError("marketing_exact_case_assignment_required")
    return MarketingCampaignRequestV1(raw)


def validate_prepared_graph_binding(request, prepared):
    """Pure comparison against already obtained API data; not custody or admission.

    Never calls marketing_paid_execution.prepare: that API consumes an invocation.
    No world object/factory, connections, credential or deadline is accepted here.
    """
    if type(request) is not MarketingCampaignRequestV1:
        raise ValueError("marketing_exact_typed_request_required")
    checked = prepare_marketing_request(request.canonical_bytes)
    value = json.loads(checked.canonical_bytes)
    if type(prepared) is not dict:
        raise ValueError("marketing_prepared_graph_binding_required")
    raw = _canonical(prepared)
    if len(raw) > DOCUMENT_CAP:
        raise ValueError("marketing_prepared_document_capacity")
    native, execution = prepared.get("native_binding"), prepared.get("execution")
    if type(native) is not dict or type(execution) is not dict:
        raise ValueError("marketing_prepared_native_execution_required")
    if (
        prepared.get("mode") != "marketing-native"
        or type(prepared.get("world_attachment")) is not dict
        or prepared.get("world_attachment_sha256") != _digest(prepared["world_attachment"])
        or _digest(native) != value["native_binding_sha256"]
        or _digest(execution) != value["execution_sha256"]
        or native.get("execution_sha256") != value["execution_sha256"]
        or native.get("workflow_graph_sha256") != value["workflow_graph_sha256"]
        or execution.get("workflow_graph_sha256") != value["workflow_graph_sha256"]
        or _digest(execution.get("workflow_graph")) != value["workflow_graph_sha256"]
        or native.get("case_assignment") != value["case_assignment"]
        or _digest(prepared.get("public_actor")) != value["public_actor_sha256"]
        or prepared.get("group_id") != value["group_id"]
        or any(type(prepared.get(key)) is not int or prepared[key] != value[key]
               for key in ("max_calls", "request_timeout_seconds", "episode_timeout_seconds", "repetition"))
    ):
        raise ValueError("marketing_prepared_graph_bytes_changed")
    # Return immutable bytes; do not retain the caller's mutable mapping.
    return raw


def encode_graph_result(output, receipt, *, output_limit, receipt_limit):
    """Pure bounded final documents; explicit values are NOT operator admission.

    Streaming/process memory bounds and independent receipt custody remain separate.
    No KYC cap is inherited and no implicit Marketing cap is supplied.
    """
    if any(type(limit) is not int or not 1 <= limit <= DOCUMENT_CAP
           for limit in (output_limit, receipt_limit)):
        raise ValueError("marketing_explicit_document_limits_required")
    public = _bounded_canonical(output, output_limit)
    evidence = _bounded_canonical(receipt, receipt_limit)
    return public, evidence


def execute_marketing_campaign(folder, request, *, host, python):
    marketing_native_gate()
    # Missing independent resolver/world/lifecycle never falls back to KYC/raw.


def _verify_attached_world_identity(request, world):
    """Pure identity comparison; source/world/rights qualification is separate."""
    if type(request) is not MarketingCampaignRequestV1:
        raise ValueError("marketing_exact_typed_request_required")
    prepare_marketing_request(request.canonical_bytes)
    value = json.loads(request.canonical_bytes)
    if (
        type(world.generation) is not int or world.generation != value["generation"]
        or world.case_id != value["case_assignment"]["case_id"]
        or world.episode_id != value["episode_id"]
    ):
        raise ValueError("marketing_attached_world_request_identity_changed")


def _run_marketing_graph(connections, job, prepared, request, *, absolute_deadline, native_guard):
    marketing_native_gate()
    from anvil.marketing_native_records import MarketingRecordBytesV1, resolve_marketing_records
    from anvil.marketing_native_world_binding import (
        validate_expected_world_record,
        validate_prepared_world_binding,
        validate_world_binding,
        verify_facade_source,
    )

    records = resolve_marketing_records(request)
    if (
        type(records) is not MarketingRecordBytesV1
        or type(request) is not MarketingCampaignRequestV1
        or records.request_sha256 != hashlib.sha256(request.canonical_bytes).hexdigest()
    ):
        raise ValueError("marketing_independent_full_request_records_required")
    world_record = dict(records.records).get("world")
    validate_expected_world_record(request, world_record)
    from anvil.marketing_native_start import before_business

    before_business(request)
    # Fixed-file custody is additional to the still-required full runtime seal.
    verify_facade_source()
    from anvil.marketing_paid_graph import GraphRunner
    from anvil.marketing_paid_world import QualifiedWorld

    # Future private integration only: operation intent, independent world/rights
    # record qualification and actual lifecycle custody are still prerequisites.
    frozen = validate_prepared_graph_binding(request, prepared)
    prepared = json.loads(frozen)
    validate_prepared_world_binding(request, prepared, world_record)
    value = json.loads(request.canonical_bytes)
    if any(str(job[field]) != value[key] for key, field in (
        ("job_id", "id"), ("plan_id", "plan_id"), ("project_id", "project_id"),
        ("actor_id", "actor_id"),
    )):
        raise ValueError("marketing_exact_job_request_binding_required")
    if native_guard() is not True:
        raise RuntimeError("marketing_native_liveness_before_world_attach_required")
    world = QualifiedWorld.attach(job, prepared, absolute_deadline=absolute_deadline)
    if type(world) is not QualifiedWorld:
        raise ValueError("marketing_exact_world_facade_required")
    _verify_attached_world_identity(request, world)
    validate_world_binding(request, world.binding_projection, world_record)
    if native_guard() is not True:
        raise RuntimeError("marketing_native_liveness_after_world_attach_required")
    runner = GraphRunner(
        connections, job, prepared, world, absolute_deadline=absolute_deadline
    )
    return runner.run(native_guard)
