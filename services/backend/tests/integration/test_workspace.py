import hashlib

from test_api_security import USERS
from test_praxis_harbor import BASE, imported

from anvil import artifacts
from anvil.cli import OUTSIDER_PROJECT, PROJECT
from anvil.db import Jsonb, transaction, uid


def test_workspace_admin_reads_persisted_history_and_only_bound_internal_evidence(client_factory):
    _, _, _, source, package = imported(client_factory)
    hid = uid()
    output = b'{"decision":"actual retained test output"}'
    with transaction(PROJECT, USERS["researcher"]) as c:
        aid = artifacts.store(c, PROJECT, output, "internal")
        hidden = artifacts.store(c, PROJECT, b"PRIVATE-REFERENCE-MARKER", "hidden_reference")
        c.execute(
            """INSERT INTO anvil.harbor_checks(id,project_id,package_id,created_by,candidate,state,result)
                    VALUES(%s,%s,%s,%s,'reference','succeeded',%s)""",
            (
                hid,
                PROJECT,
                package["id"],
                USERS["researcher"],
                Jsonb(
                    {
                        "diagnostics": {"reward": 0, "hard_failures": ["budget"]},
                        "evidence": [
                            {
                                "artifact_id": str(aid),
                                "kind": "output.json",
                                "sha256": hashlib.sha256(output).hexdigest(),
                            }
                        ],
                    }
                ),
            ),
        )
    admin, _ = client_factory("admin-1")
    listing = admin.get(BASE + "/workspace/runs", params={"task_id": source["task_id"]})
    assert listing.status_code == 200, listing.text
    assert [r["id"] for r in listing.json()["data"]["items"]] == [hid]
    detail = admin.get(BASE + f"/workspace/runs/{hid}")
    assert detail.status_code == 200 and detail.json()["data"]["metrics"]["task_failed"] == 1
    assert "PRIVATE-NORTHSTAR" not in detail.text and "reference_output" not in detail.text
    bound = admin.get(BASE + f"/workspace/runs/{hid}/evidence/{aid}")
    assert bound.status_code == 200 and "actual retained test output" in bound.text
    assert admin.get(BASE + f"/workspace/runs/{hid}/evidence/{hidden}").status_code == 404
    outsider, _ = client_factory("outsider")
    assert outsider.get(BASE + f"/workspace/runs/{hid}").status_code == 404
    assert admin.get(f"/api/v1/projects/{OUTSIDER_PROJECT}/workspace/runs/{hid}").status_code == 404
    sales, _ = client_factory("sales")
    assert sales.get(BASE + "/workspace/tasks").status_code == 200


def test_multiple_model_profiles_are_admin_scoped_idempotent_and_not_live(client_factory):
    admin, _ = client_factory("admin-1")
    researcher, _ = client_factory("researcher")
    body = {
        "name": "Workspace test baseline",
        "provider": "openai",
        "model_id": "example-test-model",
    }
    assert researcher.post(BASE + "/workspace/models", json=body).status_code == 403
    key = uid()
    one = admin.post(BASE + "/workspace/models", json=body, headers={"Idempotency-Key": key})
    replay = admin.post(BASE + "/workspace/models", json=body, headers={"Idempotency-Key": key})
    assert one.status_code == 200, one.text
    assert one.json()["data"]["id"] == replay.json()["data"]["id"]
    two = admin.post(
        BASE + "/workspace/models",
        json={**body, "name": "Second baseline"},
        headers={"Idempotency-Key": uid()},
    )
    assert two.status_code == 200 and two.json()["data"]["id"] != one.json()["data"]["id"]
    assert not one.json()["data"]["launch_available"]
    assert "secret_reference" not in one.text and "api_key" not in one.text
    assert (
        admin.post(BASE + "/workspace/models", json={**body, "api_key": "do-not-save"}).status_code
        == 422
    )
    assert admin.get(BASE + "/workspace/models?limit=1").json()["data"]["next_cursor"]
    admin.headers.pop("X-CSRF-Token")
    assert admin.post(BASE + "/workspace/models", json=body).status_code == 403


def test_framework_profiles_are_persistent_metadata_not_executable_connections(client_factory):
    admin, _ = client_factory("admin-1")
    researcher, _ = client_factory("researcher")
    body = {"name": "Local reviewed worker", "framework": "harbor", "runtime_version": "0.25.0"}
    assert researcher.post(BASE + "/workspace/frameworks", json=body).status_code == 403
    saved = admin.post(
        BASE + "/workspace/frameworks", json=body, headers={"Idempotency-Key": uid()}
    )
    assert saved.status_code == 200, saved.text
    record = saved.json()["data"]
    assert record["config"]["dispatch_enabled"] is False
    assert record["config"]["trace_export_enabled"] is False
    listed = researcher.get(BASE + "/workspace/frameworks?limit=100")
    assert listed.status_code == 200
    page = listed.json()["data"]
    ids = {r["id"] for r in page["items"]}
    while page["next_cursor"] and record["id"] not in ids:
        page = researcher.get(
            BASE + "/workspace/frameworks?limit=100&after=" + page["next_cursor"]
        ).json()["data"]
        ids.update(r["id"] for r in page["items"])
    assert record["id"] in ids
    assert (
        admin.post(
            BASE + "/workspace/frameworks", json={**body, "runtime_version": "99.0"}
        ).status_code
        == 422
    )
    assert (
        admin.post(
            BASE + "/workspace/frameworks", json={**body, "endpoint": "https://evil.test"}
        ).status_code
        == 422
    )
    assert (
        admin.post(
            BASE + "/workspace/frameworks", json={**body, "trace_export_enabled": True}
        ).status_code
        == 422
    )
    outsider, _ = client_factory("outsider")
    assert outsider.get(BASE + "/workspace/frameworks").status_code == 404


def test_admin_run_records_software_authority_without_another_approval(client_factory):
    _, _, payload, source, package = imported(client_factory)
    admin, _ = client_factory("admin-1")
    assert admin.get(BASE + "/praxis-sources").status_code == 200
    assert admin.get(BASE + f"/harbor-packages/{package['id']}").status_code == 200
    replay = admin.post(
        BASE + "/praxis-sources", json={"payload": payload}, headers={"Idempotency-Key": uid()}
    )
    assert replay.status_code == 200 and replay.json()["data"]["id"] == source["id"]
    blocked = admin.post(
        BASE + f"/harbor-packages/{package['id']}/checks",
        json={"candidate": "reference"},
        headers={"Idempotency-Key": uid()},
    )
    assert blocked.status_code == 200, blocked.text
    check = blocked.json()["data"]
    cancelled = admin.post(
        BASE + f"/harbor-checks/{check['id']}/cancel", headers={"Idempotency-Key": uid()}
    )
    assert cancelled.status_code == 200
    # Admin can also record the same software scope explicitly; no paid authority follows.
    approval = admin.post(
        BASE + f"/harbor-packages/{package['id']}/approve",
        json={
            "package_sha256": package["package_sha256"],
            "rationale": "Must not auto-approve from engineering access",
            "scope": "synthetic_software_checks_only",
        },
    )
    assert approval.status_code == 200


def test_workspace_profile_never_silently_uses_the_legacy_provider_key(client_factory):
    _, _, _, _, package = imported(client_factory)
    admin, _ = client_factory("admin-1")
    created = admin.post(
        BASE + "/workspace/models",
        json={
            "name": "Test no legacy key substitution",
            "provider": "openai",
            "model_id": "test-model",
        },
        headers={"Idempotency-Key": uid()},
    )
    assert created.status_code == 200
    connection_id = created.json()["data"]["id"]
    legacy = admin.get(BASE + "/harbor-agent-connections")
    assert legacy.status_code == 200
    assert all(r["id"] != connection_id for r in legacy.json()["data"])
    blocked = admin.post(
        BASE + f"/harbor-packages/{package['id']}/agent-plans",
        json={
            "connection_id": connection_id,
            "agent": "anvil-structured-json-v1",
            "model": "test-model",
            "max_total_micro_usd": 1000,
            "trials": 1,
        },
        headers={"Idempotency-Key": uid()},
    )
    assert blocked.status_code == 409
    assert "never substituted" in blocked.text
