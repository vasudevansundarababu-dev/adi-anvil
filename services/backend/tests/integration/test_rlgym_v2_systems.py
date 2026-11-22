"""RL Gym v2 work package 2.5: keys, immutable model versions, probes, model sets. Own disposable workspace.
No provider is called: only the controlled mock answers; other providers record `live_disabled`."""

import json
import secrets
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row
from test_rlgym_v2 import USERS, person, post  # noqa: F401  (shared helpers)

from anvil.config import ROOT, setting


@pytest.fixture(scope="module")
def ws():
    slug = "it-sys-" + uuid.uuid4().hex[:6]
    wid = str(uuid.uuid4())
    with psycopg.connect(setting("MIGRATION_DATABASE_URL")) as c:
        c.execute(
            "INSERT INTO admin.workspaces(id,slug,name,tier) VALUES(%s,%s,%s,'dev')",
            (wid, slug, slug),
        )
        for name, profile in [("admin-1", "admin"), ("researcher", "rl_engineer")]:
            c.execute(
                "INSERT INTO admin.users(id,workspace_id,email,name,profile,status) VALUES(%s,%s,%s,%s,%s,'active')",
                (USERS[name], wid, f"{name}@anvil.invalid", name, profile),
            )
    return {"slug": slug, "id": wid, "base": f"/api/v1/workspaces/{slug}"}


def test_keys_are_admin_only_write_only_and_never_stored_in_clear(ws):
    secret = "sk-test-" + secrets.token_urlsafe(24)
    r = post(
        person("researcher"),
        ws["base"] + "/keys",
        {"provider": "anthropic", "name": "Workspace Anthropic", "secret": secret},
        expected=None,
    )
    assert r.status_code == 403
    admin = person("admin-1")
    key = post(
        admin,
        ws["base"] + "/keys",
        {"provider": "anthropic", "name": "Workspace Anthropic", "secret": secret},
    ).json()["data"]
    assert (
        key["last4"] == secret[-4:]
        and key["status"] == "untested"
        and "secret" not in json.dumps(key).lower().replace("secret_ref", "")
    )
    listed = admin.get(ws["base"] + "/keys").json()["data"]["items"]
    assert secret not in json.dumps(listed)
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        dump = json.dumps(
            c.execute(
                "SELECT * FROM systems.provider_keys WHERE workspace_id=%s", (ws["id"],)
            ).fetchall(),
            default=str,
        )
        dump += json.dumps(
            c.execute(
                "SELECT * FROM infra.idempotency_keys WHERE route LIKE %s", (f"{ws['slug']}:%",)
            ).fetchall(),
            default=str,
        )
        dump += json.dumps(
            c.execute(
                "SELECT * FROM admin.audit_events WHERE workspace_id=%s", (ws["id"],)
            ).fetchall(),
            default=str,
        )
    assert secret not in dump and secret[:-4] not in dump
    files = list((ROOT / ".local/workspace-secrets").iterdir())
    assert all(secret.encode() not in f.read_bytes() for f in files if f.is_file())
    tested = post(admin, ws["base"] + f"/keys/{key['id']}/test", {}).json()["data"]
    assert tested["status"] == "untested" and "not sent anywhere" in tested["status_note"]


def test_model_versions_are_immutable_and_live_providers_are_never_called(ws):
    admin = person("admin-1")
    missing = post(
        admin,
        ws["base"] + "/systems",
        {
            "kind": "frontier",
            "provider": "mistral",
            "model_id": "mistral-large",
            "limits": {"rpm": 60, "spend_per_episode_usd": 0.4},
        },
        expected=None,
    )
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "KEY_MISSING"
    body = {
        "kind": "frontier",
        "provider": "anthropic",
        "name": "Claude Opus 5.5",
        "model_id": "claude-opus-5-5",
        "params": {"temperature": 0, "max_output_tokens": 4096, "timeout_s": 120},
        "limits": {"rpm": 60, "spend_per_episode_usd": 0.4},
    }
    created = post(admin, ws["base"] + "/systems", body).json()["data"]
    system = created["system"]
    assert system["latest"]["version"] == 1 and created["probe"]["result"] == "live_disabled"
    assert system["status"] == "Live calls disabled"
    same = post(admin, ws["base"] + f"/systems/{system['system_id']}/versions", body).json()["data"]
    assert same["created"] is False and same["version"] == 1
    changed = post(
        admin,
        ws["base"] + f"/systems/{system['system_id']}/versions",
        {
            **body,
            "params": {**body["params"], "temperature": 0.2},
            "change_note": "temperature 0.2",
        },
    ).json()["data"]
    assert changed["created"] is True and changed["version"] == 2
    with psycopg.connect(setting("DATABASE_URL")) as c:
        c.execute("SELECT set_config('rlgym.workspace', %s, true)", (ws["id"],))
        with pytest.raises((psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)):
            c.execute(
                "UPDATE systems.system_versions SET model_id='other' WHERE workspace_id=%s",
                (ws["id"],),
            )
    bad = post(
        admin,
        ws["base"] + "/systems",
        {**body, "name": "bad", "limits": {"rpm": 0, "spend_per_episode_usd": 0.4}},
        expected=None,
    )
    assert bad.status_code == 422 and bad.json()["error"]["details"]["field"] == "rpm"
    fine_tuned = post(
        admin, ws["base"] + "/systems", {**body, "kind": "fine_tuned", "name": "ft"}, expected=None
    )
    assert fine_tuned.status_code == 422
    # Rotating the key changes no model version.
    key_id = system["key"]["id"]
    post(
        admin,
        ws["base"] + f"/keys/{key_id}/rotate",
        {"secret": "sk-rotated-" + secrets.token_urlsafe(16)},
    )
    after = admin.get(ws["base"] + f"/systems/{system['system_id']}").json()["data"]
    assert (
        after["latest"]["version"] == 2
        and after["key"]["rotated_at"] != system["key"]["rotated_at"]
    )
    used = post(admin, ws["base"] + f"/keys/{key_id}/revoke", {"reason": "it"}, expected=None)
    assert used.status_code == 422


def test_open_weight_needs_a_pinned_commit_and_hub_lookup_is_off(ws):
    admin = person("admin-1")
    post(
        admin,
        ws["base"] + "/keys",
        {
            "provider": "huggingface",
            "name": "Workspace HF token",
            "secret": "hf_" + secrets.token_urlsafe(20),
        },
    )
    body = {
        "kind": "open_weight",
        "name": "Qwen3.6-35B-A3B",
        "model_id": "Qwen/Qwen3.6-35B-A3B",
        "hf_revision": "main",
        "limits": {"rpm": 30, "spend_per_episode_usd": 0.2},
    }
    r = post(admin, ws["base"] + "/systems", body, expected=None)
    assert r.status_code == 422 and r.json()["error"]["details"]["field"] == "hf_revision"
    ok = post(admin, ws["base"] + "/systems", {**body, "hf_revision": "345d467b" * 5}).json()[
        "data"
    ]
    assert ok["system"]["latest"]["hf_revision"] == "345d467b" * 5
    lookup = admin.get(ws["base"] + "/hf/models/Qwen/Qwen3.6-35B-A3B/revisions/latest")
    assert lookup.status_code == 422


def test_controlled_mock_probe_and_model_sets(ws):
    admin = person("admin-1")
    post(admin, ws["base"] + "/keys", {"provider": "mock", "name": "Controlled mock"})
    systems = []
    for profile in ("mock/diligent-v1", "mock/skips-screening-v1"):
        out = post(
            admin,
            ws["base"] + "/systems",
            {
                "kind": "frontier",
                "provider": "mock",
                "model_id": profile,
                "name": profile,
                "limits": {"rpm": 600, "spend_per_episode_usd": 0.01},
            },
        ).json()["data"]
        assert (
            out["probe"]["result"] == "ok"
            and out["probe"]["mode"] == "controlled_mock"
            and out["system"]["status"] == "Ready"
        )
        systems.append(out["system"])
    members = [{"system_id": s["system_id"], "system_version": 1} for s in systems]
    first = post(
        admin, ws["base"] + "/model-sets", {"name": "IT line-up", "members": members}
    ).json()["data"]
    again = post(
        admin, ws["base"] + "/model-sets", {"name": "IT line-up", "members": members}
    ).json()["data"]
    assert first["version"] == 1 and again == {**first, "created": False}
    smaller = post(
        admin, ws["base"] + "/model-sets", {"name": "IT line-up", "members": members[:1]}
    ).json()["data"]
    assert smaller["version"] == 2
    post(admin, ws["base"] + f"/systems/{systems[1]['system_id']}/disable", {"reason": "it"})
    refused = post(
        admin, ws["base"] + "/model-sets", {"name": "IT line-up", "members": members}, expected=None
    )
    assert refused.status_code == 422
    sets = admin.get(ws["base"] + "/model-sets").json()["data"]["items"]
    assert sets[0]["version"] == 2 and [h["version"] for h in sets[0]["history"]] == [2, 1]
