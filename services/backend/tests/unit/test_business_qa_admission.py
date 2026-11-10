import pytest
from fastapi import HTTPException

from anvil.benchmark_business_admission import enabled
from anvil.benchmark_rehearsal import PAID_FLAGS


def test_cloud_business_gate_requires_exact_source_and_all_paid_paths_off(monkeypatch):
    from anvil import benchmark_runs

    monkeypatch.setenv("ANVIL_ENV", "cloud")
    with pytest.raises(HTTPException) as error:
        enabled()
    assert error.value.status_code == 503
    monkeypatch.setenv("ANVIL_BUSINESS_QA_ENABLED", "true")
    monkeypatch.setenv("ANVIL_QA_ACCEPTANCE_CONTROLS_ENABLED", "true")
    monkeypatch.setenv("ANVIL_BUSINESS_QA_SOURCE_SHA256", "a" * 64)
    monkeypatch.setattr(benchmark_runs, "source_hash", lambda: "b" * 64)
    for key in (*PAID_FLAGS, "ANVIL_IMPORT_GENERATION_ENABLED", "ANVIL_GENERATION_ENABLED"):
        monkeypatch.setenv(key, "false")
    with pytest.raises(HTTPException) as error:
        enabled()
    assert error.value.status_code == 409
    monkeypatch.setenv("ANVIL_BUSINESS_QA_SOURCE_SHA256", "b" * 64)
    enabled()
    for key in PAID_FLAGS:
        monkeypatch.setenv(key, "true")
        with pytest.raises(HTTPException):
            enabled()
        monkeypatch.setenv(key, "false")


def test_local_business_gate_still_uses_original_local_rehearsal(monkeypatch):
    monkeypatch.setenv("ANVIL_ENV", "local")
    monkeypatch.delenv("ANVIL_LOCAL_FIXTURE_ENABLED", raising=False)
    with pytest.raises(HTTPException) as error:
        enabled()
    assert error.value.status_code == 503
