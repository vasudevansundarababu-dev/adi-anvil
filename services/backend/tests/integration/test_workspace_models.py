from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from test_api_security import USERS
from test_praxis_harbor import BASE, imported

from anvil import workspace_secrets
from anvil.cli import PROJECT
from anvil.db import transaction, uid


def test_versioned_models_cas_disable_pricing_and_frozen_preparations(
    client_factory, tmp_path, monkeypatch
):
    monkeypatch.setattr(workspace_secrets, "ROOT", tmp_path)
    monkeypatch.setattr(workspace_secrets, "CLOUD", False)
    admin, _ = client_factory("admin-1")
    researcher, _, _, _, package = imported(client_factory)
    outsider, _ = client_factory("outsider")
    path = BASE + "/workspace"

    def post(endpoint, body, expected=200, version=None, key=None, client=admin):
        response = client.post(
            endpoint,
            json=body,
            headers={
                "Idempotency-Key": key or uid(),
                **({"If-Match": str(version)} if version is not None else {}),
            },
        )
        assert response.status_code == expected, response.text
        return response.json().get("data")

    legacy = post(
        BASE + "/providers/openai/config",
        {"model_id": "test-only-legacy-compatibility", "max_output_tokens": 2048},
    )
    credential = post(
        path + "/credentials",
        {
            "name": "Test-only model key",
            "provider": "openai",
            "secret": "test-only-not-provider-key-" + uid(),
        },
    )
    model_body = {
        "name": "Test-only versioned model",
        "provider": "openai",
        "model_id": "test-model-v1",
        "max_output_tokens": 2048,
        "credential_id": credential["id"],
        "credential_version_id": credential["current_version_id"],
    }
    initial = post(path + "/models", model_body)
    assert initial["version"] == 1 and initial["is_current"]
    assert initial["pricing"] is None and initial["pricing_state"] == "missing"
    runner = post(path + "/frameworks", {"name": "Test version runner", "framework": "harbor"})
    preset_body = {
        "name": "Test frozen model preset",
        "runner_profile_id": runner["id"],
        "candidate_runtime": "anvil-structured-json-v1",
        "model_profile_ids": [initial["id"]],
    }
    preset = post(path + "/presets", preset_body)
    draft_body = {
        "preset_id": preset["id"],
        "package_id": package["id"],
        "model_profile_ids": [initial["id"]],
        "max_output_tokens": 2048,
        "episode_timeout_seconds": 300,
    }
    draft = post(path + "/preparations", draft_body, client=researcher)
    rotated = post(
        path + f"/credentials/{credential['id']}/versions",
        {"secret": "test-only-rotated-model-key-" + uid()},
    )
    successor_body = {
        **model_body,
        "model_id": "test-model-v2",
        "pricing": {
            "reference": "test-only-not-real-provider-pricing",
            "source_url": "https://example.test/pricing",
            "input_micro_usd_per_million_tokens": 1234567,
            "output_micro_usd_per_million_tokens": 7654321,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        "processing_terms_reviewed": True,
        "processing_terms_reference": "Test-only terms metadata; no rights grant",
    }
    version_path = path + f"/models/{initial['id']}/versions"
    post(version_path, successor_body, 428)
    post(version_path, successor_body, 412, version=999)
    post(
        version_path, successor_body, 403, version=initial["profile_row_version"], client=researcher
    )
    post(version_path, successor_body, 409, version=initial["profile_row_version"])
    successor_body["credential_version_id"] = rotated["current_version_id"]
    post(
        version_path,
        {**successor_body, "provider": "gemini"},
        422,
        version=initial["profile_row_version"],
    )
    expired = {
        **successor_body,
        "pricing": {**successor_body["pricing"], "expires_at": "2020-01-01T00:00:00Z"},
    }
    post(version_path, expired, 422, version=initial["profile_row_version"])
    key = uid()
    updated = post(version_path, successor_body, version=initial["profile_row_version"], key=key)
    assert (
        post(version_path, successor_body, version=initial["profile_row_version"], key=key)
        == updated
    )
    assert updated["version"] == 2 and updated["profile_id"] == initial["profile_id"]
    assert updated["id"] != initial["id"] and updated["pricing_state"] == "current_metadata"
    assert not updated["launch_available"]
    listed_legacy = admin.get(BASE + "/providers").json()["data"]
    assert (
        next(item for item in listed_legacy if item["content"]["provider_key"] == "openai")["id"]
        == legacy["id"]
    )
    refused = researcher.post(
        BASE + f"/harbor-packages/{package['id']}/agent-plans",
        json={
            "connection_id": updated["id"],
            "agent": "anvil-structured-json-v1",
            "model": updated["model_id"],
            "max_total_micro_usd": 12345,
            "trials": 1,
        },
        headers={"Idempotency-Key": uid()},
    )
    assert refused.status_code == 409 and "workspace" in refused.text.lower()
    post(version_path, successor_body, 409, version=updated["profile_row_version"])
    old = admin.get(path + f"/models/{initial['id']}/configuration").json()["data"]
    assert (
        old["config_hash"] == initial["config_hash"]
        and old["model_id"] == "test-model-v1"
        and old["pricing"] is None
    )
    assert (
        old["credential_binding"]["version_id"] == credential["current_version_id"]
        and not old["is_current"]
    )
    read = researcher.get(path + f"/preparations/{draft['id']}").json()["data"]
    assert read["snapshot"] == draft["snapshot"] and read["subject_hash"] == draft["subject_hash"]
    assert "model_version_superseded" in read["readiness"]["models"][0]["missing"]
    post(path + "/preparations", draft_body, 409, client=researcher)
    history = admin.get(version_path + "?limit=1").json()["data"]
    assert history["items"][0]["version"] == 2 and history["next_cursor"] == 2
    assert admin.get(version_path + "?after=2").json()["data"]["items"][0]["version"] == 1
    assert admin.get(version_path + "?after=1").json()["data"]["next_cursor"] is None
    assert outsider.get(path + f"/models/{updated['id']}/configuration").status_code == 404
    assert researcher.get(version_path).status_code == 403
    disable = path + f"/models/{updated['id']}/disable"
    key = uid()
    disabled = post(disable, {}, version=updated["profile_row_version"], key=key)
    assert post(disable, {}, version=updated["profile_row_version"], key=key) == disabled
    assert disabled["status"] == "disabled"
    post(
        path + f"/models/{updated['id']}/versions",
        successor_body,
        409,
        version=disabled["profile_row_version"],
    )
    post(path + "/presets", {**preset_body, "model_profile_ids": [updated["id"]]}, 409)
    read = researcher.get(path + f"/preparations/{draft['id']}").json()["data"]
    assert "model_profile_disabled" in read["readiness"]["models"][0]["missing"]
    assert read["snapshot"] == draft["snapshot"]
    with transaction(PROJECT, USERS["admin-1"]) as c:
        raw = c.execute(
            "SELECT config FROM anvil.connections WHERE id=%s", (updated["id"],)
        ).fetchone()["config"]
        assert raw["workspace_terms"]["reviewed"] and not raw["processing_terms_reviewed"]
        assert raw["pricing_revision"] is None and raw["bound_micro_usd"] is None
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.provider_approvals WHERE connection_id IN (%s,%s)",
                (initial["id"], updated["id"]),
            ).fetchone()["n"]
            == 0
        )
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.workspace_model_versions WHERE profile_id=%s",
                (initial["profile_id"],),
            ).fetchone()["n"]
            == 2
        )
    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        with transaction(PROJECT, USERS["admin-1"]) as c:
            c.execute(
                "UPDATE anvil.connections SET model_id='changed' WHERE id=%s", (initial["id"],)
            )
    admin.headers.pop("X-CSRF-Token")
    post(disable, {}, 403, version=disabled["profile_row_version"])
