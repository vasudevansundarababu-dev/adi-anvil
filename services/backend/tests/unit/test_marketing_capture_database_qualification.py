"""Qualification admission controls, not actual database execution evidence."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from anvil import marketing_capture_database_qualification as q
from anvil import marketing_capture_database_target as target

NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)
TARGET = "a" * 64
IDENTITY = {"source_sha256": "b" * 64, "image_sha256": "c" * 64,
            "psycopg_version": "test-only", "libpq_version": 170006, "cancel_safe": True}


def receipt():
    return {
        "schema_version": q.SCHEMA, "scope": q.SCOPE, "origin": "independent_qa",
        "qualified": True, "revoked": False, "spending_authority": False,
        "issued_at": NOW.isoformat(), "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "target_sha256": TARGET, "runtime_identity": deepcopy(IDENTITY),
        "role_profile_sha256": "d" * 64, "observed_target_sha256": "e" * 64,
        "probe_evidence_sha256": "f" * 64, "review_receipt_sha256": "1" * 64,
        "checks": {key: {"status": "passed", "evidence_sha256": "2" * 64} for key in q.CHECKS},
    }


def test_current_exact_scoped_receipt_returns_only_safe_projection():
    result = q.validate(receipt(), TARGET, IDENTITY, now=NOW)
    assert result["scope"] == q.SCOPE and result["spending_authority"] is False
    assert set(result) == {"schema_version", "scope", "receipt_sha256", "target_sha256", "expires_at", "spending_authority"}


@pytest.mark.parametrize("field,value", [
    ("scope", "technical_components_only"), ("scope", "capture_registrar"),
    ("origin", "uploaded"), ("qualified", 1), ("revoked", True),
    ("spending_authority", True), ("target_sha256", "3" * 64),
    ("expires_at", NOW.isoformat()), ("expires_at", "2026-11-21T00:00:00Z"),
    ("issued_at", "2026-11-20T00:00:00Z"), ("issued_at", "2026-11-19T00:00:00"),
    ("issued_at", None), ("expires_at", 123),
    ("runtime_identity", IDENTITY | {"image_sha256": "4" * 64}),
    ("runtime_identity", IDENTITY | {"libpq_version": 170007}),
    ("runtime_identity", IDENTITY | {"source_sha256": "5" * 64}),
    ("review_receipt_sha256", None), ("probe_evidence_sha256", "not-a-hash"),
    ("checks", {}),
])
def test_changed_revoked_expired_or_unreviewed_evidence_is_denied(field, value):
    body = receipt()
    body[field] = value
    with pytest.raises((ValueError, TypeError)):
        q.validate(body, TARGET, IDENTITY, now=NOW)


@pytest.mark.parametrize("check", q.CHECKS)
def test_each_actual_control_is_required(check):
    body = receipt()
    body["checks"][check]["status"] = "unknown"
    with pytest.raises(ValueError):
        q.validate(body, TARGET, IDENTITY, now=NOW)


def test_uploaded_receipt_path_is_never_accepted(monkeypatch, tmp_path):
    file = tmp_path / "uploaded.json"
    file.write_text("{}")
    monkeypatch.setenv(q.FILE, str(file))
    monkeypatch.setattr(q, "runtime_identity", lambda: pytest.fail("Uploaded data cannot reach admission"))
    assert q.installed(TARGET) is None


def test_same_path_trust_rotation_invalidates_target_pin(monkeypatch, tmp_path):
    cert = tmp_path / "ca.pem"
    cert.write_bytes(b"test public trust anchor A")
    monkeypatch.setattr(target, "setting", lambda _: "host=db hostaddr=192.0.2.1 dbname=test user=test sslmode=verify-full gssencmode=disable sslrootcert=" + str(cert))
    _, first = target.inspect_target()
    monkeypatch.setenv(target.PIN, first)
    cert.write_bytes(b"test public trust anchor B")
    assert target.readiness()["reason"] == "capture_database_binding_pin_stale"


def test_unbound_trust_directory_is_rejected(monkeypatch):
    monkeypatch.setattr(target, "setting", lambda _: "host=db hostaddr=192.0.2.1 dbname=test user=test sslmode=verify-full gssencmode=disable sslcrldir=/unbound")
    assert target.readiness()["reason"] == "capture_database_trust_file_required"


def test_writable_trust_file_cannot_qualify_transport(tmp_path):
    ca = tmp_path / "ca.pem"
    ca.write_text("test public CA")
    with pytest.raises(ValueError, match="Immutable operator trust"):
        q.trusted_transport({"host": "db", "sslmode": "verify-full", "sslrootcert": str(ca)})
