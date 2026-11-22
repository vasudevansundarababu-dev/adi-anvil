"""RL Gym v2 integration: API + PostgreSQL (RLS, triggers, checks) + the running local Studio/ADI Forge stubs.

Each test module run creates its own disposable workspace (it-<hex>) so the KYC November demo data in
adi-labs-research is never changed irreversibly. Requires `pnpm dev` (API, stubs) and `pnpm rlgym:demo` state for
the registry mirror. Synthetic data only; no model is called.
"""

import json
import os
import secrets
import sys
import time
import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from anvil.api import app
from anvil.auth import hashed
from anvil.config import ROOT, setting
from anvil.db import transaction
from anvil.rlgym import integrations
from anvil.rlgym.common import sign

sys.path.insert(0, str(ROOT / "services/stubs"))
import golden_kyc as g  # noqa: E402

USERS = json.loads((ROOT / ".local/demo-identities.json").read_text())
STUDIO = "http://127.0.0.1:8211"
FORGE = "http://127.0.0.1:8212"
PROJECT = g.FORGE_PROJECT_ID


@pytest.fixture(scope="module")
def ws():
    slug = "it-" + uuid.uuid4().hex[:8]
    wid = str(uuid.uuid4())
    with psycopg.connect(setting("MIGRATION_DATABASE_URL")) as c:
        c.execute(
            "INSERT INTO admin.workspaces(id,slug,name,tier) VALUES(%s,%s,%s,'dev')",
            (wid, slug, f"Integration {slug}"),
        )
        for name, profile, approver in [
            ("researcher", "rl_engineer", False),
            ("admin-1", "admin", True),
            ("admin-2", "admin", True),
            ("sales", "viewer", False),
        ]:
            c.execute(
                "INSERT INTO admin.users(id,workspace_id,email,name,profile,binding_approver,status) VALUES(%s,%s,%s,%s,%s,%s,'active')",
                (USERS[name], wid, f"{name}@anvil.invalid", name, profile, approver),
            )
    # Stubs must be up; the registry mirror must hold golden-kyc-openenv v2 and v3 (pnpm rlgym:demo).
    with httpx.Client(timeout=240, trust_env=False) as client:
        assert client.post(STUDIO + "/stub/bootstrap").status_code == 200
    return {"slug": slug, "id": wid, "base": f"/api/v1/workspaces/{slug}"}


def person(name):
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    with transaction() as c:
        c.execute(
            "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
            (hashed(token), USERS[name], hashed(csrf)),
        )
    client = TestClient(app)
    client.cookies.set("anvil_session", token)
    client.headers.update({"Origin": setting("WEB_ORIGIN"), "X-CSRF-Token": csrf})
    return client


def service(name):
    key = {"studio": "RLGYM_STUDIO_CLIENT_KEY", "forge": "RLGYM_FORGE_CLIENT_KEY"}[name]
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {os.environ[key]}"})
    return client


def post(client, path, body, expected=(200, 201), key=None):
    r = client.post(path, json=body, headers={"Idempotency-Key": key or str(uuid.uuid4())})
    if expected:
        assert r.status_code in (expected if isinstance(expected, tuple) else (expected,)), r.text
    return r


@pytest.fixture(scope="module")
def activated(ws):
    studio = service("studio")
    for binding in g.evaluator_bindings():
        created = post(studio, ws["base"] + "/evaluators", binding).json()["data"]
        again = post(studio, ws["base"] + "/evaluators", binding).json()["data"]
        assert (
            again["version"] == created["version"]
        )  # the same S7 binding twice is the same version
        tested = post(
            studio,
            ws["base"] + f"/evaluators/{binding['id']}/test",
            {"version": created["version"]},
        ).json()["data"]
        assert tested["result"] == "qualified", tested
    template = g.template()
    act = post(studio, ws["base"] + "/templates/activations", template).json()["data"]
    assert act["state"] == "active", act
    return ws


@pytest.fixture(scope="module")
def exported(activated):
    ws = activated
    with httpx.Client(timeout=60, trust_env=False) as client:
        body = client.post(FORGE + f"/stub/projects/{PROJECT}/export", json={"send": False}).json()[
            "export"
        ]
    r = post(
        service("forge"),
        ws["base"] + f"/projects/{PROJECT}/exports",
        body,
        201,
        key=body["export_sha256"],
    )
    receipt = r.json()["data"]
    assert (receipt["new"], receipt["superseding"], receipt["unchanged"], receipt["blocked"]) == (
        40,
        0,
        0,
        [],
    )
    return {**ws, "export": body, "receipt": receipt}


def test_export_is_idempotent_hash_checked_and_corrections_supersede(exported):
    ws, body = exported, exported["export"]
    forge = service("forge")
    replay = post(
        forge, ws["base"] + f"/projects/{PROJECT}/exports", body, key=body["export_sha256"]
    ).json()["data"]
    assert replay["receipt_sha256"] == exported["receipt"]["receipt_sha256"]
    again = post(forge, ws["base"] + f"/projects/{PROJECT}/exports", body).json()[
        "data"
    ]  # new key, same body
    assert again["replayed"] is True and again["new"] == 40
    tampered = {**body, "export_sha256": "0" * 64}
    r = post(forge, ws["base"] + f"/projects/{PROJECT}/exports", tampered, expected=None)
    assert r.status_code == 422 and r.json()["error"]["code"] == "HASH_MISMATCH"
    clash = {**body, "reason": "changed reason, same export id"}
    clash["export_sha256"] = g.sha({k: v for k, v in clash.items() if k != "export_sha256"})
    r = post(forge, ws["base"] + f"/projects/{PROJECT}/exports", clash, expected=None)
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    # Re-export after SME review: task-kyc-0013 r2 supersedes r1; the other 39 are unchanged.
    with httpx.Client(timeout=60, trust_env=False) as client:
        corrected = client.post(
            FORGE + f"/stub/projects/{PROJECT}/export",
            json={
                "send": False,
                "export_id": "exp-0002",
                "reason": "re-export after SME review smr-0007",
                "corrections": {
                    "task-kyc-0013": {
                        "revision": 2,
                        "sme_batch_id": "smr-0007",
                        "note": "Two expiry dates; use the later.",
                    }
                },
            },
        ).json()["export"]
    receipt = post(forge, ws["base"] + f"/projects/{PROJECT}/exports", corrected, 201).json()[
        "data"
    ]
    assert (receipt["new"], receipt["superseding"], receipt["unchanged"]) == (0, 1, 39)
    rows = (
        person("researcher")
        .get(ws["base"] + f"/projects/{PROJECT}/tasks?q=task-kyc-0013")
        .json()["data"]["items"]
    )
    assert [(t["revision"], t["state"]) for t in rows] == [(2, "ready"), (1, "superseded")]
    assert rows[0]["corrects_revision"] == 1 and rows[0]["sme_batch_id"] == "smr-0007"


def test_people_cannot_push_exports_and_services_stay_on_their_routes(exported):
    ws = exported
    r = post(
        person("admin-1"),
        ws["base"] + f"/projects/{PROJECT}/exports",
        exported["export"],
        expected=None,
    )
    assert r.status_code == 401  # export is a service route (adi-forge) only
    r = post(service("forge"), ws["base"] + "/evaluators", g.evaluator_bindings()[0], expected=None)
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    r = TestClient(app).get(ws["base"] + "/projects", headers={"Authorization": "Bearer not-a-key"})
    assert r.status_code == 401


def test_workspace_isolation_by_membership_and_row_level_security(exported):
    ws = exported
    outsider = person("outsider")
    r = outsider.get(ws["base"] + "/projects")
    assert r.status_code == 403 and r.json()["error"]["code"] == "TENANT_SCOPE_VIOLATION"
    # Row-level security as the application role: another workspace's rows are invisible.
    with psycopg.connect(setting("DATABASE_URL"), row_factory=dict_row) as c:
        c.execute(
            "SELECT set_config('rlgym.workspace', %s, true)",
            ("b0000000-0000-4000-8000-0000000000a2",),
        )
        assert (
            c.execute(
                "SELECT count(*) n FROM projects.task_imports WHERE workspace_id=%s", (ws["id"],)
            ).fetchone()["n"]
            == 0
        )
        c.execute("SELECT set_config('rlgym.workspace', %s, true)", (ws["id"],))
        assert c.execute("SELECT count(*) n FROM projects.task_imports").fetchone()["n"] >= 40
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(
                "INSERT INTO projects.projects(workspace_id,project_id,name,template_id,template_version,spec_sha256,forge_template_id,forge_version,mode,state) "
                "VALUES(%s,'prj_rlsprobe','x','t',1,%s,'f',1,'single_agent','ready')",
                ("b0000000-0000-4000-8000-0000000000a2", "0" * 64),
            )


def test_imported_tasks_and_exports_are_immutable(exported):
    ws = exported
    with psycopg.connect(setting("DATABASE_URL")) as c:
        c.execute("SELECT set_config('rlgym.workspace', %s, true)", (ws["id"],))
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute(
                "UPDATE projects.task_imports SET case_selector='{}'::jsonb WHERE project_id=%s",
                (PROJECT,),
            )
    with psycopg.connect(setting("DATABASE_URL")) as c:
        c.execute("SELECT set_config('rlgym.workspace', %s, true)", (ws["id"],))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("DELETE FROM projects.project_exports WHERE project_id=%s", (PROJECT,))


def test_private_task_part_is_audited_and_never_in_actor_part(exported):
    ws = exported
    detail = (
        person("researcher")
        .get(ws["base"] + f"/projects/{PROJECT}/tasks/task-kyc-0001")
        .json()["data"]
    )
    assert detail["private_label"].startswith("Reviewer only")
    assert "expected" not in json.dumps(detail["actor"]) and "rubric" not in json.dumps(
        detail["actor"]
    )
    with psycopg.connect(setting("MIGRATION_DATABASE_URL")) as c:
        n = c.execute(
            "SELECT count(*) FROM admin.audit_events WHERE workspace_id=%s AND action='task.private_viewed'",
            (ws["id"],),
        ).fetchone()[0]
    assert n >= 1


def test_override_requires_a_different_binding_approver(exported):
    ws = exported
    researcher, sales, admin1 = person("researcher"), person("sales"), person("admin-1")
    bad = post(
        researcher,
        ws["base"] + "/rule-overrides",
        {
            "project_id": PROJECT,
            "alias": "kyc",
            "reason": "x",
            "to_rule": {"kind": "pinned", "pinned_version_id": "other-contract@v1"},
        },
        expected=None,
    )
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "BINDING_INCOMPATIBLE"
    none = post(
        researcher,
        ws["base"] + "/rule-overrides",
        {
            "project_id": PROJECT,
            "alias": "kyc",
            "reason": "x",
            "to_rule": {"kind": "same_data", "seed_family": "kyc_cases-19990101"},
        },
        expected=None,
    )
    assert none.status_code == 409 and none.json()["error"]["code"] == "BINDING_INCOMPATIBLE"
    req = post(
        researcher,
        ws["base"] + "/rule-overrides",
        {
            "project_id": PROJECT,
            "alias": "kyc",
            "reason": "Hold on v2 (it)",
            "to_rule": {"kind": "pinned", "pinned_version_id": "golden-kyc-openenv@v2"},
        },
    ).json()["data"]
    oid = req["short_id"]
    own = post(
        researcher,
        ws["base"] + f"/rule-overrides/{oid}/decision",
        {"decision": "approved"},
        expected=None,
    )
    assert own.status_code == 403  # researcher is not a binding approver either
    viewer = post(
        sales,
        ws["base"] + f"/rule-overrides/{oid}/decision",
        {"decision": "approved"},
        expected=None,
    )
    assert viewer.status_code == 403 and viewer.json()["error"]["code"] == "FORBIDDEN"
    reject_without_note = post(
        admin1,
        ws["base"] + f"/rule-overrides/{oid}/decision",
        {"decision": "rejected"},
        expected=None,
    )
    assert reject_without_note.status_code == 422
    # The database refuses the same person even if the API were bypassed.
    with psycopg.connect(setting("DATABASE_URL")) as c:
        c.execute("SELECT set_config('rlgym.workspace', %s, true)", (ws["id"],))
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(
                "UPDATE projects.rule_overrides SET decided_by=requested_by, decision='approved' WHERE short_id=%s AND workspace_id=%s",
                (oid, ws["id"]),
            )
    todo = admin1.get(ws["base"] + "/todo").json()["data"]
    assert any(i["kind"] == "override_waiting" for grp in todo["groups"] for i in grp["items"])
    assert not any(
        i["kind"] == "override_waiting"
        for grp in researcher.get(ws["base"] + "/todo").json()["data"]["groups"]
        for i in grp["items"]
    )
    approved = post(
        admin1,
        ws["base"] + f"/rule-overrides/{oid}/decision",
        {"decision": "approved", "note": "ok"},
    ).json()["data"]
    assert approved["decision"] == "approved" and approved["decided_by"] == USERS["admin-1"]
    view = researcher.get(ws["base"] + f"/projects/{PROJECT}/selection-rules").json()["data"]
    kyc = view["aliases"][0]
    assert (
        kyc["rule"] == "Pinned · golden-kyc-openenv v2"
        and kyc["override"]
        and kyc["would_bind"] == "golden-kyc-openenv@v2"
    )
    assert "approved by admin-1" in kyc["history"][-1]["change_note"]
    # Admin who requested cannot approve their own request either (different person rule for approvers).
    req2 = post(
        admin1,
        ws["base"] + "/rule-overrides",
        {
            "project_id": PROJECT,
            "alias": "kyc",
            "reason": "admin asks",
            "to_rule": {"kind": "latest"},
        },
        expected=None,
    )
    assert req2.status_code == 201
    self_approve = post(
        admin1,
        ws["base"] + f"/rule-overrides/{req2.json()['data']['short_id']}/decision",
        {"decision": "approved"},
        expected=None,
    )
    assert (
        self_approve.status_code == 422
        and "different person" in self_approve.json()["error"]["message"]
    )
    post(
        person("admin-2"),
        ws["base"] + f"/rule-overrides/{req2.json()['data']['short_id']}/decision",
        {"decision": "rejected", "note": "not now"},
    )
    removed = post(researcher, ws["base"] + f"/rule-overrides/{oid}/remove", {}).json()["data"]
    assert removed["decision"] == "removed"
    kyc = researcher.get(ws["base"] + f"/projects/{PROJECT}/selection-rules").json()["data"][
        "aliases"
    ][0]
    assert (
        kyc["rule"] == "Same data · kyc_cases-20261119"
        and kyc["would_bind"] == "golden-kyc-openenv@v3"
    )


def _eval_rule(ws, criterion):
    view = (
        person("researcher").get(ws["base"] + f"/projects/{PROJECT}/selection-rules").json()["data"]
    )
    return next(c for c in view["criteria"] if c["criterion_id"] == criterion)


def test_evaluator_fix_versions_cohorts_revoke_and_b4(exported):
    ws = exported
    admin = person("admin-1")
    cid = "golden-kyc:decision"
    base = _eval_rule(ws, "decision")
    assert base["binds_now"] == 1 and base["rule"] == "Latest qualified"
    # A broken fix fails its known-case tests and is never selected.
    broken = post(
        admin,
        ws["base"] + f"/evaluators/{cid}/versions",
        {
            "fix_of": 1,
            "reason": "it: wrong field",
            "config": {
                "evidence": "final_output",
                "rules": [
                    {"kind": "output_equals", "field": "next_action", "reference": "decision"}
                ],
            },
        },
    ).json()["data"]
    assert (
        broken["known_case_test"]["result"] == "failed"
        and broken["configuration"]["state"] == "failed"
    )
    assert _eval_rule(ws, "decision")["binds_now"] == 1
    # A good fix (SME "grader wrong") qualifies, binds under Latest qualified and starts a new cohort.
    fix = post(
        admin,
        ws["base"] + f"/evaluators/{cid}/versions",
        {
            "fix_of": 1,
            "reason": "SME smr-0008: grader wrong",
            "source": "smr-0008",
            "known_cases": {
                "sme_case": {
                    **g.evaluator_bindings()[4]["known_cases"]["allowed"],
                    "case_id": "kyc-adult-joint-002",
                }
            },
        },
    ).json()["data"]
    v_fix = fix["configuration"]["version"]
    assert (
        fix["known_case_test"]["result"] == "qualified"
        and len(fix["known_case_test"]["checks"]) == 4
    )
    rule = _eval_rule(ws, "decision")
    assert rule["binds_now"] == v_fix and "new leaderboard cohort" in rule["last_note"]
    todo = admin.get(ws["base"] + "/todo").json()["data"]
    assert any(i["kind"] == "evaluator_new_cohort" for grp in todo["groups"] for i in grp["items"])
    # Same configuration, same verdicts.
    t1 = post(admin, ws["base"] + f"/evaluators/{cid}/test", {"version": v_fix}).json()["data"]
    t2 = post(admin, ws["base"] + f"/evaluators/{cid}/test", {"version": v_fix}).json()["data"]
    assert t1["receipt_id"] == t2["receipt_id"]
    # Revoke with impact: the replacement is v1; the rule falls back automatically.
    impact = admin.get(ws["base"] + f"/evaluators/{cid}/impact?version={v_fix}").json()["data"]
    assert impact["replacement"]["version"] == 1 and impact["projects"][0]["project_id"] == PROJECT
    no_reason = post(
        admin, ws["base"] + f"/evaluators/{cid}/revoke", {"version": v_fix}, expected=None
    )
    assert no_reason.status_code == 422
    post(
        admin,
        ws["base"] + f"/evaluators/{cid}/revoke",
        {"version": v_fix, "reason": "it revoke fix"},
    )
    assert _eval_rule(ws, "decision")["binds_now"] == 1
    # Revoke the last qualified version: B4, the project is Blocked and To do raises it.
    assert (
        admin.get(ws["base"] + f"/evaluators/{cid}/impact?version=1").json()["data"]["replacement"]
        is None
    )
    post(
        admin,
        ws["base"] + f"/evaluators/{cid}/revoke",
        {"version": 1, "reason": "it: no replacement"},
    )
    project = admin.get(ws["base"] + f"/projects/{PROJECT}").json()["data"]
    assert project["state"] == "blocked" and "B4" in project["state_reason"]
    assert project["suggested_actions"][0]["label"] == "Create evaluator fix version"
    todo = admin.get(ws["base"] + "/todo").json()["data"]
    assert any(
        i["kind"] == "evaluator_no_replacement" for grp in todo["groups"] for i in grp["items"]
    )
    # Revocation is final; the version cannot be qualified again.
    with psycopg.connect(setting("DATABASE_URL")) as c:
        c.execute("SELECT set_config('rlgym.workspace', %s, true)", (ws["id"],))
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute(
                "UPDATE catalog.evaluator_configurations SET state='qualified' WHERE workspace_id=%s AND id=%s AND version=1",
                (ws["id"], cid),
            )
    # The RL Gym fixes it itself: a new version from v1, no Studio inbox item.
    again = post(
        admin,
        ws["base"] + f"/evaluators/{cid}/versions",
        {
            "fix_of": 1,
            "allow_from_revoked": True,
            "reason": "re-issue after revoke",
            "config": {**g.evaluator_bindings()[4]["config"], "allow_partial": False},
        },
    ).json()["data"]
    assert again["configuration"]["state"] == "qualified"
    project = admin.get(ws["base"] + f"/projects/{PROJECT}").json()["data"]
    assert project["state"] == "ready"
    events = httpx.get(STUDIO + "/stub/state", timeout=10).json()
    integrations.dispatch_once()
    events = httpx.get(STUDIO + "/stub/state", timeout=10).json()["rlgym_events"]
    assert any(e["data"]["type"] == "evaluator.revoked" and e["data"]["id"] == cid for e in events)
    assert (
        admin.get(ws["base"] + "/inbox-items?kind=evaluator_defect").json()["data"]["items"] == []
    )


def test_evaluator_defect_item_only_when_the_criterion_must_change(exported):
    ws = exported
    r = post(
        person("admin-1"),
        ws["base"] + "/inbox-items",
        {
            "kind": "evaluator_defect",
            "template_id": g.TEMPLATE_ID,
            "version": 8,
            "summary": "grader is wrong",
        },
        expected=None,
    )
    assert r.status_code == 422


def _signed(event, secret=None):
    raw = json.dumps(event).encode()
    ts = str(int(time.time()))
    return raw, {
        "Content-Type": "application/json",
        "X-ADI-Timestamp": ts,
        "X-ADI-Signature": sign(secret or os.environ["RLGYM_REGISTRY_WEBHOOK_SECRET"], ts, raw),
    }


def test_registry_webhook_signature_duplicates_and_gap_resync(exported):
    client = TestClient(app)
    log = httpx.get(
        STUDIO + "/api/v1/registry/events",
        headers={"Authorization": f"Bearer {os.environ['RLGYM_ANVIL_KEY']}"},
    ).json()["events"]
    first = log[0]
    raw, headers = _signed(first, secret="wrong-secret")
    assert client.post("/api/v1/registry-events", content=raw, headers=headers).status_code == 401
    raw, headers = _signed(first)
    dup = client.post("/api/v1/registry-events", content=raw, headers=headers).json()["data"]
    assert dup["status"] == "duplicate"
    # A gap: an event far ahead of the registry's log is not trusted blindly; the cursor stays at what was applied.
    ahead = {
        **first,
        "id": "reg-fake",
        "data": {**first["data"], "seq": log[-1]["data"]["seq"] + 50},
    }
    raw, headers = _signed(ahead)
    gap = client.post("/api/v1/registry-events", content=raw, headers=headers).json()["data"]
    assert gap["status"] == "gap_unresolved" and gap["last_seq"] == log[-1]["data"]["seq"]


def test_urgent_path_when_a_selected_version_fails_requalification(exported):
    ws = exported
    admin1, admin2 = person("admin-1"), person("admin-2")
    with httpx.Client(timeout=120, trust_env=False) as stub:
        v4 = stub.post(STUDIO + "/stub/scenarios/release-v4").json()
        assert (
            v4["state"] == "registered"
        )  # released without the known fixtures: the RL Gym refused it
        receipts = admin1.get(ws["base"] + "/catalog/environments/golden-kyc-openenv@v4").json()[
            "data"
        ]["qualification"]
        assert receipts["result"] == "failed" and receipts["checks"][-1]["name"] == "known_fixtures"
        assert stub.post(STUDIO + "/stub/scenarios/release-v5").json()["state"] == "qualified"
        # Pin this test workspace's project on v4 (another seed family: needs the cohort acknowledgement).
        req = post(
            admin1,
            ws["base"] + "/rule-overrides",
            {
                "project_id": PROJECT,
                "alias": "kyc",
                "reason": "it: urgent path",
                "to_rule": {"kind": "pinned", "pinned_version_id": "golden-kyc-openenv@v5"},
            },
        ).json()["data"]
        assert req["data_change"] is True
        no_ack = post(
            admin2,
            ws["base"] + f"/rule-overrides/{req['short_id']}/decision",
            {"decision": "approved"},
            expected=None,
        )
        assert no_ack.status_code == 422
        post(
            admin2,
            ws["base"] + f"/rule-overrides/{req['short_id']}/decision",
            {"decision": "approved", "new_cohort_acknowledged": True},
        )
        try:
            stub.post(
                STUDIO + "/stub/scenarios/fault/golden-kyc-openenv@v5",
                json={"fault": "reset_keeps_findings"},
            )
            result = stub.post(STUDIO + "/stub/scenarios/requalify/golden-kyc-openenv@v5").json()[
                "data"
            ]
            assert result["result"] == "failed" and result["failure_class"] == "environment_defect"
            assert result["checks"][-1]["name"] == "state_cleared"
            project = admin1.get(ws["base"] + f"/projects/{PROJECT}").json()["data"]
            assert project["state"] == "blocked" and "B1" in project["state_reason"]
            items = admin1.get(ws["base"] + "/inbox-items?kind=environment_defect").json()["data"][
                "items"
            ]
            urgent = [i for i in items if i["environment_version_id"] == "golden-kyc-openenv@v5"]
            assert (
                urgent
                and urgent[0]["urgent"] is True
                and urgent[0]["evidence"]["failed_checks"][0]["name"] == "state_cleared"
            )
            todo = admin1.get(ws["base"] + "/todo").json()["data"]
            assert any(
                i["kind"] == "version_stopped" for grp in todo["groups"] for i in grp["items"]
            )
            integrations.dispatch_once()
            assert any(
                i.get("rlgym_item_id") == urgent[0]["id"]
                for i in stub.get(STUDIO + "/stub/state").json()["inbox"]
            )
            # An environment defect cannot be "re-qualified" away from the RL Gym UI (only infrastructure failures).
            r = post(
                admin1,
                ws["base"] + "/catalog/environments/golden-kyc-openenv@v5/requalify",
                {},
                expected=None,
            )
            assert r.status_code == 422
        finally:
            stub.post(STUDIO + "/stub/scenarios/fault/golden-kyc-openenv@v5", json={})
            stub.post(STUDIO + "/stub/scenarios/requalify/golden-kyc-openenv@v5")
    project = admin1.get(ws["base"] + f"/projects/{PROJECT}").json()["data"]
    assert project["state"] == "ready"
