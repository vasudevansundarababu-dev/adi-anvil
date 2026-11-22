# ruff: noqa: F811  (pytest fixtures shared from test_rlgym_v2 are parameters here)
"""RL Gym v2 work package 2.12, edge cases and slice tags, on the stubs: Golden KYC V11 (S4 edge cases and S1 slice
lists) and project KYC Edge Cases. The data plan counts cases per edge-case tag at the template's minimum; a short tag
is asked for with its recipe and expected outcome; tasks carry complexity and archetype; reports slice by both; a new
case kind needs the four plain-English parts. Own disposable workspace; controlled mock only."""

import json
import sys
import uuid

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row
from test_rlgym_v2 import FORGE, person, post, service, ws  # noqa: F401

from anvil.config import ROOT, setting
from anvil.rlgym.runs import images, worker

sys.path.insert(0, str(ROOT / "services/stubs"))
import golden_kyc as g  # noqa: E402

pytestmark = pytest.mark.skipif(not images.docker_status()[0], reason="Docker is required for runs")
PROJECT = "prj_e11a5c07"


def put(client, path, body, expected=200):
    r = client.put(path, json=body, headers={"Idempotency-Key": uuid.uuid4().hex})
    if expected:
        assert r.status_code == expected, r.text
    return r


@pytest.fixture(scope="module")
def v11(ws):
    studio = service("studio")
    for binding in g.evaluator_bindings():
        created = post(studio, ws["base"] + "/evaluators", binding).json()["data"]
        post(
            studio,
            ws["base"] + f"/evaluators/{binding['id']}/test",
            {"version": created["version"]},
        )
    for binding in g.block_evaluator_bindings():
        created = post(studio, ws["base"] + "/evaluators", binding).json()["data"]
        post(
            studio,
            ws["base"] + f"/evaluators/{binding['id']}/test",
            {
                "version": created["version"],
                "blocks": binding["blocks"],
                "expected_values_from": "case_reference",
            },
        )
    act = post(studio, ws["base"] + "/templates/activations", g.template(g.EDGES_VERSION)).json()[
        "data"
    ]
    assert act["state"] == "active", act
    with httpx.Client(timeout=60, trust_env=False) as client:
        body = client.post(FORGE + f"/stub/projects/{PROJECT}/export", json={"send": False}).json()[
            "export"
        ]
    receipt = post(service("forge"), ws["base"] + f"/projects/{PROJECT}/exports", body, 201).json()[
        "data"
    ]
    assert receipt["blocked"] == [], receipt
    return ws


def test_activation_mirrors_edge_cases_and_validate_refuses_an_edge_case_without_a_recipe(v11):
    view = (
        person("admin-1")
        .get(v11["base"] + f"/templates/{g.TEMPLATE_ID}/versions/{g.EDGES_VERSION}")
        .json()["data"]
    )
    assert [e["tag"] for e in view["edge_cases"]] == [e["tag"] for e in g.S4_EDGE_CASES]
    assert view["slice_lists"] == g.SLICE_LISTS
    bad = json.loads(json.dumps(g.template(g.EDGES_VERSION)))
    bad["edge_cases"][0]["recipe"] = ""
    bad["edge_cases"][1]["archetype"] = "not_in_s1"
    out = post(service("studio"), v11["base"] + "/templates/validate", bad).json()["data"]
    check = next(c for c in out["checks"] if c["check"] == "edge_cases_valid")
    assert not out["valid"] and not check["ok"]
    assert "screening_hit: no generator recipe" in check["reason"]
    assert "archetype 'not_in_s1' is not in the template's S1 list" in check["reason"]


def test_tasks_carry_complexity_and_archetype(v11):
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        rows = c.execute(
            "SELECT complexity, archetype, count(*) n FROM projects.task_imports WHERE workspace_id=%s AND project_id=%s GROUP BY 1,2",
            (v11["id"], PROJECT),
        ).fetchall()
    tags = {(r["complexity"], r["archetype"]) for r in rows}
    assert ("single_step", "standard") in tags and ("judgement", "sanctions_near_match") in tags
    assert all(r["complexity"] in g.SLICE_LISTS["complexity"] for r in rows)
    # The actor part never carries them.
    actor = person("admin-1").get(v11["base"] + f"/projects/{PROJECT}/tasks").json()["data"]
    assert "archetype" not in json.dumps([t.get("actor") for t in actor.get("items", [])])


def test_data_plan_counts_edge_tags_and_asks_for_the_short_one_with_its_recipe(v11):
    base, admin = v11["base"], person("admin-1")
    suites = admin.get(base + f"/projects/{PROJECT}/suites").json()["data"]["items"]
    default = next(s for s in suites if s["is_default"])
    saved = next(v for v in default["versions"] if v["state"] == "saved")
    plan = admin.get(base + f"/suite-versions/{saved['id']}").json()["data"]
    cells = {c["cell_key"]: c for c in plan["cells"]}
    for e in g.S4_EDGE_CASES:
        assert cells[f"edge:{e['tag']}"]["quota"] == sum(e["minimum"].values())
    short = cells["edge:address_mismatch"]
    assert short["quota"] == 60 and short["available"] < 60
    draft = post(
        admin, base + f"/suites/{default['suite_id']}/drafts", {"project_id": PROJECT}
    ).json()["data"]
    item = post(admin, base + f"/suite-versions/{draft['id']}/more-data", {}, 201).json()["data"]
    evidence = item["item"]["evidence"]
    cell = next(c for c in evidence["cells"] if c["cell_key"] == "edge:address_mismatch")
    assert cell["edge_case"]["recipe"] == "address_on_document_matches is false for the case"
    assert cell["edge_case"]["expected_outcome"]["request_type"] == "proof_of_address"
    assert cell["edge_case"]["archetype"] == "address_mismatch"
    assert cell["request"] == 60 - cell["have"]


@pytest.fixture(scope="module")
def run(v11):
    base, admin = v11["base"], person("admin-1")
    post(admin, base + "/keys", {"provider": "mock", "name": "Controlled mock"})
    out = post(
        admin,
        base + "/systems",
        {
            "kind": "frontier",
            "provider": "mock",
            "model_id": "mock/skips-screening-v1",
            "name": "skips-screening",
            "limits": {"rpm": 600, "spend_per_episode_usd": 0.01},
        },
    ).json()["data"]
    ms = post(
        admin,
        base + "/model-sets",
        {
            "name": "Edge line-up",
            "members": [{"system_id": out["system"]["system_id"], "system_version": 1}],
        },
    ).json()["data"]
    suites = admin.get(base + f"/projects/{PROJECT}/suites").json()["data"]["items"]
    default = next(s for s in suites if s["is_default"])
    saved = next(v for v in default["versions"] if v["state"] == "saved")
    r = post(
        admin,
        base + "/runs",
        {
            "name": "KYC Edge Cases · slices",
            "project_id": PROJECT,
            "suite_version_id": str(saved["id"]),
            "model_set": {"id": ms["id"], "version": ms["version"]},
            "attempts": 1,
            "episode_timeout_min": 2,
            "infra_retries": 1,
            "budget_usd": 5,
        },
        201,
    ).json()["data"]
    assert not r["refused"], r
    assert worker.drain(timeout=900)
    return {**v11, "run_id": r["run"]["id"]}


def test_reports_slice_by_complexity_and_archetype(run):
    base, admin = run["base"], person("admin-1")
    tasks = admin.get(base + f"/runs/{run['run_id']}/report?tab=tasks").json()["data"]["view"]
    dims = {(s["dimension"], s["value"]) for s in tasks["slices"]}
    assert ("complexity", "single_step") in dims and ("archetype", "standard") in dims
    assert {d for d, _ in dims} == {"complexity", "archetype"}
    assert all(v in g.SLICE_LISTS[d] for d, v in dims)
    failures = admin.get(base + f"/runs/{run['run_id']}/report?tab=failures").json()["data"]["view"]
    # The skips-screening mock fails the screening gate, so every slice it ran shows failures.
    assert all(sum(v["failed"] for v in s["per_model"].values()) >= 1 for s in failures["slices"])
    assert any(e.get("archetype") for e in failures["episodes"])


def test_a_new_case_kind_needs_the_four_parts(run):
    base, admin = run["base"], person("admin-1")
    failed = admin.get(base + f"/runs/{run['run_id']}/report?tab=failures").json()["data"]["view"][
        "episodes"
    ]
    episode = next(e for e in failed if e["state"] == "scored")
    put(
        admin,
        base + f"/episodes/{episode['episode_id']}/diagnosis",
        {
            "task_finding": "task_defect",
            "attributed_to": "task",
            "evaluator_finding": "evaluator_correct",
            "strength": "moderate",
            "evidence_items": ["K1"],
            "why": "The case shows a situation no edge case covers (integration test).",
        },
    )
    send = base + f"/episodes/{episode['episode_id']}/inbox-items"
    refused = post(admin, send, {"kind": "new_case_kind"}, expected=None)
    assert refused.status_code == 422 and "four parts" in refused.text
    item = post(
        admin,
        send,
        {
            "kind": "new_case_kind",
            "edge_case": {
                "scenario_context": "A joint applicant is a trust, not a person.",
                "twist": "The trust deed names a beneficiary on the sanctions list.",
                "expected_outcome": "escalate",
                "rationale": "Beneficial owners are screened like parties.",
            },
        },
        201,
    ).json()["data"]
    edge = item["evidence"]["edge_case"]
    assert edge["twist"].startswith("The trust deed")
    # Slice tags default to the episode's task.
    assert edge["slice_tags"]["complexity"] == episode["complexity"]
    assert edge["slice_tags"]["archetype"] == episode["archetype"]
