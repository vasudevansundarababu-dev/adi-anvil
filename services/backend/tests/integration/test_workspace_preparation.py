import psycopg
import pytest
from test_api_security import USERS
from test_praxis_harbor import BASE, imported

from anvil import workspace_credentials, workspace_secrets
from anvil.cli import OUTSIDER_PROJECT, PROJECT
from anvil.db import transaction, uid


@pytest.mark.parametrize("runtime", ["anvil-structured-json-v1", "semantic_kernel"])
def test_exact_planning_bindings_readiness_and_zero_execution_effects(
    client_factory, tmp_path, monkeypatch, runtime
):
    monkeypatch.setattr(workspace_secrets, "ROOT", tmp_path)
    monkeypatch.setattr(workspace_secrets, "CLOUD", False)
    admin, _ = client_factory("admin-1")
    researcher, _, _, source, package = imported(client_factory)
    advisor, _ = client_factory("advisor")
    outsider, _ = client_factory("outsider")
    path = BASE + "/workspace"

    def post(endpoint, body, expected=200, client=admin, key=None):
        response = client.post(endpoint, json=body, headers={"Idempotency-Key": key or uid()})
        assert response.status_code == expected, response.text
        return response.json().get("data")

    frameworks = {
        kind: post(path + "/frameworks", {"name": "Test planning " + kind, "framework": kind})
        for kind in ("harbor", "semantic_kernel", "langsmith")
    }
    credential = post(
        path + "/credentials",
        {
            "name": "Test-only planning credential",
            "provider": "openai",
            "secret": "test-only-key-not-a-provider-" + uid(),
        },
    )
    models = [
        post(
            path + "/models",
            {
                "name": "Test planning " + str(i),
                "provider": provider,
                "model_id": "test-model-" + str(i),
                "max_output_tokens": 1024,
                **({"credential_id": credential["id"]} if i == 0 else {}),
            },
        )
        for i, provider in enumerate(("openai", "anthropic"))
    ]
    preset_body = {
        "name": "Test planning exact preset",
        "runner_profile_id": frameworks["harbor"]["id"],
        "candidate_runtime": runtime,
        "candidate_profile_id": frameworks["semantic_kernel"]["id"]
        if runtime == "semantic_kernel"
        else None,
        "tracing_profile_id": frameworks["langsmith"]["id"],
        "model_profile_ids": [m["id"] for m in models],
    }
    effect_tables = (
        "jobs",
        "harbor_agent_plans",
        "harbor_agent_calls",
        "evaluation_spend_windows",
        "budget_reservations",
        "provider_approvals",
        "harbor_approvals",
    )

    def counts():
        with transaction(PROJECT, USERS["admin-1"]) as c:
            return {
                table: c.execute(f"SELECT count(*) n FROM anvil.{table}").fetchone()["n"]
                for table in effect_tables
            }

    before = counts()
    key = uid()
    preset = post(path + "/presets", preset_body, key=key)
    assert post(path + "/presets", preset_body, key=key) == preset
    post(path + "/presets", preset_body, 403, client=researcher)
    post(
        path + "/presets", {**preset_body, "runner_profile_id": frameworks["langsmith"]["id"]}, 404
    )
    post(path + "/presets", {**preset_body, "model_profile_ids": [models[0]["id"]] * 2}, 422)
    foreign_runner = uid()
    with transaction(OUTSIDER_PROJECT, USERS["outsider"]) as c:
        c.execute(
            "INSERT INTO anvil.workspace_framework_profiles(id,project_id,name,framework,config,config_hash,created_by) VALUES(%s,%s,'Test-only foreign runner','harbor','{\"runtime_version\":\"0.25.0\"}'::jsonb,%s,%s)",
            (foreign_runner, OUTSIDER_PROJECT, "0" * 64, USERS["outsider"]),
        )
    post(path + "/presets", {**preset_body, "runner_profile_id": foreign_runner}, 404)
    body = {
        "preset_id": preset["id"],
        "package_id": package["id"],
        "model_profile_ids": [m["id"] for m in models],
        "max_output_tokens": 2048,
        "episode_timeout_seconds": 300,
    }
    key = uid()
    draft = post(path + "/preparations", body, client=researcher, key=key)
    assert post(path + "/preparations", body, client=researcher, key=key) == draft
    assert draft["snapshot"]["aggregate_cap_micro_usd"] is None
    assert draft["snapshot"]["package"]["package_sha256"] == package["package_sha256"]
    assert draft["snapshot"]["package"]["manifest"]["revision_id"] == source["revision_id"]
    assert (
        draft["snapshot"]["models"][0]["credential"]["version_id"]
        == credential["current_version_id"]
    )
    assert "files" not in draft["snapshot"]["package"]["manifest"] and "PRIVATE" not in str(draft)
    assert draft["readiness"]["reservation_micro_usd"] is None
    assert draft["readiness"]["conservative_cost_micro_usd"] is None
    assert not draft["launch_available"] and not draft["readiness"]["trace_export_enabled"]
    assert "aggregate_api_cap_missing" in draft["readiness"]["missing"]
    assert "selected_output_limit_exceeds_profile" in draft["readiness"]["models"][0]["missing"]
    if runtime == "semantic_kernel":
        assert "candidate_runtime_not_qualified" in draft["readiness"]["missing"]
    post(path + "/preparations", body, 403, client=advisor)
    assert outsider.get(path + "/preparations/" + draft["id"]).status_code == 404
    post(path + "/preparations", {**body, "package_id": uid()}, 404, client=researcher)
    post(path + "/preparations", {**body, "model_profile_ids": [uid()]}, 422, client=researcher)
    post(path + "/preparations", {**body, "aggregate_cap_micro_usd": 0}, 422, client=researcher)
    bounded = post(
        path + "/preparations",
        {**body, "aggregate_cap_micro_usd": 12345, "max_output_tokens": 1024},
        client=researcher,
    )
    assert bounded["snapshot"]["aggregate_cap_micro_usd"] == 12345
    assert all("aggregate_cap_micro_usd" not in m for m in bounded["snapshot"]["models"])
    # Readiness uses metadata only; raw key resolution is forbidden even after rotation.
    monkeypatch.setattr(
        workspace_credentials,
        "resolve",
        lambda *args: pytest.fail("Secret resolved during planning"),
    )
    post(
        path + f"/credentials/{credential['id']}/versions",
        {"secret": "test-only-rotated-key-" + uid()},
    )
    refreshed = researcher.get(path + "/preparations/" + draft["id"]).json()["data"]
    assert refreshed["snapshot"] == draft["snapshot"]
    assert refreshed["subject_hash"] == draft["subject_hash"]
    assert "bound_credential_rotated" in refreshed["readiness"]["models"][0]["missing"]
    post(path + f"/credentials/{credential['id']}/revoke", {})
    refreshed = researcher.get(path + "/preparations/" + draft["id"]).json()["data"]
    assert "credential_revoked_or_unavailable" in refreshed["readiness"]["models"][0]["missing"]
    # New database guard prevents destination drift, even if a caller preserves config_hash.
    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        with transaction(PROJECT, USERS["admin-1"]) as c:
            c.execute(
                "UPDATE anvil.connections SET destination='https://invalid.example.test' WHERE id=%s",
                (models[0]["id"],),
            )
    assert (
        researcher.get(path + "/preparations/" + draft["id"]).json()["data"]["snapshot"]
        == draft["snapshot"]
    )
    # Existing legacy route must continue to reject workspace profiles without any dispatch.
    post(
        BASE + f"/harbor-packages/{package['id']}/agent-plans",
        {
            "connection_id": models[0]["id"],
            "agent": "anvil-structured-json-v1",
            "model": models[0]["model_id"],
            "max_total_micro_usd": 12345,
            "trials": 1,
        },
        409,
        client=researcher,
    )
    assert counts() == before
    assert researcher.get(path + "/preparations?limit=1").json()["data"]["next_cursor"]
    assert admin.get(path + "/presets?limit=1").status_code == 200
    assert researcher.get(path + "/packages?task_id=" + source["task_id"]).json()["data"]["items"]
    assert researcher.post(path + f"/preparations/{draft['id']}/launch", json={}).status_code == 404
    researcher.headers.pop("X-CSRF-Token")
    post(path + "/preparations", body, 403, client=researcher)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with transaction(PROJECT, USERS["admin-1"]) as c:
            c.execute(
                "UPDATE anvil.workspace_run_preparations SET snapshot='{}'::jsonb WHERE id=%s",
                (draft["id"],),
            )
