# ruff: noqa: F811  (pytest fixtures shared from the run tests are parameters here)
"""RL Gym v2 work package 2.9: episode viewer, SME review batch to the ADI Forge stub, decisions back (all five kinds),
reviewed scores, Studio inbox items, the RL Gym's grader fix, corrected task re-export and the validation run.
Own disposable workspace; controlled mock agents only; SMEs act only through ADI Forge's key."""

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row
from test_rlgym_v2 import (  # noqa: F401
    FORGE,
    PROJECT,
    activated,
    exported,
    person,
    post,
    service,
    ws,
)
from test_rlgym_v2_runs import body, finished, lineup, small_suite  # noqa: F401

from anvil.config import setting
from anvil.rlgym import integrations
from anvil.rlgym.runs import images, worker

pytestmark = pytest.mark.skipif(not images.docker_status()[0], reason="Docker is required for runs")


def _wait_sent(client, base, run_id, batch_id, timeout=30):
    """The dev API's dispatcher may deliver the batch before this process does; wait until it is sent either way."""
    import time

    end = time.time() + timeout
    while time.time() < end:
        integrations.dispatch_once()
        for b in client.get(base + f"/runs/{run_id}/sme-review").json()["data"]["batches"]:
            if b["id"] == batch_id and b["state"] != "building":
                return b
        time.sleep(0.5)
    raise AssertionError(f"{batch_id} was not sent")


def put(client, path, payload, expected=200):
    r = client.put(path, json=payload, headers={"Idempotency-Key": __import__("uuid").uuid4().hex})
    if expected:
        assert r.status_code == expected, r.text
    return r


def _episodes(client, base, run_id, **q):
    params = "&".join(f"{k}={v}" for k, v in q.items())
    return client.get(base + f"/runs/{run_id}/episodes?size=200&{params}").json()["data"]["items"]


def test_episode_viewer_path_timeline_criteria_and_output(finished):
    base, run_id, viewer = finished["base"], finished["run"]["id"], person("sales")
    failed = _episodes(viewer, base, run_id, kind="case", verdict="failed")
    assert failed
    v = viewer.get(base + f"/episodes/{failed[0]['id']}").json()["data"]
    assert v["path"]["order"] and v["path"]["failed_node"] and "failed at" in v["path"]["summary"]
    assert (
        any(n["taken"] for n in v["path"]["nodes"])
        and v["timeline"][0]["tool"] == "application.read"
    )
    assert len(v["criteria"]) == 20 and all(c["evaluator"] for c in v["criteria"])
    screening = next(c for c in v["criteria"] if c["criterion_id"] == "screening")
    assert "screen" in screening["nodes"]
    assert v["output"]["expected"] and v["output"]["fields"] and v["sealed_sha256"]
    assert service("studio").get(base + f"/episodes/{failed[0]['id']}").status_code == 200
    assert person("outsider").get(base + f"/episodes/{failed[0]['id']}").status_code == 403
    assert (
        put(
            viewer,
            base + f"/episodes/{failed[0]['id']}/suspected-cause",
            {"cause": "agent_failure"},
            None,
        ).status_code
        == 403
    )
    admin = person("admin-1")
    out = put(
        admin, base + f"/episodes/{failed[0]['id']}/suspected-cause", {"cause": "agent_failure"}
    ).json()["data"]
    assert out["likely_cause_source"] == "rl_engineer"
    other = next(
        e
        for e in _episodes(admin, base, run_id, kind="case")
        if e["case_id"] == failed[0]["case_id"] and e["system_id"] != failed[0]["system_id"]
    )
    cmp = admin.get(base + f"/episodes/{failed[0]['id']}/compare?other={other['id']}").json()[
        "data"
    ]
    assert cmp["first_divergence"] is not None


def test_sme_loop_end_to_end(finished):
    base, run_id, admin, forge = (
        finished["base"],
        finished["run"]["id"],
        person("admin-1"),
        service("forge"),
    )
    skips = _episodes(admin, base, run_id, kind="case", system="skips-screening")
    chosen = [e["id"] for e in skips[:5]]
    assert len(chosen) == 5
    assert (
        post(
            person("sales"),
            base + f"/runs/{run_id}/sme-review-batches",
            {"episode_ids": chosen},
            expected=None,
        ).status_code
        == 403
    )
    batch = post(
        admin, base + f"/runs/{run_id}/sme-review-batches", {"episode_ids": chosen}, 201
    ).json()["data"]
    assert batch["state"] == "building" and len(batch["items"]) == 5 and batch["batch_sha256"]
    _wait_sent(admin, base, run_id, batch["id"])
    batch = admin.get(base + f"/sme-review-batches/{batch['id']}").json()["data"]
    assert batch["state"] == "sent" and batch["forge_batch_ref"]
    with httpx.Client(timeout=10, trust_env=False) as client:
        forge_state = client.get(FORGE + "/stub/state").json()
    assert any(r.get("batch_id") == batch["id"] for r in forge_state["run_reviews"])
    with psycopg.connect(setting("MIGRATION_DATABASE_URL")) as c:
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute(
                "INSERT INTO results.sme_review_items(id,batch_id,workspace_id,episode_id,task_id,task_revision) VALUES('x',%s,%s,%s,'t',1)",
                (batch["id"], finished["id"], chosen[0]),
            )
    items = batch["items"]
    kinds = [
        "agent_failure",
        "task_correction",
        "grader_wrong",
        "rubric_correction",
        "environment_wrong",
    ]
    decisions = [
        {
            "item_id": i["id"],
            "decision": k,
            "rationale": f"SME rationale for {k} (integration test)",
            "decided_by": "A. Menon (SME, ADI Forge)",
            **(
                {"criterion_id": "screening"}
                if k == "grader_wrong"
                else {"criterion_id": "decision"}
                if k == "rubric_correction"
                else {}
            ),
        }
        for i, k in zip(items, kinds, strict=True)
    ]
    body = {"schema": "rlgym.sme-decisions.v1", "batch_id": batch["id"], "decisions": decisions}
    # Only ADI Forge sends decisions: people (SMEs have no RL Gym account) are refused.
    assert post(
        admin, base + f"/sme-review-batches/{batch['id']}/decisions", body, expected=None
    ).status_code in (401, 403)
    decided = post(forge, base + f"/sme-review-batches/{batch['id']}/decisions", body, 200).json()[
        "data"
    ]
    assert decided["state"] == "decided" and decided["progress"]["all_decided"]
    by_kind = {i["decision"]: i for i in decided["items"]}
    assert not by_kind["agent_failure"]["excluded_from_reviewed"]
    assert all(by_kind[k]["excluded_from_reviewed"] for k in kinds[1:])
    assert (
        by_kind["rubric_correction"]["inbox_item"]["id"]
        and by_kind["environment_wrong"]["inbox_item"]["id"]
    )
    assert by_kind["grader_wrong"]["inbox_item_id"] is None  # fixed in the RL Gym, no Studio item
    reviewed = {r["system_id"]: r for r in decided["reviewed_scores"]}
    assert reviewed["skips-screening"]["excluded"] == 4 and reviewed["diligent"]["excluded"] == 0
    changed = {**decisions[0], "decision": "task_correction"}
    again = post(
        forge,
        base + f"/sme-review-batches/{batch['id']}/decisions",
        {**body, "decisions": [changed]},
        expected=None,
    )
    assert again.status_code == 409
    report = admin.get(base + f"/runs/{run_id}/report?tab=overview").json()["data"]
    assert report["header"]["reviewed"]
    card = next(c for c in report["view"]["cards"] if c["system_id"] == "skips-screening")
    assert card["reviewed"]["excluded"] == 4
    assert len(report["view"]["review_sample"]["items"]) == 5
    # Grader is wrong → the RL Gym's own fix version with the episode as a known case (no Studio item).
    fix = post(
        admin, base + f"/sme-review-items/{by_kind['grader_wrong']['id']}/grader-fix", {}, 201
    ).json()["data"]
    assert (
        fix["configuration"]["id"] == "golden-kyc:screening"
        and fix["configuration"]["version"] >= 2
    )
    assert any(ch["name"].startswith("sme_") for ch in fix["known_case_test"]["checks"])
    # Task needs correction → ADI Forge re-exports the corrected revision; then a validation run.
    task_item = by_kind["task_correction"]
    early = post(
        admin, base + f"/sme-review-items/{task_item['id']}/validation-run", {}, expected=None
    )
    assert early.status_code == 409
    with httpx.Client(timeout=60, trust_env=False) as client:
        corrected = client.post(
            FORGE + f"/stub/projects/{PROJECT}/export",
            json={
                "send": False,
                "export_id": "exp-sme-1",
                "reason": f"re-export after SME review {batch['id']}",
                "corrections": {
                    task_item["task_id"]: {
                        "revision": task_item["task_revision"] + 1,
                        "sme_batch_id": batch["id"],
                        "note": "Clarified (integration test).",
                    }
                },
            },
        ).json()["export"]
    post(forge, base + f"/projects/{PROJECT}/exports", corrected, 201)
    batch = admin.get(base + f"/sme-review-batches/{batch['id']}").json()["data"]
    assert batch["state"] == "corrections_imported"
    run = post(admin, base + f"/sme-review-items/{task_item['id']}/validation-run", {}, 201).json()[
        "data"
    ]
    assert worker.drain(timeout=600)
    batch = admin.get(base + f"/sme-review-batches/{batch['id']}").json()["data"]
    item = next(i for i in batch["items"] if i["id"] == task_item["id"])
    assert (
        item["validation"]["run_id"] == run["run_id"] and item["validation"]["state"] == "completed"
    )
    assert item["validation"]["result"] in ("fixed", "still_failing")
    assert batch["state"] == "validated"
    vrun = admin.get(base + f"/runs/{run['run_id']}").json()["data"]
    assert (
        vrun["purpose"] == "validation"
        and vrun["manifest"]["validation_of"]["batch_id"] == batch["id"]
    )
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        original = c.execute(
            "SELECT count(*) n FROM scoring.scoring_passes WHERE run_id=%s", (run_id,)
        ).fetchone()["n"]
    assert original >= 1  # the original run's passes are untouched by the SME loop


def test_qualified_grader_fix_starts_a_new_cohort(finished):
    """BUILD-LOCAL 'Done when': a grader fix becomes a new evaluator version and the next run is a new cohort."""
    base, run_id, admin, forge = (
        finished["base"],
        finished["run"]["id"],
        person("admin-1"),
        service("forge"),
    )
    episode = _episodes(admin, base, run_id, kind="case", system="diligent")[0]
    batch = post(
        admin, base + f"/runs/{run_id}/sme-review-batches", {"episode_ids": [episode["id"]]}, 201
    ).json()["data"]
    _wait_sent(admin, base, run_id, batch["id"])
    item = batch["items"][0]
    post(
        forge,
        base + f"/sme-review-batches/{batch['id']}/decisions",
        {
            "schema": "rlgym.sme-decisions.v1",
            "batch_id": batch["id"],
            "decisions": [
                {
                    "item_id": item["id"],
                    "decision": "grader_wrong",
                    "criterion_id": "decision",
                    "rationale": "grader note (it)",
                    "decided_by": "SME",
                }
            ],
        },
        200,
    )
    # The fix keeps the configuration and adds this episode as a known case with its current verdict: it qualifies.
    fix = post(
        admin,
        base + f"/sme-review-items/{item['id']}/grader-fix",
        {"expect": "pass", "reason": "known case added after SME review"},
        201,
    ).json()["data"]
    assert fix["configuration"]["state"] == "qualified" and fix["configuration"]["version"] >= 2
    todo = {
        i["kind"] for g in admin.get(base + "/todo").json()["data"]["groups"] for i in g["items"]
    }
    assert "rescore_ready" in todo  # re-score is offered, never automatic
    # The earlier corrected re-export changed the ready task set; the re-export already saved a current suite version.
    old = admin.get(base + f"/suite-versions/{finished['suite_version_id']}").json()["data"]
    suites = admin.get(base + f"/projects/{PROJECT}/suites").json()["data"]["items"]
    saved = next(
        v
        for v in next(x for x in suites if x["suite_id"] == old["suite_id"])["versions"]
        if v["state"] == "saved"
    )
    second = post(
        admin,
        base + "/runs",
        body(finished, name="after the grader fix", suite_version_id=saved["id"]),
        201,
    ).json()["data"]["run"]
    assert worker.drain(timeout=600)
    new = admin.get(base + f"/runs/{second['id']}").json()["data"]["manifest"]["evaluators"]
    assert (
        next(e for e in new if e["criterion_id"] == "decision")["version"]
        == fix["configuration"]["version"]
    )
    board = admin.get(base + f"/projects/{PROJECT}/leaderboard").json()["data"]
    assert board["run"]["id"] == second["id"] and len(board["cohorts"]) >= 2
