# ruff: noqa: F811  (pytest fixtures shared from the run tests are parameters here)
"""RL Gym v2 work package 2.8: the run report (five views, drill-downs), PDF export by headless Chromium, RL engineer
diagnoses with Studio inbox items, and packages. Own disposable workspace; controlled mock agents only."""

import hashlib
import json

import psycopg
import pytest
from psycopg.rows import dict_row
from test_rlgym_v2 import PROJECT, activated, exported, person, post, ws  # noqa: F401
from test_rlgym_v2_runs import body, finished, lineup, small_suite  # noqa: F401

from anvil.config import setting
from anvil.rlgym.runs import images

pytestmark = pytest.mark.skipif(not images.docker_status()[0], reason="Docker is required for runs")


def put(client, path, payload, expected=200):
    r = client.put(path, json=payload, headers={"Idempotency-Key": __import__("uuid").uuid4().hex})
    if expected:
        assert r.status_code == expected, r.text
    return r


def test_five_views_come_from_one_view_hash(finished):
    base, run_id, viewer = finished["base"], finished["run"]["id"], person("sales")
    hashes = set()
    views = {}
    for tab in ("overview", "tasks", "agent", "failures", "ts"):
        out = viewer.get(base + f"/runs/{run_id}/report?tab={tab}").json()["data"]
        assert out["ready"] and out["tab"] == tab
        hashes.add(out["view_sha256"])
        views[tab] = out["view"]
    assert len(hashes) == 1  # every view is a slice of the same report view
    header = out["header"]
    assert (
        header["manifest_sha256"] == finished["run"]["manifest_sha256"]
        and "Matched cohort: 8 cases" in header["cohort"]
    )
    cards = {c["name"]: c for c in views["overview"]["cards"]}
    assert cards["diligent"]["gate"] == "PASSED" and cards["diligent"]["mean"] == 100
    # A critical Trust & Safety incident fails the gate whatever the mean.
    assert (
        cards["skips-screening"]["gate"] == "FAILED"
        and "critical" in cards["skips-screening"]["gate_notes"][0]
    )
    assert len(views["tasks"]["criteria"]) == 20 and views["tasks"]["strata"]
    assert views["ts"]["enabled"] and len(views["ts"]["critical_incidents"]) == 1
    assert views["failures"]["episodes"] and all(
        e["failed_criteria"] or e["state"] != "scored" for e in views["failures"]["episodes"]
    )
    axes = {a["capability"] for a in views["overview"]["capability_profile"]}
    assert {"Screening", "Decision", "Identification"} <= axes
    bad = viewer.get(base + f"/runs/{run_id}/report?tab=nope")
    assert bad.status_code == 422


def test_drill_downs_and_audited_expected_answers(finished):
    base, run_id, admin = finished["base"], finished["run"]["id"], person("admin-1")
    failures = admin.get(base + f"/runs/{run_id}/report?tab=failures").json()["data"]["view"]
    failed = failures["episodes"][0]
    for kind, key in [
        ("capability", "Screening"),
        ("axes", ""),
        ("task", failed["task_id"]),
        ("case", failed["case_id"]),
        ("tscat", "aml_tipping_off"),
        ("policy", ""),
        ("risk", ""),
        ("review", failed["episode_id"]),
    ]:
        r = admin.get(base + f"/runs/{run_id}/report/drill?kind={kind}&key={key}")
        assert r.status_code == 200, (kind, r.text)
    case = admin.get(
        base + f"/runs/{run_id}/report/drill?kind=case&key={failed['case_id']}"
    ).json()["data"]["drill"]
    assert case["required"]["decision"] and case["per_model"][0]["episodes"][0]["workflow"]
    assert admin.get(base + f"/runs/{run_id}/report/drill?kind=bogus").status_code == 422
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        n = c.execute(
            "SELECT count(*) n FROM admin.audit_events WHERE workspace_id=%s AND action='report.expected_viewed'",
            (finished["id"],),
        ).fetchone()["n"]
    assert n >= 2


def test_pdf_is_rendered_once_per_view_and_downloads_intact(finished):
    base, run_id, admin = finished["base"], finished["run"]["id"], person("admin-1")
    first = post(admin, base + f"/runs/{run_id}/report/pdf", {}, 201).json()["data"]
    assert first["pages"] >= 8 and first["revision"] >= 1 and "Chromium" in first["renderer"]
    again = post(admin, base + f"/runs/{run_id}/report/pdf", {}, 201).json()["data"]
    assert again["revision"] == first["revision"] and again["pdf_sha256"] == first["pdf_sha256"]
    r = person("sales").get(base + f"/runs/{run_id}/report/pdf/{first['revision']}")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert (
        r.content.startswith(b"%PDF")
        and hashlib.sha256(r.content).hexdigest() == first["pdf_sha256"]
    )
    assert (
        "attachment" in r.headers["content-disposition"] and r.headers["x-frame-options"] == "DENY"
    )
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        view = c.execute(
            "SELECT view, view_sha256 FROM results.reports WHERE run_id=%s AND revision=%s",
            (run_id, first["revision"]),
        ).fetchone()
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute("UPDATE results.reports SET view='{}' WHERE run_id=%s", (run_id,))
    assert view["view"]["header"]["manifest_sha256"] == finished["run"]["manifest_sha256"]
    assert person("admin-1").get(base + f"/runs/{run_id}/report/pdf/999").status_code == 404


def test_diagnosis_never_changes_a_score_and_sends_only_criterion_defects(finished):
    base, run_id, admin = finished["base"], finished["run"]["id"], person("admin-1")
    failed = admin.get(base + f"/runs/{run_id}/report?tab=failures").json()["data"]["view"][
        "episodes"
    ]
    episode = next(e for e in failed if e["state"] == "scored")
    path = base + f"/episodes/{episode['episode_id']}/diagnosis"
    assert put(person("sales"), path, {}, expected=None).status_code == 403
    assert put(admin, path, {"attributed_to": "nobody"}, expected=None).status_code == 422
    assert (
        put(admin, path, {"attributed_to": "agent"}, expected=None).status_code == 422
    )  # needs a why
    saved = put(
        admin,
        path,
        {
            "task_finding": "task_correct",
            "attributed_to": "agent",
            "evaluator_finding": "grader_defect",
            "strength": "strong",
            "evidence_items": ["K1", "K3"],
            "why": "The agent skipped screening.check although the case has a possible match (integration test).",
        },
    ).json()["data"]
    assert saved["evaluator_finding"] == "grader_defect"
    send_path = base + f"/episodes/{episode['episode_id']}/inbox-items"
    grader = post(
        admin, send_path, {"kind": "evaluator_defect", "criterion_id": "screening"}, expected=None
    )
    assert (
        grader.status_code == 422
    )  # a grader defect is a new RL Gym configuration version, not a Studio item
    put(
        admin,
        path,
        {
            "task_finding": "task_correct",
            "attributed_to": "rubric",
            "evaluator_finding": "criterion_defect",
            "strength": "moderate",
            "evidence_items": ["K1"],
            "why": "The S7 screening criterion does not say what counts as a possible match (integration test).",
        },
    )
    item = post(
        admin, send_path, {"kind": "evaluator_defect", "criterion_id": "screening"}, 201
    ).json()["data"]
    assert (
        item["kind"] == "evaluator_defect"
        and item["evaluator_configuration"] == "golden-kyc:screening"
    )
    again = post(admin, send_path, {"kind": "new_case_kind"}, expected=None)
    assert again.status_code == 409
    after = admin.get(base + f"/runs/{run_id}/episodes?q={episode['episode_id']}").json()["data"][
        "items"
    ][0]
    assert float(after["score"]) == float(episode["score"])
    drill = admin.get(
        base + f"/runs/{run_id}/report/drill?kind=review&key={episode['episode_id']}"
    ).json()["data"]["drill"]
    assert drill["diagnosis"]["inbox_item_id"] == item["id"]


def test_packages_bundle_completed_runs_only(finished):
    base, run_id, admin = finished["base"], finished["run"]["id"], person("admin-1")
    refused = admin.get(base + "/runs?state=refused").json()["data"]["items"]
    if refused:
        bad = post(admin, base + "/packages", {"run_ids": [refused[0]["id"]]}, expected=None)
        assert bad.status_code in (409, 422)
    assert post(admin, base + "/packages", {"run_ids": []}, expected=None).status_code == 422
    assert (
        post(person("sales"), base + "/packages", {"run_ids": [run_id]}, expected=None).status_code
        == 403
    )
    pkg = post(admin, base + "/packages", {"run_ids": [run_id]}, 201).json()["data"]
    r = admin.get(base + f"/packages/{pkg['id']}/download")
    assert r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == pkg["package_sha256"]
    contents = json.loads(r.content)
    assert contents["runs"][0]["manifest_sha256"] == finished["run"]["manifest_sha256"]
    assert "not model performance" in contents["data_card"]["agents"]
    assert "reference" not in json.dumps(contents["runs"][0]["score_cards"])
    listed = admin.get(base + "/packages").json()["data"]["items"]
    assert listed[0]["id"] == pkg["id"]


def test_a_refused_run_has_no_report(small_suite):
    base, admin = small_suite["base"], person("admin-1")
    r = post(admin, base + "/runs", body(small_suite, name=""), expected=None)
    run_id = r.json()["error"]["details"]["run_id"]
    assert admin.get(base + f"/runs/{run_id}/report?tab=overview").status_code == 409


def test_gate_criteria_fail_a_model_whatever_its_mean(lineup):
    """Golden KYC V9 marks screening and the escalation decision as gates (owner decision RG-24): a model that skips
    screening fails its gate on the KYC December project even when its mean is above the pass mark."""
    import httpx
    from test_rlgym_v2 import FORGE, g, service

    from anvil.rlgym.runs import worker

    base, admin, studio = lineup["base"], person("admin-1"), service("studio")
    v9 = g.template(g.GATED_VERSION)
    assert {c["criterion_id"] for c in v9["criteria"] if c["is_gate"]} == {"screening", "decision"}
    act = post(studio, base + "/templates/activations", v9, 201).json()["data"]
    assert act["state"] == "active"
    with httpx.Client(timeout=60, trust_env=False) as client:
        export = client.post(
            FORGE + "/stub/projects/prj_d4e9b1a7/export", json={"send": False}
        ).json()["export"]
    post(
        service("forge"),
        base + "/projects/prj_d4e9b1a7/exports",
        export,
        201,
        key=export["export_sha256"],
    )
    suites = admin.get(base + "/projects/prj_d4e9b1a7/suites").json()["data"]["items"]
    sv = next(s for s in suites if s["is_default"])["versions"][0]["id"]
    run = post(
        admin,
        base + "/runs",
        {
            "name": "KYC December · gates",
            "project_id": "prj_d4e9b1a7",
            "suite_version_id": sv,
            "model_set": lineup["model_set"],
            "attempts": 1,
            "budget_usd": 5,
        },
        201,
    ).json()["data"]["run"]
    assert worker.drain(timeout=600)
    cards = {
        c["name"]: c
        for c in admin.get(base + f"/runs/{run['id']}/report?tab=overview").json()["data"]["view"][
            "cards"
        ]
    }
    skips = cards["skips-screening"]
    assert skips["gate"] == "FAILED" and any(
        "gate criteria failed" in n for n in skips["gate_notes"]
    )
    assert "screening" in skips["gate_notes"][0]
    assert cards["diligent"]["gate"] == "PASSED"
    eps = admin.get(base + f"/runs/{run['id']}/episodes?system=skips-screening&size=200").json()[
        "data"
    ]["items"]
    # Every episode of the profile fails screening, so no case passes even where its score is above 90.
    assert eps and not any(e["passed"] for e in eps if e["kind"] == "case")
