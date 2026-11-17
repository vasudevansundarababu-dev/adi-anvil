"""API-only complete evidence custody, distinct from native capture acceptance.

Slots and expected category populations come only from private SQL. A reserved
UUID is not issued content. Mutable rows must have immutable API snapshots; all
other entries bind exact immutable original records and their canonical bytes.
No worker path, client-provided evidence body or provider credential is accepted.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from anvil.dataset_export_contract import json_object
from anvil.marketing_capture_attestation import STOP
from anvil.marketing_native_wire_bounds import bounded_json
from anvil.marketing_world_quiescence import Quiescence, Scope
from anvil.praxis_generic_contract import canonical, digest

MANIFEST_CAP = 16777216
# Reference envelopes include existing32MiB campaign before/after text with
# JSON escaping. They are hashed, not copied into the capture storage/wire.
# These NEW bounds derive from existing1000SDK/8000tool/400effect limits; the
# source fixture's20k-row bound is a different population and stays unchanged.
ROW_CAP = 67108864 + 65536
ROW_COUNT_CAP = 30000
MANIFEST_NODE_CAP = ROW_COUNT_CAP * 13 + 512  # Six key/value pairs per entry plus fixed roots.
REFERENCE_BYTES_CAP = 4294967296
SNAPSHOT_CACHE_CAP = 16777216
READY_DESCRIPTOR_CAP = 3072
# This allowlist is shared with the fixed private SQL projection, not supplied
# by a submitter. Empty categories still require an explicit complete count.
CATEGORIES = frozenset({
    "world_source", "world_qualification", "dataset", "runtime_allowlist", "channel_qualification",
    "capture_enrollment", "agent_binding", "world_attachment", "world_releases", "workflow_effects",
    "turn_intents", "turn_observations", "sdk_calls", "sdk_prompts", "tool_intents", "tool_receipts",
    "tool_states", "service_effects", "campaign_states", "final_world_state", "fence", "quiescence",
})
SINGLETONS = frozenset({"world_source", "world_qualification", "dataset", "runtime_allowlist", "channel_qualification",
                        "capture_enrollment", "agent_binding", "world_attachment", "final_world_state", "fence", "quiescence"})
SNAPSHOTS = frozenset({"sdk_calls", "final_world_state"})


@dataclass(frozen=True, slots=True)
class PreparedEvidence:
    manifest: bytes = field(repr=False)
    sha256: str
    snapshots: tuple[tuple[str, str, bytes], ...] = field(repr=False)
    descriptor: dict = field(repr=False)


def _counts(counts):
    if (type(counts) is not dict or set(counts) != CATEGORIES
            or any(type(n) is not int or not 0 <= n <= ROW_COUNT_CAP for n in counts.values())
            or sum(counts.values()) > ROW_COUNT_CAP or any(counts[key] != 1 for key in SINGLETONS)
            or counts["sdk_calls"] != counts["sdk_prompts"] or counts["sdk_calls"] != counts["turn_intents"]
            or counts["sdk_calls"] != counts["turn_observations"]
            or counts["tool_intents"] != counts["tool_receipts"] or counts["tool_intents"] != counts["tool_states"]):
        raise ValueError("Complete actual API category counts and custody joins required")


def _original(context):
    required = {"manifest_id", "enrollment_id", "request_sha256", "operation_nonce", "scope", "expires_at",
                "quiescence", "category_counts", "intent_id", "materialize_before"}
    if type(context) is not dict or set(context) != required:
        raise ValueError("Exact original API evidence materialization context required")
    for key in ("manifest_id", "enrollment_id", "intent_id"):
        if str(UUID(context[key])) != context[key]:
            raise ValueError("Canonical original evidence identifiers required")
    scope = Scope.model_validate(context["scope"])
    quiescence = Quiescence.model_validate(context["quiescence"])
    if (any(getattr(quiescence, key) != getattr(scope, key) for key in Scope.model_fields)
            or digest({key: value for key, value in context["quiescence"].items() if key != "receipt_sha256"}) != quiescence.receipt_sha256):
        raise ValueError("Actual immutable same-scope quiescence receipt required")
    if any(type(context[key]) is not str or not re.fullmatch(r"[a-f0-9]{64}", context[key])
           for key in ("request_sha256", "operation_nonce")):
        raise ValueError("Original request and operation nonce required")
    _counts(context["category_counts"])
    return scope, quiescence


class EvidenceCompiler:
    """Incremental fixed-source compiler shared by sync and async custody."""

    def __init__(self, context, *, now=None):
        scope, quiescence = _original(context)
        instant = datetime.now(timezone.utc) if now is None else now
        expiry = datetime.fromisoformat(context["expires_at"].replace("Z", "+00:00"))
        before = datetime.fromisoformat(context["materialize_before"].replace("Z", "+00:00"))
        if (instant.tzinfo is None or expiry.tzinfo is None or before.tzinfo is None
                or expiry > STOP or before >= expiry or not instant < before):
            raise ValueError("Original API evidence expiry reached; no reset")
        counts = {category: 0 for category in CATEGORIES}
        entries, seen = [], set()
        total = 0
        self.context, self.now = context, now
        self.scope, self.quiescence, self.before = scope, quiescence, before
        self.counts, self.entries, self.seen, self.total = counts, entries, seen, total

    def add(self, row):
        context, now, scope, before = self.context, self.now, self.scope, self.before
        counts, entries, seen, total = self.counts, self.entries, self.seen, self.total
        if now is None and datetime.now(timezone.utc) >= before:
            raise ValueError("Original API evidence expiry reached during materialization")
        if (len(entries) >= ROW_COUNT_CAP or type(row) is not dict
                or set(row) != {"category", "source_id", "body"}
                or type(row["category"]) is not str or row["category"] not in CATEGORIES or type(row["source_id"]) is not str
                or not 1 <= len(row["source_id"]) <= 200):
            raise ValueError("Complete bounded fixed-source API evidence row required")
        category, identifier = row["category"], row["source_id"]
        if (category, identifier) in seen:
            raise ValueError("Duplicate API evidence source identity")
        seen.add((category, identifier))
        counts[category] += 1
        if counts[category] > context["category_counts"][category]:
            raise ValueError("Additional row outside actual reserved evidence inventory")
        bounded_json(row["body"], ROW_CAP, max_nodes=600000)
        if type(row["body"]) is not dict:
            raise ValueError("Actual API source record object required")
        if any(key in row["body"] and str(row["body"][key]) != str(getattr(scope, key))
               for key in ("project_id", "plan_id", "episode_id", "generation")):
            raise ValueError("Foreign API evidence record scope")
        raw = canonical(row["body"])
        pin = hashlib.sha256(raw).hexdigest()
        total += len(raw)
        if total > REFERENCE_BYTES_CAP:
            raise ValueError("Complete referenced evidence exceeds derived original-table bounds; no truncation")
        entry = {"category": category, "source_id": identifier, "canonical_bytes": len(raw), "canonical_sha256": pin,
                 "encoding": "anvil.canonical-json.v1",
                 "custody": "immutable_api_snapshot" if category in SNAPSHOTS else "immutable_api_record"}
        entries.append(entry)
        self.total = total
        return (category, identifier, raw) if category in SNAPSHOTS else None

    def finish(self):
        context, now, scope, before = self.context, self.now, self.scope, self.before
        counts, entries, total, quiescence = self.counts, self.entries, self.total, self.quiescence
        if counts != context["category_counts"]:
            raise ValueError("Incomplete API evidence inventory; no truncation or partial readiness")
        roots = {key: context[key] for key in ("manifest_id", "enrollment_id", "request_sha256", "operation_nonce", "scope", "expires_at")}
        body = {"schema_version": "anvil.marketing-api-evidence-manifest.v1", **roots,
                "quiescence_id": str(quiescence.quiescence_id), "quiescence_receipt_sha256": quiescence.receipt_sha256,
                "fence_epoch": quiescence.fence_epoch, "graph_ledger_sha256": quiescence.graph_ledger_sha256,
                "reconstruction_sha256": quiescence.reconstruction_sha256, "category_counts": counts,
                "entry_count": len(entries), "raw_bytes_total": total,
                "entries": sorted(entries, key=lambda entry: (entry["category"], entry["source_id"])),
                "capture_accepted": False, "model_performance_validated": False}
        bounded_json(body, MANIFEST_CAP, max_nodes=MANIFEST_NODE_CAP)
        raw = canonical(body)
        pin = hashlib.sha256(raw).hexdigest()
        descriptor = {key: value for key, value in body.items() if key != "entries"}
        descriptor.update(schema_version="anvil.marketing-api-evidence-ready.v1", manifest_sha256=pin)
        bounded_json(descriptor, READY_DESCRIPTOR_CAP, max_nodes=3000)
        # Checked scope was parsed independently above; it is not a user assertion.
        if scope.model_dump(mode="json") != body["scope"]:
            raise ValueError("Canonical exact original evidence scope required")
        if now is None and datetime.now(timezone.utc) >= before:
            raise ValueError("Original API evidence expiry reached during materialization")
        return PreparedEvidence(raw, pin, (), descriptor)


def prepare(context, rows, *, now=None, retain_snapshot=None):
    """Synchronous software utility; live capture uses async bounded custody."""
    compiler = EvidenceCompiler(context, now=now)
    snapshots, cached = [], 0
    for row in rows:
        snapshot = compiler.add(row)
        if snapshot is not None:
            if retain_snapshot is None:
                cached += len(snapshot[2])
                if cached > SNAPSHOT_CACHE_CAP:
                    raise ValueError("Bounded streaming API snapshot custody required")
                snapshots.append(snapshot)
            else:
                retain_snapshot(*snapshot)
    result = compiler.finish()
    return PreparedEvidence(result.manifest, result.sha256, tuple(snapshots), result.descriptor)


async def prepare_async(context, rows, *, retain_snapshot, now=None):
    """One actual source row at a time, awaiting immutable snapshot custody."""
    compiler = EvidenceCompiler(context, now=now)
    async for row in rows:
        snapshot = compiler.add(row)
        if snapshot is not None:
            await retain_snapshot(*snapshot)
    return compiler.finish()


def _verification_steps(manifest, descriptor, *, now=None):
    """Private receiver reloads actual records; never trust row IDs/hashes alone.

    The caller must first load manifest/descriptor from the original immutable
    API store and compare the signed seal's exact descriptor hash. This function
    does not authenticate a caller, physical shutdown, seal or accepted capture.
    """
    if type(manifest) is not bytes or not 0 < len(manifest) <= MANIFEST_CAP:
        raise ValueError("Bounded retained API manifest bytes required")
    body = json_object(manifest)
    fields = {"schema_version", "manifest_id", "enrollment_id", "request_sha256", "operation_nonce", "scope", "expires_at",
              "quiescence_id", "quiescence_receipt_sha256", "fence_epoch", "graph_ledger_sha256", "reconstruction_sha256",
              "category_counts", "entry_count", "raw_bytes_total", "entries", "capture_accepted", "model_performance_validated"}
    if (set(body) != fields or body["schema_version"] != "anvil.marketing-api-evidence-manifest.v1"
            or type(body["entry_count"]) is not int or type(body["raw_bytes_total"]) is not int):
        raise ValueError("Exact immutable API manifest fields required")
    Scope.model_validate(body["scope"])
    _counts(body["category_counts"])
    if canonical(body) != manifest or hashlib.sha256(manifest).hexdigest() != descriptor.get("manifest_sha256"):
        raise ValueError("Original materialized API manifest digest differs")
    expected = {key: value for key, value in body.items() if key != "entries"}
    expected.update(schema_version="anvil.marketing-api-evidence-ready.v1", manifest_sha256=hashlib.sha256(manifest).hexdigest())
    if descriptor != expected:
        raise ValueError("Seal descriptor differs from actually issued API content")
    expiry = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    instant = datetime.now(timezone.utc) if now is None else now
    if instant.tzinfo is None or expiry.tzinfo is None or expiry > STOP or not instant < expiry:
        raise ValueError("Original API evidence expiry reached; no reset")
    counts = {category: 0 for category in CATEGORIES}
    seen, total = set(), 0
    if type(body.get("entries")) is not list or len(body["entries"]) > ROW_COUNT_CAP:
        raise ValueError("Bounded complete API manifest entries required")
    for entry in body["entries"]:
        if now is None and datetime.now(timezone.utc) >= min(expiry, STOP):
            raise ValueError("Original API evidence expiry reached during verification")
        if (type(entry) is not dict or set(entry) != {"category", "source_id", "canonical_bytes", "canonical_sha256", "encoding", "custody"}
                or type(entry["category"]) is not str or entry["category"] not in CATEGORIES
                or type(entry["source_id"]) is not str or not 1 <= len(entry["source_id"]) <= 200
                or entry["encoding"] != "anvil.canonical-json.v1"
                or entry["custody"] != ("immutable_api_snapshot" if entry["category"] in SNAPSHOTS else "immutable_api_record")):
            raise ValueError("Fixed complete original API entry required")
        key = (entry["category"], entry["source_id"])
        if key in seen:
            raise ValueError("Duplicate retained API evidence entry")
        seen.add(key)
        raw = yield key
        if (type(raw) is not bytes or not 0 < len(raw) <= ROW_CAP
                or type(entry["canonical_bytes"]) is not int or entry["canonical_bytes"] != len(raw)
                or hashlib.sha256(raw).hexdigest() != entry["canonical_sha256"]):
            raise ValueError("Missing or changed actual API evidence content")
        counts[entry["category"]] += 1
        total += len(raw)
    if (counts != body["category_counts"] or len(seen) != body["entry_count"] or total != body["raw_bytes_total"]
            or body["capture_accepted"] is not False or body["model_performance_validated"] is not False):
        raise ValueError("Incomplete API evidence category closure")
    if now is None and datetime.now(timezone.utc) >= expiry:
        raise ValueError("Original API evidence expiry reached during verification")
    return {"content_verified": True, "capture_accepted": False, "native_qualified": False}


def verify_content(manifest, descriptor, load_original, *, now=None):
    """Same fixed complete verification over synchronous private originals."""
    steps = _verification_steps(manifest, descriptor, now=now)
    try:
        key = next(steps)
        while True:
            key = steps.send(load_original(*key))
    except StopIteration as completed:
        return completed.value
    finally:
        steps.close()


async def verify_content_async(manifest, descriptor, load_original, *, now=None):
    """Same algorithm, awaited original custody; caller owns its original cutoff."""
    steps = _verification_steps(manifest, descriptor, now=now)
    try:
        key = next(steps)
        while True:
            key = steps.send(await load_original(*key))
    except StopIteration as completed:
        return completed.value
    finally:
        steps.close()
