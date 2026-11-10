"""QA admission must not activate legacy rehearsals or paid dispatch."""

import pytest
from fastapi import HTTPException

from anvil import environment_admission as admission
from anvil import environment_execution
from anvil.benchmark_rehearsal import PAID_FLAGS
from anvil.benchmark_rehearsal import enabled as legacy_enabled


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setenv("ANVIL_ENV", "cloud")
    monkeypatch.setenv("ANVIL_ENVIRONMENT_QA_ENABLED", "true")
    monkeypatch.setenv("ANVIL_ENVIRONMENT_QA_SOURCE_SHA256", "a" * 64)
    monkeypatch.setattr(environment_execution, "source_hash", lambda: "a" * 64)
    for flag in (*PAID_FLAGS, "ANVIL_IMPORT_GENERATION_ENABLED", "ANVIL_GENERATION_ENABLED"):
        monkeypatch.setenv(flag, "false")


def test_explicit_cloud_qa_does_not_open_legacy_or_model_dispatch(cloud):
    admission.enabled()
    with pytest.raises(HTTPException) as error:
        legacy_enabled()
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "flag", [*PAID_FLAGS, "ANVIL_IMPORT_GENERATION_ENABLED", "ANVIL_GENERATION_ENABLED"]
)
def test_every_paid_path_blocks_qa_admission(cloud, monkeypatch, flag):
    monkeypatch.setenv(flag, "true")
    with pytest.raises(HTTPException) as error:
        admission.enabled()
    assert error.value.status_code == 409


@pytest.mark.parametrize(
    "field,value",
    [
        ("ANVIL_ENVIRONMENT_QA_ENABLED", "false"),
        ("ANVIL_ENVIRONMENT_QA_SOURCE_SHA256", "b" * 64),
        ("ANVIL_ENV", "other"),
    ],
)
def test_missing_activation_wrong_source_and_unknown_mode_fail(cloud, monkeypatch, field, value):
    monkeypatch.setenv(field, value)
    with pytest.raises(HTTPException):
        admission.enabled()
