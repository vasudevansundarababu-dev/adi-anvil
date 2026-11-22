# ruff: noqa: F811  (pytest fixtures shared from test_rlgym_v2 are parameters here)
"""Verifier plug-ins end to end (D22, 2.14) with the real GoRules ZEN image: install and qualification by its known
cases, a plug-in that tries the network is blocked, validate refuses bad plug-in settings and a missing rules file,
and a Golden KYC V12 run on the stubs scores the ZEN block from sealed snapshots."""

import json
import subprocess
import sys

import httpx
import pytest
from test_rlgym_v2 import FORGE, person, post, service, ws  # noqa: F401

from anvil.config import ROOT
from anvil.rlgym.plugins import runner
from anvil.rlgym.runs import images, worker

sys.path.insert(0, str(ROOT / "services/stubs"))
import golden_kyc as g  # noqa: E402

MANIFEST_FILE = ROOT / ".local/plugins/gorules-zen-1.0.0.json"
pytestmark = pytest.mark.skipif(
    not images.docker_status()[0] or not MANIFEST_FILE.exists(),
    reason="Docker and a built ZEN image (python3 scripts/local.py plugin-build gorules-zen) are required",
)
PROJECT = "prj_c12e7f30"


@pytest.fixture(scope="module")
def zen(ws):
    manifest = json.loads(MANIFEST_FILE.read_text())
    out = post(
        person("admin-1"), ws["base"] + "/evaluators/plugins", {"manifest": manifest}
    ).json()["data"]
    assert out["state"] == "qualified", out
    listed = service("studio").get(ws["base"] + "/evaluators/plugins").json()["data"]["items"]
    assert any(
        p["id"] == "gorules-zen" and p["settings_schema"]["required"] == ["mode", "rules", "inputs"]
        for p in listed
    )
    return {**ws, "manifest": manifest}


def test_only_an_admin_installs_and_a_changed_manifest_is_a_new_version(zen):
    m = zen["manifest"]
    assert (
        post(
            person("researcher"),
            zen["base"] + "/evaluators/plugins",
            {"manifest": m},
            expected=None,
        ).status_code
        == 403
    )
    changed = {**m, "name": "Something else"}
    assert (
        post(
            person("admin-1"),
            zen["base"] + "/evaluators/plugins",
            {"manifest": changed},
            expected=None,
        ).status_code
        == 409
    )


def test_the_plugin_sandbox_has_no_network(zen):
    args = runner.docker_args(
        {
            **zen["manifest"],
            "entrypoint": [
                "python",
                "-c",
                "import urllib.request as u; u.urlopen('http://1.1.1.1', timeout=3)",
            ],
        }
    )
    p = subprocess.run(["docker", *args], input=b"{}", capture_output=True, timeout=60, check=False)
    assert p.returncode != 0 and b"Network is unreachable" in p.stderr


@pytest.fixture(scope="module")
def v12(zen):
    studio = service("studio")
    for binding in g.evaluator_bindings():
        created = post(studio, zen["base"] + "/evaluators", binding).json()["data"]
        post(
            studio,
            zen["base"] + f"/evaluators/{binding['id']}/test",
            {"version": created["version"]},
        )
    for binding in g.block_evaluator_bindings():
        created = post(studio, zen["base"] + "/evaluators", binding).json()["data"]
        post(
            studio,
            zen["base"] + f"/evaluators/{binding['id']}/test",
            {
                "version": created["version"],
                "blocks": binding["blocks"],
                "expected_values_from": "case_reference",
            },
        )
    act = post(studio, zen["base"] + "/templates/activations", g.template(g.ZEN_VERSION)).json()[
        "data"
    ]
    assert act["state"] == "active", act
    with httpx.Client(timeout=60, trust_env=False) as client:
        body = client.post(FORGE + f"/stub/projects/{PROJECT}/export", json={"send": False}).json()[
            "export"
        ]
    receipt = post(
        service("forge"), zen["base"] + f"/projects/{PROJECT}/exports", body, 201
    ).json()["data"]
    assert receipt["blocked"] == []
    return zen


def test_validate_refuses_bad_plugin_settings_and_a_missing_rules_file(v12):
    doc = json.loads(json.dumps(g.template(g.ZEN_VERSION)))
    decision = next(c for c in doc["criteria"] if c["criterion_id"] == "decision")
    decision["verifier_blocks"][-1]["settings"]["mode"] = "guess"
    doc["verifier_files"] = {}
    out = post(service("studio"), v12["base"] + "/templates/validate", doc).json()["data"]
    check = next(
        c
        for c in out["checks"]
        if c["check"] == "verifier_blocks_valid" and c["criterion"] == "decision"
    )
    assert not check["ok"]
    assert (
        "settings.mode: must be one of" in check["reason"]
        and "is not in the release's verifier_files" in check["reason"]
    )
    tampered = json.loads(json.dumps(g.template(g.ZEN_VERSION)))
    tampered["verifier_files"][g.ZEN_RULES_SHA256]["nodes"][1]["name"] = "edited"
    out = post(service("studio"), v12["base"] + "/templates/validate", tampered).json()["data"]
    assert not next(c for c in out["checks"] if c["check"] == "verifier_files_valid")["ok"]


def test_a_v12_run_scores_the_zen_block_from_sealed_snapshots(v12):
    base, admin = v12["base"], person("admin-1")
    post(admin, base + "/keys", {"provider": "mock", "name": "Controlled mock"})
    members = []
    for profile in ("mock/diligent-v1", "mock/erratic-v1"):
        out = post(
            admin,
            base + "/systems",
            {
                "kind": "frontier",
                "provider": "mock",
                "model_id": profile,
                "name": profile.split("/")[1],
                "limits": {"rpm": 600, "spend_per_episode_usd": 0.01},
            },
        ).json()["data"]
        members.append({"system_id": out["system"]["system_id"], "system_version": 1})
    ms = post(admin, base + "/model-sets", {"name": "ZEN line-up", "members": members}).json()[
        "data"
    ]
    suites = admin.get(base + f"/projects/{PROJECT}/suites").json()["data"]["items"]
    saved = next(
        v for v in next(s for s in suites if s["is_default"])["versions"] if v["state"] == "saved"
    )
    check = admin.post(
        base + "/runs/admission-check",
        json={
            "name": "ZEN",
            "project_id": PROJECT,
            "suite_version_id": str(saved["id"]),
            "model_set": {"id": ms["id"], "version": ms["version"]},
            "attempts": 1,
            "episode_timeout_min": 2,
            "infra_retries": 1,
            "budget_usd": 5,
        },
    ).json()["data"]
    plugins_item = next(i for i in check["items"] if i["key"] == "plugins")
    assert plugins_item["ok"] and "gorules-zen 1.0.0" in plugins_item["detail"]
    r = post(
        admin,
        base + "/runs",
        {
            "name": "ZEN",
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
    run_id = r["run"]["id"]
    assert worker.drain(timeout=900)
    run = admin.get(base + f"/runs/{run_id}").json()["data"]
    assert run["manifest"]["plugins"]["decision.minor_tin"]["plugin_id"] == "gorules-zen"
    episodes = admin.get(base + f"/runs/{run_id}/episodes?page_size=200").json()["data"]["items"]
    minors = {c["case_id"] for c in g.cases(100) if "minor_without_tin" in c["edge_cases"]}
    seen = []
    for e in [e for e in episodes if e["kind"] == "case"]:
        view = admin.get(base + f"/episodes/{e['id']}").json()["data"]
        decision = next(c for c in view["criteria"] if c["criterion_id"] == "decision")
        line = next(x for x in decision["block_lines"] if x["block_id"] == "decision.minor_tin")
        assert line["kind"] == "plugin" and line["verdict"] in ("pass", "fail"), line
        seen.append((e["system_id"], e["case_id"], line["verdict"]))
    diligent = members[0]["system_id"]
    assert seen and all(
        v == "pass" for s, c, v in seen if s == diligent
    )  # it escalates minors without a TIN
    del minors
