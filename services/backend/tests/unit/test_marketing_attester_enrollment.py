"""Public-only synthetic handshake, no key generation or live registration."""

import asyncio
import hashlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from time import monotonic
from uuid import UUID

import pytest

from anvil.marketing_attester_enrollment import (
    ENROLL_SQL,
    OriginalBinding,
    check_original,
    parse_public_ready,
    register_public_ready,
    validate_receipt,
)
from anvil.marketing_capture_status import CONTROLS
from anvil.marketing_native_capture_budget import KIND_LIMITS
from anvil.praxis_generic_contract import canonical, digest


def packet(*, now=None):
    now = datetime(2026, 11, 14, tzinfo=timezone.utc) if now is None else now
    pub = "11" * 32  # Fixed PUBLIC test bytes; no private key exists in this test.
    ready = {"schema_version": "anvil.marketing-attester-public-ready.v1", "peer_binding_id": str(UUID(int=1)),
             "request_sha256": "a" * 64, "operation_nonce": "b" * 64, "boot_id": str(UUID(int=2)),
             "profile_sha256": "c" * 64, "public_key_hex": pub,
             "public_key_fingerprint_sha256": hashlib.sha256(bytes.fromhex(pub)).hexdigest()}
    scope = {key: str(UUID(int=number)) for number, key in enumerate(
        ("project_id", "job_id", "plan_id", "world_binding_id", "episode_id"), 10)}
    scope.update(world_binding_sha256="d" * 64, generation=0, lease_sha256="e" * 64,
                 source_qualification_sha256="f" * 64, execution_sha256="1" * 64)
    transport = {"schema_version": "anvil.marketing-status-transport-qualification.v1",
                 "origin": "https://anvil-qa.adi-labs.ai", "path": "/api/v1/integrations/marketing/native-capture/evidence-status",
                 "method": "GET", "api_image_digest": "sha256:" + "a" * 64,
                 "source_sha256": "a" * 64, "ingress_evidence_sha256": "b" * 64, "ca_bundle_sha256": "c" * 64,
                 "not_after": (now + timedelta(seconds=120)).isoformat(), "cleanup_reserve_seconds": 10,
                 "controls": {name: {"status": "passed", "evidence_sha256": "a" * 64} for name in CONTROLS}}
    original = {key: ready[key] for key in ("peer_binding_id", "request_sha256", "operation_nonce", "boot_id", "profile_sha256")}
    original.update(enrollment_id=str(UUID(int=3)), producer_qualification_sha256="2" * 64,
                    status_transport_sha256=digest(transport), scope=scope,
                    expires_at=(now + timedelta(seconds=90)).isoformat())
    receipt = {key: original[key] for key in ("enrollment_id", "request_sha256", "operation_nonce", "boot_id",
                                             "profile_sha256", "producer_qualification_sha256", "scope", "expires_at")}
    receipt.update(manifest_id=str(UUID(int=4)), public_key_hex=pub,
                   body_schema="anvil.marketing-native-capture-submission.v2", document_limits=dict(KIND_LIMITS),
                   wire_limit=1048576, status_transport=transport, capture_accepted=False, run_authority="not_granted")
    return ready, OriginalBinding.model_validate_json(canonical(original)), receipt, now


def test_exact_public_ready_and_server_receipt_preserve_original_scope_without_authority():
    ready, original, receipt, now = packet()
    parsed = parse_public_ready(canonical(ready))
    result = validate_receipt(receipt, original, parsed, now=now)
    assert result.capture_accepted is False and result.run_authority == "not_granted"
    assert result.scope == original.scope and result.public_key_hex == ready["public_key_hex"]


@pytest.mark.parametrize("change", ["private_key", "pid", "sign_body", "fingerprint", "duplicate", "noncanonical", "oversize"])
def test_untrusted_or_noncanonical_extra_capability_material_is_rejected_without_echo(change):
    ready, _, _, _ = packet()
    if change in ("private_key", "pid", "sign_body"):
        ready[change] = "SYNTHETIC-UNTRUSTED-SENSITIVE-VALUE"
    elif change == "fingerprint":
        ready["public_key_fingerprint_sha256"] = "f" * 64
    raw = canonical(ready)
    if change == "duplicate":
        raw = b'{"boot_id":"shadow",' + raw[1:]
    elif change == "noncanonical":
        raw = b" " + raw
    elif change == "oversize":
        raw = b"x" * 2049
    with pytest.raises(ValueError) as caught:
        parse_public_ready(raw)
    assert "SYNTHETIC-UNTRUSTED-SENSITIVE-VALUE" not in str(caught.value)


@pytest.mark.parametrize("key,value", [("request_sha256", "f" * 64), ("operation_nonce", "f" * 64),
                                      ("profile_sha256", "f" * 64), ("boot_id", str(UUID(int=99)))])
def test_public_message_cannot_select_another_original_operation(key, value):
    ready, original, _, _ = packet()
    ready[key] = value
    with pytest.raises(ValueError, match="operation binding changed"):
        check_original(parse_public_ready(canonical(ready)), original)


@pytest.mark.parametrize("change", ["scope", "expiry", "transport", "key", "caps", "flag"])
def test_changed_or_unretainable_server_readback_blocks_before_sdk(change):
    ready, original, receipt, now = packet()
    receipt = deepcopy(receipt)
    if change == "scope":
        receipt["scope"]["generation"] = 1
    elif change == "expiry":
        receipt["expires_at"] = (now + timedelta(seconds=100)).isoformat()
    elif change == "transport":
        receipt["status_transport"]["ca_bundle_sha256"] = "f" * 64
    elif change == "key":
        receipt["public_key_hex"] = "22" * 32
    elif change == "caps":
        receipt["document_limits"]["capture_seal"] = 1
    else:
        receipt["capture_accepted"] = 0
    with pytest.raises(ValueError):
        validate_receipt(receipt, original, parse_public_ready(canonical(ready)), now=now)


def test_one_original_bounded_operator_call_has_no_retry_or_new_deadline():
    ready, original, receipt, _ = packet(now=datetime.now(timezone.utc))

    class Connection:
        capture_deadline = monotonic() + 1
        calls = []

        async def execute(self, sql, params):
            self.calls.append((sql, params))
            return self

        async def fetchone(self):
            return {"value": receipt}

    connection = Connection()
    original_cutoff = connection.capture_deadline
    result = asyncio.run(register_public_ready(connection, canonical(ready), original,
                                               absolute_deadline=original_cutoff + 100))
    assert result.capture_accepted is False and connection.capture_deadline == original_cutoff
    assert connection.calls == [(ENROLL_SQL, (UUID(ready["peer_binding_id"]), ready["public_key_hex"]))]
