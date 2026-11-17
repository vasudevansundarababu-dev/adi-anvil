"""Bounded source-reviewed capture transport, never a physical-proof validator.

Harbor channel design 20878503e7b302859e8879bbb673dc93ac0021a42ccde9d7995abdefaac49461.
Canonical original bytes are preserved. Parsing cannot issue acceptance.
"""

import hashlib
from dataclasses import dataclass, field
from uuid import UUID

from anvil.dataset_export_contract import json_object
from anvil.marketing_native_capture_budget import KIND_LIMITS, prepare_v2_metadata_budget
from anvil.marketing_native_capture_budget import SCHEMA as METADATA_SCHEMA
from anvil.marketing_native_wire_bounds import bounded_json
from anvil.praxis_generic_contract import canonical

WIRE_CAP = 1048576  # Existing ordinary API request ceiling, never expanded.
SCHEMA = "anvil.marketing-native-capture-submission.v1"
CONSISTENCY_KINDS = frozenset({"framework_entry", "world_fence_status", "world_final_status", "environment_stop_intent",
                               "environment_inspect_before", "environment_inspect_after", "environment_stop_observed",
                               "graph_return_receipt", "actor_output", "collection_receipt"})
AUTHORITATIVE_KINDS = frozenset({"whole_actor_shutdown", "capture_seal"})
KINDS = CONSISTENCY_KINDS | AUTHORITATIVE_KINDS


@dataclass(frozen=True, slots=True)
class Submission:
    enrollment_id: str
    request_sha256: str
    operation_nonce: str
    body_schema: str
    wire_sha256: str
    # Never include raw operational/candidate bytes in exception/log reprs.
    wire: bytes = field(repr=False)
    documents: tuple[tuple[str, bytes], ...] = field(repr=False)


def wire_budget(enrollment):
    """Prove the whole inline control envelope fits before any paid execution.

    Canonical JSON document bytes expand by at most two when embedded as JSON
    strings. Profiles that cannot prove this bound need separately API-held
    complete bulk artifacts, not truncation, larger caps or caller-file hashes.
    """
    limits = enrollment["document_limits"]
    schema = enrollment["body_schema"]
    kinds = KINDS if schema == SCHEMA else frozenset(dict(KIND_LIMITS)) if schema == METADATA_SCHEMA else None
    if (kinds is None or type(limits) is not dict or set(limits) != kinds
            or any(type(v) is not int or not 0 < v <= WIRE_CAP for v in limits.values())):
        raise ValueError("capture_original_document_limits_required")
    if schema == METADATA_SCHEMA and limits != dict(KIND_LIMITS):
        raise ValueError("capture_fixed_metadata_kind_limits_required")
    ceiling = enrollment["wire_limit"]
    if type(ceiling) is not int or not 1 <= ceiling <= WIRE_CAP:
        raise ValueError("capture_original_plan_wire_limit_required")
    frame = {"schema_version": schema,
             **{key: enrollment[key] for key in ("enrollment_id", "request_sha256", "operation_nonce")},
             "documents": {kind: "" for kind in kinds}}
    maximum = len(canonical(frame)) + 2 * sum(limits.values())
    if schema == METADATA_SCHEMA:
        producer = prepare_v2_metadata_budget(enrollment["enrollment_id"], enrollment["request_sha256"],
                                            enrollment["operation_nonce"], plan_receipt_bytes=ceiling)
        if producer.canonical_empty_frame != canonical(frame) or producer.wire_upper_bound != maximum:
            raise ValueError("capture_producer_consumer_wire_budget_mismatch")
    if maximum > ceiling:
        raise ValueError("capture_profile_requires_complete_api_held_bulk_refs")
    return {"maximum_wire_bytes": maximum, "maximum_decoded_bytes": sum(limits.values()), "wire_cap": ceiling}


def parse(raw, enrollment):
    """enrollment is original private API data, never producer-supplied limits."""
    if type(raw) is not bytes or not 0 < len(raw) <= WIRE_CAP:
        raise ValueError("capture_wire_bound")
    try:
        value = json_object(raw)
        bounded_json(value, WIRE_CAP, max_nodes=20000)
        if canonical(value) != raw:
            raise ValueError("canonical")
        if (set(value) != {"schema_version", "enrollment_id", "request_sha256", "operation_nonce", "documents"}
                or value["schema_version"] != enrollment["body_schema"]
                or str(UUID(value["enrollment_id"])) != value["enrollment_id"]
                or any(value[key] != enrollment[key] for key in ("enrollment_id", "request_sha256", "operation_nonce"))
                or type(value["documents"]) is not dict or set(value["documents"]) != set(enrollment["document_limits"])):
            raise ValueError("scope")
        wire_budget(enrollment)
        limits = enrollment["document_limits"]
        documents, total = [], 0
        for kind in sorted(limits):
            text = value["documents"][kind]
            if type(text) is not str:
                raise ValueError("document")
            data = text.encode("utf-8")
            total += len(data)
            if not 0 < len(data) <= limits[kind] or total > WIRE_CAP:
                raise ValueError("bound")
            document = json_object(data)
            bounded_json(document, limits[kind], max_nodes=20000)
            if canonical(document) != data:
                raise ValueError("document canonical")
            documents.append((kind, data))
        return Submission(value["enrollment_id"], value["request_sha256"], value["operation_nonce"], value["schema_version"],
                          hashlib.sha256(raw).hexdigest(), raw, tuple(documents))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, AttributeError):
        raise ValueError("capture_submission_invalid_or_scope_changed") from None
