"""Protocol negatives; these do not substitute for physical Linux qualification."""

import threading
import time
from types import SimpleNamespace

import pytest

from anvil.golden_native_guardian import PURPOSE, GuardianServer, signed, verify
from anvil.golden_native_peer import SDKPeerLease


def test_worker_known_mac_only_binds_message_and_detects_mutation():
    key = "a" * 64
    packet = signed({"purpose": PURPOSE, "nonce": "b" * 32}, key)
    assert verify(packet, key)["purpose"] == PURPOSE
    packet["body"]["purpose"] = "paid_result"
    with pytest.raises(ValueError):
        verify(packet, key)


def server():
    value = object.__new__(GuardianServer)
    value.request = {"binding_sha256": "a" * 64, "gateway_token": "b" * 64,
                     "original_deadline_monotonic": time.monotonic() + 30}
    value.sequence, value.lock = 0, threading.Lock()
    value.purpose = PURPOSE
    value.holder = {"_callback_closing": threading.Event()}
    value.plan = SimpleNamespace(body=lambda: {})
    return value


def test_missing_dead_or_released_sdk_never_grants_status():
    value = server()
    with pytest.raises(ValueError, match="Active original"):
        value.status("/status/1/" + "c" * 32, "a" * 64, {})
    lease = SDKPeerLease(lambda: (_ for _ in ()).throw(ValueError("SDK dead")))
    value.holder["_sdk_peer_lease"] = lease
    with pytest.raises(ValueError, match="SDK dead"):
        value.status("/status/2/" + "d" * 32, "a" * 64, {})
    lease.closed = True
    with pytest.raises(ValueError, match="released"):
        lease.check()


def test_sequence_and_closing_are_fail_closed_even_with_valid_mac_key():
    value = server()
    observed = []
    value.holder["_sdk_peer_lease"] = SDKPeerLease(lambda: observed.append("live"))
    route = "/status/1/" + "c" * 32
    packet = value.status(route, "a" * 64, {})
    assert verify(packet, "b" * 64)["nonce"] == "c" * 32
    assert observed == ["live", "live"]
    with pytest.raises(ValueError, match="once-only"):
        value.status(route, "a" * 64, {})
    value.holder["_callback_closing"].set()
    with pytest.raises(ValueError, match="Active original"):
        value.status("/status/2/" + "d" * 32, "a" * 64, {})


def test_liveness_loss_during_plan_validation_denies_response():
    value = server()
    lease = SDKPeerLease(lambda: None)
    value.holder["_sdk_peer_lease"] = lease
    value.plan = SimpleNamespace(body=lambda: setattr(lease, "closed", True))
    with pytest.raises(ValueError, match="released"):
        value.status("/status/1/" + "c" * 32, "a" * 64, {})
