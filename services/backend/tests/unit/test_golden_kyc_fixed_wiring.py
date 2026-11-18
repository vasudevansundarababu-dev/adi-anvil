"""Regression controls for fixed software execution; no native admission claims."""

import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from anvil import golden_kyc_harbor as harbor
from anvil.golden_kyc_identity import enter


def test_denied_read_stops_without_next_action_or_completed_receipt(monkeypatch):
    calls = []

    @contextmanager
    def connections():
        try:
            yield object()
        except BaseException:
            pytest.fail("Denied action evidence must commit before the failure is raised")

    monkeypatch.setattr(harbor, "tick", lambda *a, **k: None)

    def denied(*args):
        calls.append(args[-2])
        return {"status": "denied", "result": None}

    monkeypatch.setattr(harbor, "step", denied)
    monkeypatch.setattr(harbor, "locked", lambda *a: pytest.fail("Denied read cannot complete"))
    context = SimpleNamespace(
        connections=connections,
        project="p",
        user="u",
        trial_id="t",
        trial_token="synthetic",
        script=(
            {"action": "application.read", "arguments": {}},
            {"action": "documents.list", "arguments": {}},
        ),
    )
    with pytest.raises(ValueError, match="did not complete"):
        harbor.execute_software_script(context)
    assert calls == ["application.read"]


def test_sealed_opa_binding_replaces_ambient_and_restores_after_failure(tmp_path, monkeypatch):
    path = tmp_path / "opa"
    path.write_bytes(b"test-only executable bytes")
    path.chmod(0o700)
    pin = hashlib.sha256(path.read_bytes()).hexdigest()

    class Store:
        def _sealed_file(self, supplied, expected):
            assert (
                Path(supplied) == path and hashlib.sha256(path.read_bytes()).hexdigest() == expected
            )

    monkeypatch.setenv("ANVIL_OPA_BINARY", "untrusted-ambient")
    monkeypatch.delenv("ANVIL_OPA_SHA256", raising=False)
    with pytest.raises(RuntimeError, match="operation failure"):
        with harbor.fixed_policy_runtime(
            Store(), {"binaries": {"opa": {"path": str(path), "sha256": pin}}}
        ):
            assert os.environ["ANVIL_OPA_BINARY"] == str(path)
            assert os.environ["ANVIL_OPA_SHA256"] == pin
            raise RuntimeError("operation failure")
    assert os.environ["ANVIL_OPA_BINARY"] == "untrusted-ambient"
    assert "ANVIL_OPA_SHA256" not in os.environ


@pytest.mark.parametrize(
    "failure",
    [
        "rolsuper",
        "rolbypassrls",
        "rolcreatedb",
        "rolcreaterole",
        "rolreplication",
        "mixed",
        "access",
    ],
)
def test_runtime_login_rejects_privilege_before_setting_role(failure):
    observed = []
    role = dict.fromkeys(
        ("rolsuper", "rolbypassrls", "rolcreatedb", "rolcreaterole", "rolreplication"), False
    )
    role.update(rolcanlogin=True, original_login=True, assigned=True)
    role[failure] = True

    class Connection:
        def execute(self, query, params=None):
            observed.append(query)
            row = (
                {"access": failure == "access"}
                if "has_table_privilege" in query
                else {"mixed": failure == "mixed"}
                if " AS mixed" in query
                else role
            )
            return SimpleNamespace(fetchone=lambda: row)

    with pytest.raises(RuntimeError, match="disjoint"):
        enter(Connection(), "anvil_golden_scheduler", "project")
    assert not any(query.startswith("SET LOCAL ROLE") for query in observed)
