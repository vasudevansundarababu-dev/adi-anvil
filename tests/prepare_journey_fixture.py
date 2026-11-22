"""Rebuild `artifacts/test-runs/journey.json`: one reviewed synthetic diagnostic run in this checkout's database.

The retired classic-UI journey (tests/e2e/journey.spec.ts, ignored by playwright.config.ts) used to leave this file
behind; several workspace integration and browser tests still read it. This script makes the same API calls the
journey made (objective → fixture cases with rights → rubrics/tasks approved → frozen suite → protocol → run →
independent reviews → finding → approved report) through the running local API, with the local synthetic identities
and the same test-session helper the integration tests use. It never signs in with a password, calls no model (the
candidates are the deterministic fixture candidates) and sends nothing outside 127.0.0.1.

Usage (stack running: pnpm dev):  python tests/prepare_journey_fixture.py [--if-missing]
"""

import json
import secrets
import subprocess
import sys
import time
import uuid

import httpx
import psycopg

from anvil.auth import hashed
from anvil.config import ROOT, setting
from anvil.db import transaction

API = "http://127.0.0.1:8200"
TARGET = ROOT / "artifacts/test-runs/journey.json"
IDS = json.loads((ROOT / ".local/demo-identities.json").read_text())


def still_valid():
    if not TARGET.exists():
        return False
    data = json.loads(TARGET.read_text())
    with psycopg.connect(setting("MIGRATION_DATABASE_URL")) as c:
        row = c.execute(
            "SELECT state FROM anvil.runs WHERE id=%s AND project_id=%s",
            (data.get("run_id"), data.get("project_id")),
        ).fetchone()
    return bool(row and row[0] == "reviewed" and data.get("delivery_id"))


class Person:
    def __init__(self, name):
        token, self.csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with transaction() as c:
            c.execute(
                "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
                (hashed(token), IDS[name], hashed(self.csrf)),
            )
        self.client = httpx.Client(
            base_url=API, timeout=60, trust_env=False, cookies={"anvil_session": token}
        )

    def call(self, path, method="GET", body=None, version=None, key=None):
        headers = {
            "Origin": setting("WEB_ORIGIN"),
            "X-CSRF-Token": self.csrf,
            "Idempotency-Key": key or str(uuid.uuid4()),
        }
        if version:
            headers["If-Match"] = str(version)
        r = self.client.request(method, path, json=body, headers=headers)
        data = r.json()
        if r.status_code >= 300:
            raise RuntimeError(f"{method} {path} → {r.status_code}: {json.dumps(data)[:400]}")
        return data["data"]


def main():
    if "--if-missing" in sys.argv and still_valid():
        print(json.dumps({"journey": str(TARGET), "status": "valid"}))
        return
    project = json.loads(
        subprocess.check_output(
            [
                sys.executable,
                str(ROOT / "scripts/local.py"),
                "demo-new",
                "--name",
                f"Synthetic journey fixture {int(time.time())}",
            ],
            cwd=ROOT,
            text=True,
        )
        .strip()
        .splitlines()[-1]
    )["project_id"]
    base = f"/api/v1/projects/{project}"
    people = {
        n: Person(n)
        for n in ("researcher", "data-engineer", "reviewer-1", "reviewer-2", "admin-1", "admin-2")
    }
    R, D, P = people["researcher"], people["data-engineer"], people["admin-1"]

    def call(who, path, method="GET", body=None, version=None, key=None):
        return who.call(base + path, method, body, version, key)

    def transition(who, col, rec, action, body=None):
        latest = call(who, f"/{col}/{rec['id']}")
        return call(who, f"/{col}/{rec['id']}/{action}", "POST", body or {}, latest["row_version"])

    def approve(who, col, rec):
        return transition(
            who,
            col,
            rec,
            "decisions",
            {
                "purpose": "approval",
                "decision": "approve",
                "rationale": "Product Owner approval for local synthetic pipeline verification only.",
            },
        )

    objective = call(
        R,
        "/objectives",
        "POST",
        {
            "title": f"Synthetic commercial-constraint diagnostic {int(time.time())}",
            "origin": "adi_initiated",
            "entry_type": "capability",
            "hypothesis": "Supplied hard constraints are preserved in recommendations.",
            "business_context": "Original synthetic fixture exercise; no measured model performance.",
            "measurement_plan": "Three original cases; two deterministic candidates; one attempt each; anchored rubric and critical overrides; descriptive results only.",
            "researcher_id": IDS["researcher"],
            "advisor_id": IDS["advisor"],
            "product_owner_id": IDS["product-owner"],
        },
    )
    transition(R, "objectives", objective, "submit")
    approve(P, "objectives", objective)
    cases = call(
        D,
        "/fixtures/import",
        "POST",
        {
            "case_ids": ["MKT-001", "FIN-001", "STR-001"],
            "reviewer_id": IDS["reviewer-1"],
            "advisor_id": IDS["advisor"],
        },
    )
    for source in cases:
        call(
            P,
            f"/cases/{source['id']}/rights",
            "POST",
            {
                "operation": "managed_evaluation",
                "destination": "local_fixture",
                "status": "approved",
                "evidence": "Reviewed original synthetic fixture rights for local pipeline testing only; no external processing.",
            },
            source["row_version"],
        )
    for rubric in call(D, "/rubrics"):
        if rubric["lifecycle"] == "draft":
            transition(D, "rubrics", rubric, "submit")
            approve(P, "rubrics", rubric)
    for task in call(D, "/tasks"):
        if task["lifecycle"] == "draft":
            transition(D, "tasks", task, "submit")
            approve(P, "tasks", task)
            transition(D, "tasks", task, "publish")
    tasks = call(R, "/tasks")
    suite = call(
        R,
        "/suites",
        "POST",
        {
            "title": "Three-case original synthetic suite",
            "objective_revision_id": objective["current_revision_id"],
            "task_revision_ids": [t["current_revision_id"] for t in tasks],
            "selection_method": "All three supplied original fixtures.",
            "exposure_note": "Known development fixtures; no generalization or faculty validation.",
            "advisor_id": IDS["advisor"],
            "planned_source_count": 200,
        },
    )
    transition(R, "suites", suite, "submit")
    approve(P, "suites", suite)
    transition(R, "suites", suite, "freeze")
    protocol = call(
        R,
        "/protocols",
        "POST",
        {
            "title": "Deterministic two-candidate pilot",
            "objective_revision_id": objective["current_revision_id"],
            "suite_revision_id": suite["current_revision_id"],
            "candidates": ["fixture-correct", "fixture-constraint-blind"],
            "reviewer_ids": [IDS["reviewer-1"], IDS["reviewer-2"]],
            "adjudicator_id": IDS["adjudicator"],
            "advisor_id": IDS["advisor"],
            "comparison_policy": "Same frozen actor inputs, descriptive fixture pipeline checks; no model ranking.",
            "pass_policy": "Rubric threshold and critical override; second grader for critical, borderline and sampled outputs.",
        },
    )
    transition(R, "protocols", protocol, "submit")
    approve(P, "protocols", protocol)
    run = call(R, "/runs", "POST", {"protocol_revision_id": protocol["current_revision_id"]})
    call(R, f"/runs/{run['id']}/launch", "POST", {}, run["row_version"])
    deadline = time.time() + 120
    while time.time() < deadline:
        current = call(R, f"/runs/{run['id']}")
        if sum(1 for e in current["episodes"] if e["state"] == "awaiting_review") == 6:
            break
        time.sleep(1)
    else:
        raise RuntimeError(
            "the local worker did not prepare six episodes for review (is pnpm dev running?)"
        )
    for episode in current["episodes"]:
        for name in ("reviewer-1", "reviewer-2"):
            who = people[name]
            inbox = call(who, "/reviews")
            if not any(
                r["id"] == episode["id"] and not r.get("my_review_submitted") for r in inbox
            ):
                continue
            detail = call(who, f"/reviews/{episode['id']}")
            output = json.loads(detail["output"])
            bad = (
                "despite" in output["constraint_checks"]
                or "even though" in output["constraint_checks"]
            )
            quote = '"selected_option": "' + output["selected_option"] + '"'
            call(
                who,
                f"/episodes/{episode['id']}/assessments",
                "POST",
                {
                    "scores": {"R1": 4, "R2": 0 if bad else 4, "R3": 4},
                    "critical": detail["rubric"]["critical_rules"] if bad else [],
                    "evidence": {"R1": quote, "R2": quote, "R3": quote},
                    "rationale": "Scripted independent synthetic judgment; fixture verification only.",
                },
                detail["row_version"],
            )
    deadline = time.time() + 120
    while time.time() < deadline and call(R, f"/runs/{run['id']}")["state"] != "reviewed":
        time.sleep(1)
    final = call(R, f"/runs/{run['id']}")
    if final["state"] != "reviewed":
        raise RuntimeError(f"run {run['id']} did not reach reviewed")
    for source in cases:
        latest = call(P, f"/cases/{source['id']}")
        call(
            P,
            f"/cases/{source['id']}/rights",
            "POST",
            {
                "operation": "report_sharing",
                "destination": "internal_fixture",
                "status": "approved",
                "evidence": "Reviewed synthetic aggregate-only internal draft sharing. No raw case redistribution or external customer delivery.",
            },
            latest["row_version"],
        )
    evidence = call(R, f"/episodes/{final['episodes'][0]['id']}/evidence")
    finding = call(
        R,
        "/findings",
        "POST",
        {
            "title": "Reviewed illustrative output observation",
            "episode_id": final["episodes"][0]["id"],
            "observation": "The scripted fixture output contains the selected option shown in the quoted evidence.",
            "hypothesis": None,
            "alternatives": ["Predetermined fixture behavior; no inference about model reasoning."],
            "confidence": "unknown",
            "criterion": "R2",
            "output_quote": '"selected_option": "'
            + json.loads(evidence["output"])["selected_option"]
            + '"',
            "capability": "constraint_preservation",
            "advisor_id": IDS["advisor"],
        },
    )
    transition(R, "findings", finding, "submit")
    report = call(
        R,
        "/reports",
        "POST",
        {
            "title": "Reviewed synthetic diagnostic",
            "run_id": run["id"],
            "finding_revision_ids": [finding["current_revision_id"]],
            "advisor_id": IDS["advisor"],
            "reviewer_id": IDS["reviewer-1"],
            "product_owner_id": IDS["product-owner"],
            "audience": "internal_fixture",
        },
    )
    transition(R, "reports", report, "submit")
    approve(P, "reports", report)
    # The approved report's sales kit, built, and one simulated delivery through a fixture sender (network-free;
    # ANVIL_REAL_EMAIL_ENABLED stays false and the delivery records real_email_sent = false).
    deadline = time.time() + 120
    kit = None
    while time.time() < deadline and not kit:
        kit = next(
            (
                k
                for k in call(P, "/sales-kits")
                if k["content"].get("report_revision_id") == report["current_revision_id"]
                and k["lifecycle"] == "approved"
            ),
            None,
        )
        if not kit:
            time.sleep(1)
    if not kit:
        raise RuntimeError("the approved report's sales kit did not appear")
    transition(R, "reports", report, "build")
    deadline = time.time() + 120
    while time.time() < deadline:
        kit = next(k for k in call(P, "/sales-kits") if k["id"] == kit["id"])
        if (kit["content"].get("artifacts") or {}).get("evidence.zip"):
            break
        time.sleep(1)
    contact = call(
        P,
        "/sales-contacts",
        "POST",
        {
            "name": "Synthetic lab contact",
            "email": "evaluation@lab.invalid",
            "organization_label": "Local fixture lab",
            "contact_basis": "Explicit synthetic test contact for network-free workflow verification only.",
        },
    )
    call(
        P,
        f"/sales-contacts/{contact['id']}/decision",
        "POST",
        {"status": "approved"},
        contact["row_version"],
    )
    sender = call(
        P, "/fixture-senders", "POST", {"name": "Synthetic accepted sender", "scenario": "accepted"}
    )
    call(
        people["admin-2"],
        f"/fixture-senders/{sender['id']}/activate",
        "POST",
        {},
        sender["row_version"],
    )
    approval = call(
        P,
        f"/sales-kits/{kit['id']}/delivery-approvals",
        "POST",
        {"recipient_contact_id": contact["id"], "sender_connection_id": sender["id"]},
    )
    mail = call(
        P,
        f"/sales-kits/{kit['id']}/simulate-send",
        "POST",
        {"delivery_approval_id": approval["id"], "content_hash": approval["content_hash"]},
    )
    deadline = time.time() + 120
    while time.time() < deadline:
        delivery = call(P, f"/sales-deliveries/{mail['id']}")
        if delivery["status"] == "fixture_accepted":
            break
        time.sleep(1)
    if delivery["status"] != "fixture_accepted" or delivery.get("real_email_sent") is not False:
        raise RuntimeError(f"simulated delivery ended as {delivery['status']}")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps(
            {
                "project_id": project,
                "run_id": run["id"],
                "objective": objective,
                "suite": suite,
                "protocol": protocol,
                "report": report,
                "episodes": final["episodes"],
                "sales_kit_id": kit["id"],
                "delivery_id": mail["id"],
                "synthetic": True,
                "built_by": "tests/prepare_journey_fixture.py",
            },
            indent=2,
        )
    )
    print(
        json.dumps(
            {"journey": str(TARGET), "project_id": project, "run_id": run["id"], "status": "built"}
        )
    )


if __name__ == "__main__":
    main()
