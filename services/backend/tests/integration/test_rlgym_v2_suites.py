# ruff: noqa: F811  (pytest fixtures shared from test_rlgym_v2 are parameters here)
"""RL Gym v2 work package 2.6: suite versions, bindings, data plan against the case catalog, more-data inbox item,
Trust & Safety generation and approval. Own disposable workspace (fixtures from test_rlgym_v2)."""

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row
from test_rlgym_v2 import PROJECT, STUDIO, activated, exported, person, post, ws  # noqa: F401

from anvil.config import setting
from anvil.rlgym import integrations


def _draft(client, base):
    suites = client.get(base + f"/projects/{PROJECT}/suites").json()["data"]["items"]
    default = next(s for s in suites if s["is_default"])
    return post(
        client, base + f"/suites/{default['suite_id']}/drafts", {"project_id": PROJECT}
    ).json()["data"]


def patch(client, path, body, expected=200):
    r = client.patch(path, json=body, headers={"Idempotency-Key": __import__("uuid").uuid4().hex})
    if expected:
        assert r.status_code == expected, r.text
    return r


def test_export_creates_the_default_suite_and_saved_versions_are_final(exported):
    assert exported["receipt"]["default_suite_version"] == "kyc-november-default-v1"
    admin = person("admin-1")
    suites = admin.get(exported["base"] + f"/projects/{PROJECT}/suites").json()["data"]["items"]
    default = suites[0]
    assert default["is_default"] and default["versions"][0]["state"] == "saved"
    sv = admin.get(exported["base"] + f"/suite-versions/{default['versions'][0]['id']}").json()[
        "data"
    ]
    assert sv["planned_on_env_version"] == "golden-kyc-openenv@v3" and sv["tasks"]["count"] == 40
    assert sv["checklist"]["can_run"] and all(
        b["rule_kind"] == "project_rule" for b in sv["bindings"]
    )
    with psycopg.connect(setting("DATABASE_URL")) as c:
        c.execute("SELECT set_config('rlgym.workspace', %s, true)", (exported["id"],))
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute(
                "UPDATE suites.data_plans SET sample_size=1 WHERE suite_version_id=%s", (sv["id"],)
            )
    unchanged = _draft(admin, exported["base"])
    r = post(admin, exported["base"] + f"/suite-versions/{unchanged['id']}/save", {}, expected=None)
    assert r.status_code == 409  # nothing changed
    assert admin.delete(exported["base"] + f"/suite-versions/{unchanged['id']}").status_code == 200


def test_short_data_plan_lower_and_more_data_item(exported):
    base, admin = exported["base"], person("admin-1")
    draft = _draft(admin, base)
    sv = patch(
        admin,
        base + f"/suite-versions/{draft['id']}",
        {
            "data_plan": {
                "sample_size": 400,
                "completeness_quotas": {"complete": 70, "incomplete": 30},
                "required_edges": {"minor_without_tin": 40},
            }
        },
    ).json()["data"]
    short = [i for i in sv["checklist"]["items"] if i.get("short")]
    assert short and not sv["checklist"]["can_run"]
    assert any("the plan asks for 40; the data has 33" in i["label"] for i in short)
    refused = post(admin, base + f"/suite-versions/{draft['id']}/save", {}, expected=None)
    assert refused.status_code == 422 and refused.json()["error"]["details"]["items"]
    first = short[0]["cell_key"]
    sv = patch(admin, base + f"/suite-versions/{draft['id']}", {"lower": first}).json()["data"]
    lowered = next(cl for cl in sv["cells"] if cl["cell_key"] == first)
    assert lowered["quota"] == lowered["available"] and lowered["original_quota"] > lowered["quota"]
    remaining = [i["cell_key"] for i in sv["checklist"]["items"] if i.get("short") and not i["ok"]]
    missing = post(
        admin,
        base + f"/suite-versions/{draft['id']}/more-data",
        {"descriptions": {}},
        expected=None,
    )
    assert missing.status_code == 422
    sent = post(
        admin,
        base + f"/suite-versions/{draft['id']}/more-data",
        {
            "descriptions": {
                k: f"More {k.replace('|', ' ')} applications (synthetic)" for k in remaining
            },
            "lineage": "same_seed_family",
            "needed_by": "2026-12-01",
            "why": "integration test",
        },
        201,
    ).json()["data"]
    item = sent["item"]
    assert item["kind"] == "more_data" and len(item["evidence"]["cells"]) == len(remaining)
    assert sent["suite"]["checklist"]["can_run"]
    saved = post(admin, base + f"/suite-versions/{draft['id']}/save", {}).json()["data"]
    assert saved["version"] == 2 and saved["label"] == "kyc-november-default-v2"
    integrations.dispatch_once()
    inbox = httpx.get(STUDIO + "/stub/state", timeout=10).json()["inbox"]
    assert any(i.get("rlgym_item_id") == item["id"] and i["kind"] == "more_data" for i in inbox)


def test_custom_bindings_need_a_reason_and_replan_on_the_bound_data(exported):
    base, admin = exported["base"], person("admin-1")
    draft = _draft(admin, base)
    no_reason = patch(
        admin,
        base + f"/suite-versions/{draft['id']}",
        {
            "bindings": [
                {
                    "alias": "kyc",
                    "rule_kind": "pinned",
                    "pinned_version_id": "golden-kyc-openenv@v2",
                }
            ]
        },
        expected=None,
    )
    assert no_reason.status_code == 422
    sv = patch(
        admin,
        base + f"/suite-versions/{draft['id']}",
        {
            "bindings": [
                {
                    "alias": "kyc",
                    "rule_kind": "pinned",
                    "pinned_version_id": "golden-kyc-openenv@v2",
                    "reason": "compare with V8 release data",
                }
            ]
        },
    ).json()["data"]
    assert (
        sv["planned_on_env_version"] == "golden-kyc-openenv@v2"
        and sv["bindings"][0]["source"] == "custom"
    )
    assert not sv["checklist"]["can_run"]  # the 40-case plan does not fit 20 cases
    sv = patch(admin, base + f"/suite-versions/{draft['id']}", {"lower_all": True}).json()["data"]
    assert sv["checklist"]["can_run"]
    criterion = patch(
        admin,
        base + f"/suite-versions/{draft['id']}",
        {
            "criterion_bindings": [
                {
                    "criterion_id": "screening",
                    "rule_kind": "pinned",
                    "pinned_version": 99,
                    "reason": "x",
                }
            ]
        },
        expected=None,
    )
    assert criterion.status_code == 409
    assert admin.delete(base + f"/suite-versions/{draft['id']}").status_code == 200


def test_trust_and_safety_generate_review_approve(exported):
    base, admin = exported["base"], person("admin-1")
    draft = _draft(admin, base)
    suggestion = post(admin, base + f"/suite-versions/{draft['id']}/suggestions/ts", {}).json()[
        "data"
    ]
    assert suggestion["source"] == "rule_based_no_model" and suggestion["categories"]
    cats = suggestion["categories"][:3]
    vague = {
        "key": "vague",
        "name": "Be careful",
        "category_group": "Custom",
        "source": "custom",
        "boundary_tested": "be careful with elderly people",
        "observable_check": "be nice",
    }
    bad = patch(
        admin,
        base + f"/suite-versions/{draft['id']}",
        {"ts_settings": {"enabled": True}, "ts_categories": [*cats, vague]},
        expected=None,
    )
    assert bad.status_code == 422
    sv = patch(
        admin,
        base + f"/suite-versions/{draft['id']}",
        {
            "ts_settings": {
                "enabled": True,
                "prompts_per_category": 2,
                "strategies": ["plain", "jailbreak"],
            },
            "ts_categories": cats,
        },
    ).json()["data"]
    assert sv["ts"]["state"] == "draft" and not sv["checklist"]["can_run"]
    sv = post(admin, base + f"/suite-versions/{draft['id']}/ts/generate", {}).json()["data"]
    assert (
        sv["ts"]["state"] == "generated"
        and len(sv["ts"]["prompts"]) == 6
        and "Promptfoo not installed" in sv["ts"]["generator"]
    )
    first = sv["ts"]["prompts"][0]["id"]
    post(admin, base + f"/suite-versions/{draft['id']}/ts/review", {"prompts": {first: False}})
    sv = post(admin, base + f"/suite-versions/{draft['id']}/ts/approve", {}).json()["data"]
    assert (
        sv["ts"]["state"] == "approved"
        and sv["ts"]["prompt_set_sha256"]
        and sv["checklist"]["can_run"]
    )
    saved = post(admin, base + f"/suite-versions/{draft['id']}/save", {}).json()["data"]
    # A change to the settings after approval needs regeneration and a new approval.
    nxt = _draft(admin, base)
    sv = patch(
        admin, base + f"/suite-versions/{nxt['id']}", {"ts_settings": {"prompts_per_category": 3}}
    ).json()["data"]
    assert (
        sv["ts"]["state"] == "draft"
        and sv["ts"]["prompts"] == []
        and not sv["checklist"]["can_run"]
    )
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        approved = c.execute(
            "SELECT count(*) n FROM suites.ts_prompts WHERE suite_version_id=%s AND approved",
            (saved["id"],),
        ).fetchone()["n"]
    assert approved == 5
    assert admin.delete(base + f"/suite-versions/{nxt['id']}").status_code == 200


def test_people_only_and_viewer_cannot_bypass_checks(exported):
    from test_rlgym_v2 import service

    forge = service("forge")
    r = post(
        forge,
        exported["base"] + f"/projects/{PROJECT}/suites",
        {"name": "from forge"},
        expected=None,
    )
    assert r.status_code in (401, 403)
