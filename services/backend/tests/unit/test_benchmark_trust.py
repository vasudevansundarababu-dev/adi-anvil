import base64
import json
import os
from contextlib import contextmanager

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from anvil.benchmark_trust import load_trust_policy


@contextmanager
def policy_location(value):
    original = os.environ.get("ANVIL_BENCHMARK_TRUST_POLICY")
    if value is None:
        os.environ.pop("ANVIL_BENCHMARK_TRUST_POLICY", None)
    else:
        os.environ["ANVIL_BENCHMARK_TRUST_POLICY"] = str(value)
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("ANVIL_BENCHMARK_TRUST_POLICY", None)
        else:
            os.environ["ANVIL_BENCHMARK_TRUST_POLICY"] = original


def public_policy():
    private = Ed25519PrivateKey.generate()
    return {
        "schema_version": "anvil.benchmark.trust.v1",
        "keys": [
            {
                "key_id": "software-test-root",
                "public_key_base64": base64.b64encode(
                    private.public_key().public_bytes_raw()
                ).decode(),
                "not_before": "2026-01-01T00:00:00Z",
                "not_after": "2027-01-01T00:00:00Z",
                "revoked": False,
            }
        ],
    }


def test_absent_roots_never_trust_supplied_source_keys():
    with policy_location(None):
        assert load_trust_policy() == {}


def test_public_file_is_strict_and_revocation_is_reloaded(tmp_path):
    path = tmp_path / "benchmark-trust-policy.json"
    policy = public_policy()
    path.write_text(json.dumps(policy))
    path.chmod(0o600)
    with policy_location(path):
        assert not load_trust_policy()["software-test-root"].revoked
        policy["keys"][0]["revoked"] = True
        path.write_text(json.dumps(policy))
        assert load_trust_policy()["software-test-root"].revoked


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "extra", "numeric_bool", "key_bytes", "expired_order", "world_write", "symlink"],
)
def test_misconfigured_policy_fails_closed_without_dumping_fields(tmp_path, mutation):
    path = tmp_path / "benchmark-trust-policy.json"
    policy = public_policy()
    if mutation == "duplicate":
        policy["keys"].append(dict(policy["keys"][0]))
    elif mutation == "extra":
        policy["keys"][0]["unsupported_field"] = "not a real credential"
    elif mutation == "numeric_bool":
        policy["keys"][0]["revoked"] = 0
    elif mutation == "key_bytes":
        policy["keys"][0]["public_key_base64"] = "A" * 44
    elif mutation == "expired_order":
        policy["keys"][0]["not_before"] = "2028-01-01T00:00:00Z"
    path.write_text(json.dumps(policy))
    path.chmod(0o666 if mutation == "world_write" else 0o600)
    if mutation == "symlink":
        alias = tmp_path / "policy-alias.json"
        alias.symlink_to(path)
        path = alias
    with policy_location(path):
        with pytest.raises(RuntimeError) as exc:
            load_trust_policy()
        assert str(exc.value) == "Invalid installation benchmark trust policy"
