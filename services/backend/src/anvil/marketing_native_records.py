"""Read-only Marketing record custody proposal; no admission or world creation.

The operational resolver is gated before lazy imports or filesystem access.
Internal byte checks do not qualify any payload or authorize native/business work.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    PURPOSE,
    MarketingCampaignRequestV1,
    _bounded_canonical,
    _digest,
    _pairs,
    marketing_native_gate,
    prepare_marketing_request,
)

SECTIONS = frozenset({"roles", "image", "runtime", "task", "profile", "host", "recovery", "world"})
STOP = datetime.fromisoformat("2026-12-11T05:48:04+00:00")


@dataclass(frozen=True, slots=True)
class MarketingRecordBytesV1:
    request_sha256: str
    manifest_sha256: str
    # Host-private retained bytes never become an actor projection or log value.
    operation_bytes: bytes = field(repr=False)
    manifest_bytes: bytes = field(repr=False)
    records: tuple[tuple[str, bytes], ...] = field(repr=False)
    # No authorization/qualification booleans: this is byte custody only.


def _parse_record(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= DOCUMENT_CAP:
        raise ValueError("marketing_bounded_record_required")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs)
        if type(value) is not dict or _bounded_canonical(value, DOCUMENT_CAP) != raw:
            raise ValueError("record")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("marketing_exact_canonical_record_required") from None
    return value


def _checked_record_set(request, store, *, now):
    """Internal read/comparison helper, NOT an authority-bearing public interface.

    Production resolver supplies the exact pinned root store and real clock.
    A mock/local store or caller clock can prove only structural comparisons.
    """
    return _read_record_set(request, store, now=now, candidate=False)


def _checked_candidate_record_set(request, store, *, now):
    """Explicit candidate v2 manifest/world; ordinary v1 resolver is unchanged."""
    return _read_record_set(request, store, now=now, candidate=True)


def _checked_opening_record_set(request, store, *, now):
    """Distinct v3 root/world source nomination, never v2 root reinterpretation."""
    return _read_record_set(request, store, now=now, candidate=True, opening=True)


def _read_record_set(request, store, *, now, candidate, opening=False):
    if type(request) is not MarketingCampaignRequestV1:
        raise ValueError("marketing_exact_typed_request_required")
    prepare_marketing_request(request.canonical_bytes)
    value = json.loads(request.canonical_bytes)
    job = value["job_id"]
    if str(UUID(job)) != job:
        raise ValueError("marketing_canonical_job_uuid_required")
    # The manifest cannot include the hash of the request that already pins it.
    # This context removes exactly its self-pin; the separate operation below
    # binds the COMPLETE request and manifest after both are frozen.
    context = _digest({key: item for key, item in value.items() if key != "asset_manifest_sha256"})
    request_pin = hashlib.sha256(request.canonical_bytes).hexdigest()
    manifest_pin = value["asset_manifest_sha256"]
    manifest_raw = store._read("operation-assets", manifest_pin + ".json")
    if hashlib.sha256(manifest_raw).hexdigest() != manifest_pin:
        raise ValueError("marketing_manifest_bytes_changed")
    manifest = _parse_record(manifest_raw)
    if (
        set(manifest) != {"schema_version", "purpose", "request_context_sha256", "sections"}
        or manifest["schema_version"] != (
            "anvil.marketing-native-assets.v3" if opening else
            "anvil.marketing-native-assets.v2" if candidate else "anvil.marketing-native-assets.v1")
        or manifest["purpose"] != PURPOSE
        or manifest["request_context_sha256"] != context
        or type(manifest["sections"]) is not dict
        or set(manifest["sections"]) != SECTIONS
    ):
        raise ValueError("marketing_distinct_complete_asset_manifest_required")
    records = []
    for section in sorted(SECTIONS):
        pin = manifest["sections"][section]
        if type(pin) is not str or len(pin) != 64 or any(c not in "0123456789abcdef" for c in pin):
            raise ValueError("marketing_exact_section_pin_required")
        raw = store._read("operation-assets", pin + ".json")
        if hashlib.sha256(raw).hexdigest() != pin:
            raise ValueError("marketing_section_bytes_changed")
        record = _parse_record(raw)
        if (
            set(record) != {"schema_version", "purpose", "request_context_sha256", "payload"}
            or record["schema_version"] != "anvil.marketing-native-" + section + (
                ".v3" if opening and section == "world" else
                ".v2" if candidate and section == "world" else ".v1")
            or record["purpose"] != PURPOSE
            or record["request_context_sha256"] != context
            or type(record["payload"]) is not dict
        ):
            raise ValueError("marketing_independently_bound_section_required")
        records.append((section, raw))
    operation_raw = store._read("operations", job + ".json")
    operation = _parse_record(operation_raw)
    if (
        set(operation) != {"schema_version", "origin", "purpose", "job_id", "request_sha256",
                           "manifest_sha256", "expires_at", "stop_at"}
        or operation["schema_version"] != "anvil.marketing-native-operation.v1"
        or operation["origin"] != "independent_operator"
        or operation["purpose"] != PURPOSE or operation["job_id"] != job
        or operation["request_sha256"] != request_pin
        or operation["manifest_sha256"] != manifest_pin
    ):
        raise ValueError("marketing_separate_full_request_operation_required")
    try:
        expires = datetime.fromisoformat(operation["expires_at"])
        stop = datetime.fromisoformat(operation["stop_at"])
        valid = now.tzinfo is not None and expires.tzinfo is not None and stop == STOP and now < min(expires, STOP)
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("marketing_operation_expired_or_stop_changed")
    return MarketingRecordBytesV1(request_pin, manifest_pin, operation_raw, manifest_raw, tuple(records))


def resolve_marketing_records(request):
    marketing_native_gate()
    from anvil.config import ROOT
    from anvil.environment_harbor import operator_proof_module

    module = operator_proof_module()
    # Exact existing store enforces root user, QA hostname, fixed root directory,
    # no-follow dirfd reads, owner/mode/link checks and unchanged bounded files.
    # No caller-selected root, store, clock, world symbol or loader is accepted.
    with module.OperatorProofStore(ROOT) as store:
        return _checked_record_set(request, store, now=datetime.now(timezone.utc))


def resolve_marketing_candidate_records(request):
    marketing_native_gate()
    from anvil.config import ROOT
    from anvil.environment_harbor import operator_proof_module

    module = operator_proof_module()
    with module.OperatorProofStore(ROOT) as store:
        return _checked_candidate_record_set(request, store, now=datetime.now(timezone.utc))


def resolve_marketing_opening_records(request):
    marketing_native_gate()
    from anvil.config import ROOT
    from anvil.environment_harbor import operator_proof_module

    module = operator_proof_module()
    with module.OperatorProofStore(ROOT) as store:
        return _checked_opening_record_set(request, store, now=datetime.now(timezone.utc))
