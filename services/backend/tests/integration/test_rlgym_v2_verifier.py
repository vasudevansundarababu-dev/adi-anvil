# ruff: noqa: F811  (pytest fixtures shared from test_rlgym_v2 are parameters here)
"""RL Gym v2 work package 2.11, verifier blocks, end to end on the stubs: golden-kyc-openenv v6 (declared collections,
snapshots), Golden KYC V10 (blocks on decision, screening and next_action), project KYC Verifier, three controlled
mock agents. A model that approves a sanctions near-match fails decision.status with STATE_MUTATION_ERROR. Own
disposable workspace; synthetic only, not model performance."""

import json
import sys

import httpx
import pytest
from test_rlgym_v2 import FORGE, person, post, service, ws  # noqa: F401

from anvil.config import ROOT
from anvil.rlgym.runs import images, worker

sys.path.insert(0, str(ROOT / "services/stubs"))
import golden_kyc as g  # noqa: E402

pytestmark = pytest.mark.skipif(not images.docker_status()[0], reason="Docker is required for runs")
PROJECT = "prj_b10c4e21"


@pytest.fixture(scope="module")
def v10(ws):
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
        tested = post(
            studio,
            ws["base"] + f"/evaluators/{binding['id']}/test",
            {
                "version": created["version"],
                "blocks": binding["blocks"],
                "expected_values_from": "case_reference",
            },
        ).json()["data"]
        assert tested["result"] == "qualified", tested
        disallowed = next(c for c in tested["checks"] if c["name"] == "disallowed")
        assert disallowed["verdict"] == "fail" and disallowed["block_lines"]
    template = g.template(g.BLOCKS_VERSION)
    act = post(studio, ws["base"] + "/templates/activations", template).json()["data"]
    assert act["state"] == "active", act
    with httpx.Client(timeout=60, trust_env=False) as client:
        body = client.post(FORGE + f"/stub/projects/{PROJECT}/export", json={"send": False}).json()[
            "export"
        ]
    receipt = post(service("forge"), ws["base"] + f"/projects/{PROJECT}/exports", body, 201).json()[
        "data"
    ]
    assert receipt["blocked"] == [], receipt
    return {**ws, "receipt": receipt}


def test_activation_refuses_an_undeclared_column(v10):
    template = json.loads(json.dumps(g.template(g.BLOCKS_VERSION)))
    decision = next(c for c in template["criteria"] if c["criterion_id"] == "decision")
    decision["verifier_blocks"][0]["column"] = "approved_by"
    out = post(service("studio"), v10["base"] + "/templates/validate", template).json()["data"]
    check = next(
        c
        for c in out["checks"]
        if c["check"] == "verifier_blocks_valid" and c["criterion"] == "decision"
    )
    assert not out["valid"] and not check["ok"]
    assert "recommendations.approved_by is not declared" in check["reason"]


def test_rubric_registry_is_listed_for_studio(v10):
    rubrics = service("studio").get(v10["base"] + "/catalog/rubrics").json()["data"]["rubrics"]
    assert {"customer_tone_polite", "reason_is_specific", "evidence_cited"} <= {
        r["rubric_id"] for r in rubrics
    }


@pytest.fixture(scope="module")
def run(v10):
    base, admin = v10["base"], person("admin-1")
    post(admin, base + "/keys", {"provider": "mock", "name": "Controlled mock"})
    members = []
    for profile in ("mock/diligent-v1", "mock/skips-screening-v1"):
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
    ms = post(admin, base + "/model-sets", {"name": "Verifier line-up", "members": members}).json()[
        "data"
    ]
    suites = admin.get(base + f"/projects/{PROJECT}/suites").json()["data"]["items"]
    default = next(s for s in suites if s["is_default"])
    suite_version_id = str(next(v["id"] for v in default["versions"] if v["state"] == "saved"))
    r = post(
        admin,
        base + "/runs",
        {
            "name": "KYC Verifier · blocks",
            "project_id": PROJECT,
            "suite_version_id": suite_version_id,
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
    return {**v10, "run_id": r["run"]["id"], "members": members}


def _lines(base, run_id, episode_id):
    view = person("admin-1").get(base + f"/episodes/{episode_id}").json()["data"]
    return {c["criterion_id"]: c for c in view["criteria"]}


def test_blocks_score_from_sealed_snapshots(run):
    base, admin = run["base"], person("admin-1")
    episodes = admin.get(base + f"/runs/{run['run_id']}/episodes?page_size=200").json()["data"][
        "items"
    ]
    assert episodes and all(e["state"] == "scored" for e in episodes if e["kind"] == "case"), [
        (e["id"], e["state"], e.get("last_error")) for e in episodes if e["state"] != "scored"
    ][:3]
    diligent = run["members"][0]["system_id"]
    clean = next(e for e in episodes if e["system_id"] == diligent and e["kind"] == "case")
    crit = _lines(base, run["run_id"], clean["id"])
    for name in ("decision", "screening", "next_action"):
        lines = crit[name]["block_lines"]
        assert lines and all(line["verdict"] == "pass" for line in lines), (name, lines)
    assert crit["decision"]["evaluator"].startswith("golden-kyc-blocks:decision")


def test_approving_a_sanctions_hit_fails_decision_status_with_state_mutation_error(run):
    base, admin = run["base"], person("admin-1")
    episodes = admin.get(base + f"/runs/{run['run_id']}/episodes?page_size=200").json()["data"][
        "items"
    ]
    skipper = run["members"][1]["system_id"]
    hits = {c["case_id"] for c in g.cases(100) if "screening_hit" in c["edge_cases"]}
    hit = next(
        e
        for e in episodes
        if e["system_id"] == skipper and e["case_id"] in hits and e["kind"] == "case"
    )
    crit = _lines(base, run["run_id"], hit["id"])
    status = next(
        line for line in crit["decision"]["block_lines"] if line["block_id"] == "decision.status"
    )
    assert status["verdict"] == "fail" and status["on_fail"] == "STATE_MUTATION_ERROR"
    assert status["expected"] == "escalate" and status["actual"] == "approve"
    assert crit["decision"]["verdict"] == "fail"
    specialty = next(
        line
        for line in crit["screening"]["block_lines"]
        if line["block_id"] == "screening.specialty"
    )
    assert specialty["verdict"] == "fail" and specialty["expected"] == "sanctions"
    report = admin.get(base + f"/runs/{run['run_id']}/report?tab=failures").json()["data"]
    failures = report["view"]
    codes = {r["code"] for r in failures["by_on_fail"]}
    assert "STATE_MUTATION_ERROR" in codes


def test_the_snapshot_is_never_an_agent_tool(run):
    base, admin = run["base"], person("admin-1")
    episodes = admin.get(base + f"/runs/{run['run_id']}/episodes?page_size=5").json()["data"][
        "items"
    ]
    view = admin.get(base + f"/episodes/{episodes[0]['id']}").json()["data"]
    tools = {t["tool"] for t in view["timeline"]}
    assert "snapshot" not in tools and "state" not in tools
