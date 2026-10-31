from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from anvil import marketing_authority
from anvil import workspace_models as models
from anvil import workspace_preparation as planning


def price():
    return {
        "reference": "test-only-pricing-not-current-provider-rate",
        "source_url": "https://example.test/pricing",
        "input_micro_usd_per_million_tokens": 1234567,
        "output_micro_usd_per_million_tokens": 7654321,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"source_url": "http://example.test"},
        {"reference": "     "},
        {"source_url": "https://key:secret@example.test"},
        {"input_micro_usd_per_million_tokens": True},
        {"output_micro_usd_per_million_tokens": -1},
        {"expires_at": datetime(2030, 1, 1)},
    ],
)
def test_pricing_metadata_has_strict_rates_safe_reference_and_aware_expiry(changes):
    with pytest.raises(ValueError):
        models.Pricing(**{**price(), **changes})


def test_pricing_and_terms_are_not_legacy_spending_authority():
    body = models.ModelProfile(
        name="Test metadata",
        provider="openai",
        model_id="test-model",
        pricing=models.Pricing(**price()),
    )
    assert body.credential_id is None and body.processing_terms_reviewed is False
    with pytest.raises(ValueError):
        models.ModelProfile(
            name="Test metadata",
            provider="openai",
            model_id="test-model",
            processing_terms_reviewed=True,
        )
    config = {
        "workspace_profile_version": 1,
        "workspace_pricing": body.pricing.model_dump(mode="json"),
        "workspace_terms": {"reviewed": True},
    }
    assert not marketing_authority.config_valid({"config": config})
    assert models.pricing_state(config) == "current_metadata"
    config["workspace_pricing"]["expires_at"] = "2020-01-01T00:00:00+00:00"
    assert models.pricing_state(config) == "expired"
    assert models.pricing_state({}) == "missing"


def test_defense_in_depth_still_reports_endpoint_drift_without_rewriting_snapshot(monkeypatch):
    row = {
        "id": "model",
        "provider_key": "openai",
        "model_id": "test-model",
        "destination": "https://original.example.test",
        "status": "draft",
        "config_hash": "unchanged",
        "config": {
            "workspace_profile_version": 1,
            "profile_name": "Test model",
            "max_output_tokens": 2048,
        },
    }
    bound = planning.model_snapshot(row)
    snapshot = {
        "models": [bound],
        "max_output_tokens": 2048,
        "aggregate_cap_micro_usd": None,
        "preset": {
            "candidate_runtime": "anvil-structured-json-v1",
            "runner": None,
            "candidate": None,
            "tracing": None,
        },
        "package": {
            "manifest": {"binding": "structured-decision-v1", "harbor_version": "0.25.0"},
            "agent_admission_present": True,
        },
    }
    before = deepcopy(snapshot)
    row["destination"] = "https://changed.example.test"
    monkeypatch.setattr(planning, "one", lambda *args: row)
    monkeypatch.setattr(planning, "selection_issues", lambda *args: [])
    result = planning.readiness(None, snapshot)
    assert "model_configuration_changed" in result["models"][0]["missing"]
    assert not result["launch_available"] and snapshot == before
