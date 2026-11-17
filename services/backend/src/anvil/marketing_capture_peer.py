"""Private independent-operator peer record, never promotion of diagnostics.

The qualified outside operator must obtain observations from actual owned handles
and verify independent evidence bytes/custody before calling. Models/hashes alone
are not OS identity or qualification. No ordinary API or registrar writer exists.
"""

import asyncio
import hashlib
import math
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from anvil.dataset_export_contract import Model, Sha, json_object
from anvil.marketing_attester_enrollment import OriginalBinding, PublicReady, check_original
from anvil.marketing_capture_attestation import STOP
from anvil.marketing_capture_verifier import Identity
from anvil.marketing_native_boundary import MarketingCampaignRequestV1, prepare_marketing_request
from anvil.marketing_native_records import MarketingRecordBytesV1
from anvil.marketing_native_wire_bounds import bounded_json, remaining
from anvil.praxis_generic_contract import canonical, digest
from anvil.schemas import Strict

REQUIRED_EVIDENCE = frozenset({"loaded_source_and_image_identity", "dumpability_and_proc_access",
                               "namespace_and_signal_isolation", "exact_allowed_fd_endpoint_custody",
                               "qualified_verifier_profile", "attester_key_and_public_ready_binding"})
STORE_SQL = "SELECT marketing_runtime.record_attester_peer(%s,%s,%s,%s,%s,%s,%s) AS value"


class EvidenceReference(Strict):
    policy_sha256: Sha
    receipt_sha256: Sha


class FrameworkIdentityProvenance(Strict):
    stage: Literal["post_sdk_G_pre_graph_work"]
    framework_entry_sha256: Sha
    original_plan_sha256: Sha
    sdk_pid: int = Field(strict=True, ge=1)
    sdk_start_ticks: int = Field(strict=True, ge=1)
    boot_id: UUID


class KernelPair(Model):
    device: int = Field(ge=0)
    inode: int = Field(ge=1)


class ActorMount(KernelPair):
    mount_id: int = Field(ge=1)


class BeforeGChild(Model):
    pid: int = Field(ge=1)
    start_ticks: int = Field(ge=1)
    parent_pid: int = Field(ge=1)
    pidfd_identity: KernelPair
    raw_pidfd_fdinfo: str = Field(min_length=1, max_length=1024)
    cgroup_path: str = Field(min_length=1, max_length=4096)
    cgroup_device: int = Field(ge=0)
    cgroup_inode: int = Field(ge=1)
    cgroup_mount_id: int = Field(ge=1)


class BeforeGChildren(Model):
    framework: BeforeGChild
    graph: BeforeGChild


class BeforeGActors(Model):
    schema_version: Literal["anvil.marketing-original-actors-before-G.v1"]
    request_sha256: Sha
    plan_sha256: Sha
    operation_nonce: Sha
    boot_id: UUID
    original_deadline_monotonic: float
    actor_scope_binding_sha256: Sha
    original_actor_scope: ActorMount
    children: BeforeGChildren
    capture_accepted: Literal[False]
    run_authority: Literal["not_granted"]

    @model_validator(mode="before")
    @classmethod
    def exact_observation_flag(cls, value):
        if type(value) is not dict or value.get("capture_accepted") is not False:
            raise ValueError("Original before-G observation grants no capture authority")
        return value


class IndependentOSReceipt(Strict):
    schema_version: Literal["anvil.marketing-attester-os-peer-receipt.v1"]
    channel_qualification_id: UUID
    producer_qualification_sha256: Sha
    verifier_profile_sha256: Sha
    framework_identity: Identity | None = None
    framework_identity_provenance: FrameworkIdentityProvenance | None = None
    preG_actor_observation: BeforeGActors | None = None
    observation: dict
    public_ready: PublicReady
    independent_evidence: dict[str, EvidenceReference]
    capture_accepted: Literal[False]
    run_authority: Literal["not_granted"]

    @model_validator(mode="after")
    def original_observation(self):
        observed = self.observation
        bounded_json(observed, 16384, max_nodes=4000, max_depth=8)
        fields = {"schema_version", "request_sha256", "operation_nonce", "boot_id", "original_deadline_monotonic",
                  "pid", "parent_pid", "start_ticks", "pidfd", "interpreter", "outside_cgroup",
                  "direct_kernel_snapshot", "second_identical_snapshot_sha256", "independent_evidence_still_required",
                  "diagnostic_only", "native_qualified", "admission_eligible", "capture_accepted", "run_authority"}
        required = observed.get("independent_evidence_still_required")
        if (set(observed) != fields
                or any(type(observed.get(key)) is not dict for key in
                       ("pidfd", "interpreter", "outside_cgroup", "direct_kernel_snapshot"))
                or type(required) is not list or any(type(item) is not str for item in required)
                or len(required) != len(REQUIRED_EVIDENCE) or set(required) != REQUIRED_EVIDENCE):
            raise ValueError("Complete original bounded observation required")
        if (observed.get("schema_version") != "anvil.marketing-attester-os-observation.v1"
                or observed.get("diagnostic_only") is not True
                or any(observed.get(key) is not False for key in
                       ("native_qualified", "admission_eligible", "capture_accepted"))
                or observed.get("run_authority") != "not_granted"
                or set(self.independent_evidence) != REQUIRED_EVIDENCE
                or observed.get("second_identical_snapshot_sha256") != digest(observed.get("direct_kernel_snapshot"))
                or observed.get("pidfd", {}).get("exit_readable_observed") is not False):
            raise ValueError("Complete diagnostic observation and independent evidence required")
        for key in ("pid", "parent_pid", "start_ticks"):
            if type(observed.get(key)) is not int or observed[key] < 1:
                raise ValueError("Actual owned process/pidfd observation required")
        clock = observed.get("original_deadline_monotonic")
        if type(clock) not in (int, float) or not math.isfinite(clock) or clock <= 0:
            raise ValueError("Original absolute monotonic cutoff required")
        if any(str(getattr(self.public_ready, key)) != observed.get(key)
               for key in ("request_sha256", "operation_nonce", "boot_id")):
            raise ValueError("Public key and original observed operation changed")
        if (self.framework_identity is None) != (self.framework_identity_provenance is None):
            raise ValueError("Actual framework entry and its retained process provenance required together")
        if self.framework_identity is not None:
            provenance = self.framework_identity_provenance
            if (provenance.original_plan_sha256 != self.framework_identity.plan_sha256
                    or provenance.boot_id != self.public_ready.boot_id):
                raise ValueError("Original SDK framework entry plan/boot changed")
        actors = self.preG_actor_observation
        if actors is not None:
            bounded_json(actors.model_dump(mode="json"), 8192, max_nodes=1000, max_depth=8)
            if (actors.request_sha256 != self.public_ready.request_sha256
                    or actors.operation_nonce != self.public_ready.operation_nonce or actors.boot_id != self.public_ready.boot_id
                    or actors.original_deadline_monotonic != clock
                    or actors.children.framework.pid == actors.children.graph.pid):
                raise ValueError("Original owned before-G actor observation changed")
            if self.framework_identity is not None:
                if (actors.plan_sha256 != self.framework_identity.plan_sha256
                        or actors.children.framework.pid != provenance.sdk_pid
                        or actors.children.framework.start_ticks != provenance.sdk_start_ticks):
                    raise ValueError("Authenticated framework entry does not match original before-G SDK process")
        return self


def parse_independent_receipt(raw):
    """Bounded, duplicate-free consistency parser, never an OS verifier."""
    if type(raw) is not bytes or not 0 < len(raw) <= 32768:
        raise ValueError("Bounded independent receipt bytes required")
    try:
        value = json_object(raw)
        if canonical(value) != raw or value.get("capture_accepted") is not False:
            raise ValueError("representation")
        receipt = IndependentOSReceipt.model_validate_json(raw)
        if canonical(receipt.model_dump(mode="json")) != raw:
            raise ValueError("representation")
        return receipt
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("Independent original peer receipt rejected") from None


def prepare_peer_record(request, records, original, receipt):
    """Consistency only; caller must be the independently qualified OS producer."""
    if (type(request) is not MarketingCampaignRequestV1 or type(records) is not MarketingRecordBytesV1
            or type(original) is not OriginalBinding or type(receipt) is not IndependentOSReceipt):
        raise ValueError("Original independent operator records required")
    prepare_marketing_request(request.canonical_bytes)
    # Freeze/revalidate nested model state before any await. A model instance or
    # mutable caller dict never constitutes independent qualification.
    supplied = receipt.model_dump(mode="json")
    bounded_json(supplied, 32768, max_nodes=6000, max_depth=10)
    receipt = parse_independent_receipt(canonical(supplied))
    check_original(receipt.public_ready, original)
    request_hash = hashlib.sha256(request.canonical_bytes).hexdigest()
    operation = json_object(records.operation_bytes)
    if (records.request_sha256 != request_hash or request_hash != original.request_sha256
            or operation.get("schema_version") != "anvil.marketing-native-operation.v1"
            or operation.get("origin") != "independent_operator"
            or operation.get("purpose") != "marketing_campaign_graph_v1"
            or operation.get("request_sha256") != request_hash
            or operation.get("manifest_sha256") != records.manifest_sha256
            or operation.get("job_id") != str(original.scope.job_id)
            or receipt.producer_qualification_sha256 != original.producer_qualification_sha256):
        raise ValueError("Original complete request and operation receipt changed")
    identity = receipt.framework_identity
    if identity is not None and (identity.job_id != original.scope.job_id
                                 or identity.request_sha256 != original.request_sha256
                                 or identity.operation_nonce != original.operation_nonce):
        raise ValueError("Original authenticated SDK framework operation identity changed")
    try:
        expires = datetime.fromisoformat(operation["expires_at"])
        stop = datetime.fromisoformat(operation["stop_at"])
        if expires.tzinfo is None or stop != STOP or original.expires_at > min(expires, STOP):
            raise ValueError("expiry")
    except (ValueError, KeyError, TypeError):
        raise ValueError("Original operation expiry or fixed stop changed") from None
    body = receipt.model_dump(mode="json")
    bounded_json(body, 32768, max_nodes=6000, max_depth=10)
    proof = canonical(body)
    if len(proof) > 32768 or len(records.operation_bytes) > 4096:
        raise ValueError("Original complete operator peer proof exceeds bound")
    return (original.peer_binding_id, original.enrollment_id, request.canonical_bytes.decode(),
            records.operation_bytes.decode(), canonical(original.scope.model_dump(mode="json")).decode(),
            proof.decode(), original.expires_at)


async def record_peer(connection, request, records, original, receipt, *, absolute_deadline):
    """One bounded private operator call; no privilege/qualification is minted.

    This is not reachable from public-ready/SDK/API/registrar code. The SQL gate
    authenticates the independent producer's existing qualified DB identity and
    channel profile, not a Python type or submitted approval flag.
    """
    params = prepare_peer_record(request, records, original, receipt)
    peer_id, _, request_raw, operation_raw, _, proof_raw, _ = params
    proof = json_object(proof_raw.encode())
    ready = proof["public_ready"]
    proof_sha = hashlib.sha256(proof_raw.encode()).hexdigest()
    operation_sha = hashlib.sha256(operation_raw.encode()).hexdigest()
    expected_header = {
        "schema_version": "anvil.marketing-attester-peer-binding.v1",
        "boot_id": ready["boot_id"], "profile_sha256": ready["profile_sha256"],
        "request_sha256": hashlib.sha256(request_raw.encode()).hexdigest(),
        "operation_nonce": ready["operation_nonce"], "public_key_sha256": ready["public_key_fingerprint_sha256"],
        "channel_qualification_sha256": proof["producer_qualification_sha256"],
        "os_peer_receipt_sha256": proof_sha, "operation_sha256": operation_sha,
    }
    remaining(absolute_deadline)
    remaining(connection.capture_deadline)
    hard = min(absolute_deadline, connection.capture_deadline)
    connection.capture_deadline = hard
    async with asyncio.timeout(remaining(hard)):
        row = await (await connection.execute(STORE_SQL, params)).fetchone()
        value = row["value"] if row else None
        if type(value) is not dict:
            raise RuntimeError("Independent original peer custody unavailable; no retry")
        bounded_json(value, 32768, max_nodes=1000, max_depth=8)
        header_raw = value.get("peer_canonical")
        fields = {"schema_version", "peer_binding_id", "peer_canonical", "peer_receipt_sha256",
                  "os_peer_receipt_sha256", "operation_sha256", "capture_accepted", "run_authority"}
        if (set(value) != fields or value.get("schema_version") != "anvil.marketing-attester-peer-recorded.v1"
                or value.get("peer_binding_id") != str(peer_id) or type(header_raw) is not str
                or value.get("os_peer_receipt_sha256") != proof_sha or value.get("operation_sha256") != operation_sha
                or value.get("capture_accepted") is not False or value.get("run_authority") != "not_granted"):
            raise RuntimeError("Independent original peer readback changed; no retry")
        if (json_object(header_raw.encode()) != expected_header
                or hashlib.sha256(header_raw.encode()).hexdigest() != value.get("peer_receipt_sha256")):
            raise RuntimeError("Independent original binding header changed; no retry")
        remaining(hard)
        return value
