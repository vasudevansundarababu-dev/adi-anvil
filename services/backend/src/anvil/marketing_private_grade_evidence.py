"""Protected API originals for grading, without fabricating a controller seal.

No HTTP route/authentication, signing/key access or qualification is minted here.
Only an already authenticated private API caller may supply original enrollment
and actually issued descriptor pins. Scoped SQL remains a separate trust gate.
"""

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from pydantic import TypeAdapter

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import Sha, json_object
from anvil.marketing_attester_enrollment import freeze_original
from anvil.marketing_capture_database import remaining
from anvil.marketing_capture_evidence import (
    MANIFEST_CAP,
    MANIFEST_NODE_CAP,
    ROW_CAP,
    ROW_COUNT_CAP,
    verify_content_async,
)
from anvil.marketing_capture_peer import FrameworkIdentityProvenance
from anvil.marketing_capture_verifier import Identity
from anvil.marketing_world_quiescence import Quiescence
from anvil.praxis_generic_contract import canonical, digest

MANIFEST_SQL = "SELECT marketing_runtime.private_grade_evidence(%s,%s) AS value"
ORIGINAL_SQL = "SELECT marketing_runtime.private_grade_original(%s,%s,%s,%s) AS value"


@dataclass(frozen=True, slots=True)
class NativeGradeRecord:
    category: str
    source_id: str
    canonical_bytes: bytes = field(repr=False)
    sha256: str


class NativeGradeEvidence:
    """Connection-bound complete original read capability, not OS/native admission.

    Ordinary actor/SDK projections must never receive this object or its bytes.
    No serialization/reattach is supported. Independent source/profile and process
    qualification must still precede a qualified private verifier execution.
    """

    def __init__(self, connection, original, manifest_id, manifest, descriptor, identity, framework_provenance, deadline):
        self._connection, self._original, self._manifest_id = connection, original, manifest_id
        self._manifest, self._descriptor, self._deadline = manifest, canonical(descriptor), deadline
        self._identity, self._framework_provenance = canonical(identity), canonical(framework_provenance)
        body = json_object(manifest)
        bounded_json(body, MANIFEST_CAP, max_nodes=MANIFEST_NODE_CAP)
        entries = body.get("entries")
        if type(entries) is not list or len(entries) > ROW_COUNT_CAP or any(type(entry) is not dict for entry in entries):
            raise ValueError("Bounded complete original entry inventory required")
        self._entries = {(entry["category"], entry["source_id"]):
                         (entry["canonical_bytes"], entry["canonical_sha256"])
                         for entry in entries}
        if len(self._entries) != len(entries):
            raise ValueError("Duplicate original evidence source identity")
        self._complete = False

    def __reduce__(self):
        raise TypeError("Private original evidence capability cannot be serialized")

    def provenance(self):
        if not self._complete:
            raise ValueError("Complete private original custody not verified")
        remaining(self._deadline)
        return {"schema_version": "anvil.marketing-native-grade-provenance.v1",
                "origin": "api_immutable_native_records", "enrollment_id": str(self._original.enrollment_id),
                "request_sha256": self._original.request_sha256, "operation_nonce": self._original.operation_nonce,
                "identity": json_object(self._identity), "framework_identity_provenance": json_object(self._framework_provenance),
                "manifest_id": str(self._manifest_id), "manifest_sha256": hashlib.sha256(self._manifest).hexdigest(),
                "descriptor_sha256": hashlib.sha256(self._descriptor).hexdigest(),
                "scope": self._original.scope.model_dump(mode="json"), "record_count": len(self._entries),
                "capture_accepted": False, "native_qualified": False, "mapping_qualified": False,
                "run_authority": "not_granted"}

    async def _read(self, category, source_id):
        remaining(self._deadline)
        if self._connection.closed or (category, source_id) not in self._entries:
            raise ValueError("Exact live private original record required")
        row = await (await self._connection.execute(ORIGINAL_SQL, (
            self._original.enrollment_id, self._manifest_id, category, source_id,
        ))).fetchone()
        value = row["value"] if row else None
        if type(value) is not dict:
            raise ValueError("Actual private original unavailable")
        if value.get("encoding") == "retained_canonical_utf8":
            raw = value["canonical_body"].encode()
        elif value.get("encoding") == "original_immutable_record":
            bounded_json(value["body"], ROW_CAP, max_nodes=600000)
            raw = canonical(value["body"])
        else:
            raise ValueError("Exact actual private record encoding required")
        size, fingerprint = self._entries[(category, source_id)]
        if not 0 < len(raw) <= ROW_CAP or size != len(raw) or hashlib.sha256(raw).hexdigest() != fingerprint:
            raise ValueError("Original private evidence changed")
        remaining(self._deadline)
        return raw

    async def records(self):
        if not self._complete:
            raise ValueError("Complete actual private custody must be verified first")
        for category, source_id in self._entries:
            raw = await self._read(category, source_id)
            yield NativeGradeRecord(category, source_id, raw, self._entries[(category, source_id)][1])
            remaining(self._deadline)


async def load_native_evidence(connection, original, manifest_id, descriptor_sha256, *, absolute_deadline):
    """Load/verify all originals once; no capture-upload intent or synthetic seal.

    Connection must remain in the caller's original bounded read-only transaction
    while the fixed private binder consumes records. There is no new connection,
    credentials, provider call, materialization, poll, retry or clock extension.
    """
    original = freeze_original(original)
    if type(manifest_id) is not UUID:
        raise ValueError("Actual issued manifest ID required")
    TypeAdapter(Sha).validate_python(descriptor_sha256, strict=True)
    remaining(absolute_deadline)
    remaining(connection.capture_deadline)
    hard = min(absolute_deadline, connection.capture_deadline)
    connection.capture_deadline = hard
    async with asyncio.timeout(remaining(hard)):
        row = await (await connection.execute(MANIFEST_SQL, (original.enrollment_id, manifest_id))).fetchone()
        value = row["value"] if row else None
        if type(value) is not dict:
            raise ValueError("Anvil actual materialized private evidence required")
        fields = {"schema_version", "origin", "enrollment_id", "manifest_id", "canonical_body", "manifest_sha256",
                  "descriptor", "quiescence", "quiescence_stored_sha256", "capture_accepted", "native_qualified", "run_authority",
                  "identity", "framework_identity_provenance"}
        if (set(value) != fields or value["schema_version"] != "anvil.marketing-private-grade-evidence.v1"
                or value["origin"] != "api_immutable_native_records" or value["capture_accepted"] is not False
                or value["native_qualified"] is not False or value["run_authority"] != "not_granted"
                or value["enrollment_id"] != str(original.enrollment_id) or value["manifest_id"] != str(manifest_id)
                or type(value["canonical_body"]) is not str):
            raise ValueError("Original protected API evidence scope changed")
        manifest = value["canonical_body"].encode()
        if not 0 < len(manifest) <= MANIFEST_CAP or hashlib.sha256(manifest).hexdigest() != value["manifest_sha256"]:
            raise ValueError("Actual API manifest integrity changed")
        descriptor = value["descriptor"]
        bounded_json(value["identity"], 4096, max_nodes=100, max_depth=4)
        bounded_json(value["framework_identity_provenance"], 4096, max_nodes=100, max_depth=4)
        identity = Identity.model_validate_json(canonical(value["identity"]))
        framework_provenance = FrameworkIdentityProvenance.model_validate_json(canonical(value["framework_identity_provenance"]))
        if (identity.job_id != original.scope.job_id or identity.request_sha256 != original.request_sha256
                or identity.operation_nonce != original.operation_nonce or framework_provenance.boot_id != original.boot_id
                or framework_provenance.original_plan_sha256 != identity.plan_sha256):
            raise ValueError("Original authenticated SDK framework identity changed")
        bounded_json(descriptor, 3072, max_nodes=1000, max_depth=8)
        quiescence = Quiescence.model_validate(value["quiescence"])
        if (digest(descriptor) != descriptor_sha256 or descriptor["scope"] != original.scope.model_dump(mode="json")
                or descriptor["enrollment_id"] != str(original.enrollment_id)
                or descriptor["request_sha256"] != original.request_sha256
                or descriptor["operation_nonce"] != original.operation_nonce
                or datetime.fromisoformat(descriptor["expires_at"].replace("Z", "+00:00")) != original.expires_at
                or digest(value["quiescence"]) != value["quiescence_stored_sha256"]
                or descriptor["quiescence_receipt_sha256"] != quiescence.receipt_sha256):
            raise ValueError("Original actual world quiescence and evidence binding changed")
        evidence = NativeGradeEvidence(connection, original, manifest_id, manifest, descriptor,
                                       identity.model_dump(mode="json"), framework_provenance.model_dump(mode="json"), hard)
        await verify_content_async(manifest, descriptor, evidence._read)
        remaining(hard)
        evidence._complete = True  # Completeness only, explicitly NOT native qualification.
        return evidence
