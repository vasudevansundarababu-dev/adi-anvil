# ruff: noqa: F811  (pytest fixtures shared from test_rlgym_v2 are parameters here)
"""RL Gym v2 work package 2.7: admission checklist, refused runs, frozen manifest, episodes run in a locally built
golden-kyc-openenv container (Docker, no network), sealed evidence, scoring passes, explicit re-score, cancel and
comparison. Own disposable workspace. Only controlled mock agents run; results are synthetic, not model performance."""

import hashlib
import json
import os
import stat

import psycopg
import pytest
from psycopg.rows import dict_row
from test_rlgym_v2 import PROJECT, activated, exported, person, post, service, ws  # noqa: F401

from anvil.config import setting
from anvil.rlgym.runs import images, worker
from anvil.rlgym.scoring import service as scoring

pytestmark = pytest.mark.skipif(not images.docker_status()[0], reason="Docker is required for runs")


def patch(client, path, body, expected=200):
    r = client.patch(path, json=body, headers={"Idempotency-Key": __import__("uuid").uuid4().hex})
    if expected:
        assert r.status_code == expected, r.text
    return r


@pytest.fixture(scope="module")
def lineup(exported):
    base, admin = exported["base"], person("admin-1")
    post(admin, base + "/keys", {"provider": "mock", "name": "Controlled mock"})
    members = []
    for profile in ("mock/diligent-v1", "mock/skips-screening-v1", "mock/erratic-v1"):
        out = post(
            admin,
            base + "/systems",
            {
                "kind": "frontier",
                "provider": "mock",
                "model_id": profile,
                "name": profile.split("/")[1].removesuffix("-v1"),
                "limits": {"rpm": 600, "spend_per_episode_usd": 0.01},
            },
        ).json()["data"]
        members.append({"system_id": out["system"]["system_id"], "system_version": 1})
    ms = post(admin, base + "/model-sets", {"name": "IT mock line-up", "members": members}).json()[
        "data"
    ]
    return {**exported, "model_set": {"id": ms["id"], "version": ms["version"]}, "members": members}


@pytest.fixture(scope="module")
def small_suite(lineup):
    """A saved suite version: 8 cases (2 per product, half complete), Trust & Safety with two categories, one prompt
    each, plain strategy."""
    base, admin = lineup["base"], person("admin-1")
    suites = admin.get(base + f"/projects/{PROJECT}/suites").json()["data"]["items"]
    default = next(s for s in suites if s["is_default"])
    draft = post(
        admin, base + f"/suites/{default['suite_id']}/drafts", {"project_id": PROJECT}
    ).json()["data"]
    path = base + f"/suite-versions/{draft['id']}"
    patch(
        admin,
        path,
        {
            "data_plan": {
                "sample_size": 8,
                "completeness_quotas": {"complete": 50, "incomplete": 50},
            }
        },
    )
    cats = post(admin, path + "/suggestions/ts", {}).json()["data"]["categories"]
    chosen = [c for c in cats if c["key"] in ("decision_authority", "aml_tipping_off")]
    assert len(chosen) == 2
    patch(
        admin,
        path,
        {
            "ts_settings": {"enabled": True, "prompts_per_category": 1, "strategies": ["plain"]},
            "ts_categories": chosen,
        },
    )
    post(admin, path + "/ts/generate", {})
    post(admin, path + "/ts/approve", {})
    saved = post(admin, path + "/save", {}).json()["data"]
    saved = admin.get(base + f"/suite-versions/{saved['id']}").json()["data"]
    assert saved["state"] == "saved" and saved["checklist"]["can_run"], saved["checklist"]
    return {**lineup, "suite_version_id": saved["id"], "suite_label": saved["label"]}


def body(ctx, **extra):
    return {
        "name": "KYC November · IT mock line-up",
        "project_id": PROJECT,
        "suite_version_id": ctx["suite_version_id"],
        "model_set": ctx["model_set"],
        "attempts": 1,
        "episode_timeout_min": 2,
        "infra_retries": 1,
        "budget_usd": 5,
        **extra,
    }


@pytest.fixture(scope="module")
def finished(small_suite):
    admin = person("admin-1")
    r = post(admin, small_suite["base"] + "/runs", body(small_suite), 201).json()["data"]
    assert not r["refused"] and r["run"]["state"] == "admitted"
    assert worker.drain(timeout=600)
    run = admin.get(small_suite["base"] + f"/runs/{r['run']['id']}").json()["data"]
    return {**small_suite, "run": run}


def test_admission_lists_every_failing_item_and_viewers_cannot_start(small_suite):
    base, admin = small_suite["base"], person("admin-1")
    suites = admin.get(base + f"/projects/{PROJECT}/suites").json()["data"]["items"]
    default = next(s for s in suites if s["is_default"])
    draft = post(
        admin, base + f"/suites/{default['suite_id']}/drafts", {"project_id": PROJECT}
    ).json()["data"]
    check = admin.post(
        base + "/runs/admission-check",
        json={"name": " ", "project_id": PROJECT, "suite_version_id": draft["id"], "budget_usd": 0},
    ).json()["data"]
    failing = {i["key"] for i in check["items"] if not i["ok"]}
    assert not check["passed"] and {"name", "suite", "models", "budget"} <= failing
    admin.delete(base + f"/suite-versions/{draft['id']}")
    good = admin.post(base + "/runs/admission-check", json=body(small_suite)).json()["data"]
    assert good["passed"], [i for i in good["items"] if not i["ok"]]
    # (8 cases + 2 safety prompts) × 3 models × 1 attempt
    assert good["episodes"] == 30 and good["per_model"][0]["formula"] == "(8 cases + 2 safety) × 1"
    assert good["projected_usd"] == pytest.approx(0.3)
    assert "not model performance" in good["note"]
    over = admin.post(
        base + "/runs/admission-check", json=body(small_suite, budget_usd=0.1)
    ).json()["data"]
    assert any(
        i["key"] == "budget" and not i["ok"] and "BUDGET_EXCEEDED" in i["detail"]
        for i in over["items"]
    )
    viewer = post(person("sales"), base + "/runs", body(small_suite), expected=None)
    assert viewer.status_code == 403


def test_refused_run_is_stored_with_every_reason(small_suite):
    base, admin = small_suite["base"], person("admin-1")
    r = post(admin, base + "/runs", body(small_suite, budget_usd=0.05, name=""), expected=None)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ADMISSION_REFUSED"
    run_id = r.json()["error"]["details"]["run_id"]
    run = admin.get(base + f"/runs/{run_id}").json()["data"]
    assert run["state"] == "refused" and run["manifest_sha256"] is None
    assert {x["key"] for x in run["refusal_reasons"]} >= {"name", "budget"}
    listed = admin.get(base + "/runs?state=refused").json()["data"]["items"]
    assert any(x["id"] == run_id and not x["report_available"] for x in listed)


def test_run_executes_in_the_container_seals_and_scores(finished):
    run, base = finished["run"], finished["base"]
    assert run["state"] == "completed" and run["counts"] == {"scored": 30}
    m = run["manifest"]
    assert m["execution_mode"] == "controlled_mock" and m["synthetic"] and run["manifest_sha256"]
    assert m["environment"]["version_id"] == "golden-kyc-openenv@v3"
    assert m["environment"]["local_image"]["id"].startswith("sha256:")
    assert len(m["data_plan"]["case_ids"]) == 8 and len(m["evaluators"]) == 20
    assert len(m["trust_and_safety"]["prompts"]) == 2 and len(m["tasks"]) == 40
    assert (
        run["instance"]["stopped_at"] is not None
    )  # the instance is stopped when the run finishes
    by = {s["name"]: s for s in run["statistics"]["systems"]}
    assert by["diligent"]["mean_score"] == 100 and by["diligent"]["pass_rate"] == 1
    assert by["skips-screening"]["criteria"]["screening"]["pass_rate"] == 0
    assert by["diligent"]["safety"] == {
        "attacks": 2,
        "acted_on": 0,
        "blocked": 0,
        "critical": 0,
        "unscored": 0,
    }
    # skips-screening acts on both attacks: application.write is blocked by the environment; tipping off is not.
    assert by["skips-screening"]["safety"]["acted_on"] == 2
    assert by["skips-screening"]["safety"]["blocked"] == 1
    assert (
        by["skips-screening"]["safety"]["critical"] == 1
        and by["skips-screening"]["gate"] == "FAILED"
    )
    assert by["diligent"]["gate"] == "PASSED"
    assert run["statistics"]["by_stratum"]
    eps = (
        person("sales")
        .get(base + f"/runs/{run['id']}/episodes?kind=safety&size=100")
        .json()["data"]
    )
    assert eps["total"] == 6 and all(e["safety_outcome"] for e in eps["items"])
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        receipts = c.execute(
            "SELECT count(*) n FROM scoring.criterion_receipts r JOIN runs.episodes e ON e.id=r.episode_id WHERE e.run_id=%s",
            (run["id"],),
        ).fetchone()["n"]
        assert (
            receipts == 24 * 20
        )  # case episodes × criteria; safety episodes are scored separately
        sealed = c.execute(
            "SELECT s.* FROM runs.sealed_evidence s JOIN runs.episodes e ON e.id=s.episode_id WHERE e.run_id=%s",
            (run["id"],),
        ).fetchall()
        refs = c.execute(
            "SELECT reference FROM scoring.case_references WHERE workspace_id=%s", (finished["id"],)
        ).fetchall()
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute("UPDATE runs.run_manifests SET manifest='{}' WHERE run_id=%s", (run["id"],))
    assert len(sealed) == 30
    for row in sealed:
        path = scoring.evidence_path(row["bundle_ref"])
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sealed_sha256"]
        assert not os.stat(path).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        bundle = json.loads(raw)
        assert bundle["synthetic"] and "reference" not in bundle
        # The reference decision/next action never appears in what the runner saw except as the agent's own output.
        assert "reference_answers" not in raw.decode()
    assert refs and all("decision" in r["reference"] for r in refs)


def test_rescore_is_explicit_and_refuses_tampered_evidence(finished):
    base, run_id, admin = finished["base"], finished["run"]["id"], person("admin-1")
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        row = c.execute(
            "SELECT s.* FROM runs.sealed_evidence s JOIN runs.episodes e ON e.id=s.episode_id WHERE e.run_id=%s AND e.kind='case' LIMIT 1",
            (run_id,),
        ).fetchone()
    path = scoring.evidence_path(row["bundle_ref"])
    original = path.read_bytes()
    os.chmod(path, 0o644)
    path.write_bytes(original.replace(b'"decision"', b'"decisioN"', 1))
    try:
        r = post(admin, base + f"/runs/{run_id}/rescore", {"reason": "tamper check"}, expected=None)
        assert r.status_code == 422 and r.json()["error"]["code"] == "HASH_MISMATCH"
    finally:
        path.write_bytes(original)
        os.chmod(path, 0o444)
    assert (
        post(person("sales"), base + f"/runs/{run_id}/rescore", {}, expected=None).status_code
        == 403
    )
    out = post(admin, base + f"/runs/{run_id}/rescore", {"reason": "explicit re-score"}).json()[
        "data"
    ]
    assert out["rescored"] and [p["reason"] for p in out["passes"]] == ["initial", "rescore"]
    assert out["latest_pass"] == 2
    before = {s["name"]: s["mean_score"] for s in finished["run"]["statistics"]["systems"]}
    assert {s["name"]: s["mean_score"] for s in out["statistics"]["systems"]} == before


def test_compare_same_suite_and_refuse_different(finished):
    base, admin = finished["base"], person("admin-1")
    second = post(admin, base + "/runs", body(finished, name="KYC November · repeat"), 201).json()[
        "data"
    ]
    assert worker.drain(timeout=600)
    cmp = admin.get(
        base + f"/comparisons?baseline={finished['run']['id']}&compared={second['run']['id']}"
    ).json()["data"]
    assert cmp["comparable"] and cmp["paired_episodes"] == 24
    assert cmp["delta"] == 0 and cmp["disagreements"] == []  # the controlled mock is deterministic
    saved = post(
        admin,
        base + "/comparisons",
        {"baseline": finished["run"]["id"], "compared": second["run"]["id"]},
        201,
    )
    assert saved.json()["data"]["id"].startswith("cmp-")
    refused = admin.get(base + "/runs?state=refused").json()["data"]["items"][0]["id"]
    bad = admin.get(
        base + f"/comparisons?baseline={finished['run']['id']}&compared={refused}"
    ).json()["data"]
    assert not bad["comparable"] and any(not c["ok"] for c in bad["checks"])


def test_cancel_stops_queuing(small_suite):
    base, admin = small_suite["base"], person("admin-1")
    r = post(admin, base + "/runs", body(small_suite, name="to cancel"), 201).json()["data"]
    cancelled = post(admin, base + f"/runs/{r['run']['id']}/cancel", {"reason": "it"}).json()[
        "data"
    ]
    assert cancelled["cancel_requested_at"]
    assert worker.drain(timeout=600)
    run = admin.get(base + f"/runs/{r['run']['id']}").json()["data"]
    assert run["state"] == "cancelled" and run["counts"].get("cancelled", 0) > 0
    assert run["instance"] is None or run["instance"]["stopped_at"] is not None
    again = post(admin, base + f"/runs/{r['run']['id']}/cancel", {}, expected=None)
    assert again.status_code == 409


def test_studio_reads_runs_but_cannot_change_them_and_other_workspaces_see_nothing(finished):
    base, run_id = finished["base"], finished["run"]["id"]
    studio = service("studio")
    assert studio.get(base + f"/runs/{run_id}").status_code == 200
    assert post(studio, base + f"/runs/{run_id}/cancel", {}, expected=None).status_code == 403
    assert post(studio, base + "/runs", body(finished), expected=None).status_code == 403
    outsider = person("outsider").get(base + f"/runs/{run_id}")
    assert outsider.status_code == 403
    with psycopg.connect(setting("DATABASE_URL"), row_factory=dict_row) as c:
        c.execute(
            "SELECT set_config('rlgym.workspace', %s, true)",
            ("00000000-0000-0000-0000-000000000000",),
        )
        assert (
            c.execute("SELECT count(*) n FROM runs.runs WHERE id=%s", (run_id,)).fetchone()["n"]
            == 0
        )
        assert c.execute("SELECT count(*) n FROM scoring.case_references").fetchone()["n"] == 0
