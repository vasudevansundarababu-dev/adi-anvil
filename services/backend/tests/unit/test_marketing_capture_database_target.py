"""Configuration custody and safe readiness only; no connection or DNS."""

import json
import os

import pytest

from anvil import marketing_capture_database_target as target

BASE = "host=original-db.example hostaddr=192.0.2.1 port=5432 dbname=private_test_database user=private_test_role sslmode=verify-full gssencmode=disable"


@pytest.fixture(autouse=True)
def private_configuration(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith("PG") or name == target.PIN:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(target, "setting", lambda _: BASE + " password=TEST_DATABASE_PASSWORD_NEVER_RETURN")


def test_exact_numeric_binding_preserves_tls_hostname_and_credentials_privately(monkeypatch):
    parameters, pin = target.inspect_target()
    monkeypatch.setenv(target.PIN, pin)
    bound, actual = target.configuration()
    assert bound == parameters and actual == pin
    assert bound["host"] == "original-db.example" and bound["hostaddr"] == "192.0.2.1"
    assert bound["sslmode"] == "verify-full" and bound["password"] == "TEST_DATABASE_PASSWORD_NEVER_RETURN"
    status = target.readiness()
    assert status["configuration_ready"] is True
    assert status["ready"] is status["runtime_qualified"] is status["connection_probe_performed"] is False
    public = json.dumps(status)
    assert all(secret not in public for secret in ("TEST_DATABASE_PASSWORD_NEVER_RETURN", "original-db.example", "192.0.2.1", "private_test_database", "private_test_role"))


@pytest.mark.parametrize("pin,code", [(None, "capture_database_binding_pin_required"), ("f" * 64, "capture_database_binding_pin_stale")])
def test_missing_or_stale_binding_is_not_configuration_ready(monkeypatch, pin, code):
    if pin:
        monkeypatch.setenv(target.PIN, pin)
    assert target.readiness()["reason"] == code
    with pytest.raises(target.TargetUnavailable, match=code):
        target.configuration()


@pytest.mark.parametrize("change,code", [
    ("hostaddr=", "capture_database_numeric_binding_required"),
    ("hostaddr=192.0.2.1,192.0.2.2", "capture_database_single_target_required"),
    ("port=5432,5433", "capture_database_single_target_required"),
    ("port=65536", "capture_database_single_target_required"),
    ("target_session_attrs=prefer-standby", "capture_database_failover_denied"),
    ("load_balance_hosts=random", "capture_database_failover_denied"),
    ("sslmode=prefer", "capture_database_nonfallback_security_profile_required"),
    ("gssencmode=prefer", "capture_database_nonfallback_security_profile_required"),
    ("service=unqualified", "capture_database_service_expansion_denied"),
])
def test_unqualified_targets_never_become_ready_or_expose_private_configuration(monkeypatch, change, code):
    keyword = change.split("=")[0]
    parts = [part for part in BASE.split() if not part.startswith(keyword + "=")]
    monkeypatch.setattr(target, "setting", lambda _: " ".join(parts) + " " + change)
    value = target.readiness()
    assert value["reason"] == code and value["configuration_ready"] is False and value["ready"] is False


def test_environment_expansion_is_bound_and_changed_address_invalidates_pin(monkeypatch):
    monkeypatch.setattr(target, "setting", lambda _: BASE.replace(" hostaddr=192.0.2.1", ""))
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
    _, pin = target.inspect_target()
    monkeypatch.setenv(target.PIN, pin)
    assert target.readiness()["configuration_ready"]
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.2")
    assert target.readiness()["reason"] == "capture_database_binding_pin_stale"


def test_secret_changes_do_not_enter_nonsecret_target_pin(monkeypatch):
    _, first = target.inspect_target()
    monkeypatch.setattr(target, "setting", lambda _: BASE + " password=DIFFERENT_TEST_SECRET sslpassword=ANOTHER_TEST_SECRET")
    _, second = target.inspect_target()
    assert first == second
