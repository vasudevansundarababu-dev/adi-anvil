"""Self-provisioned synthetic journey for integration tests.

Replaces the `artifacts/test-runs/journey.json` file written by the retired classic-UI
Playwright journey. It performs the same API setup in a new isolated demo project: fixture
import, rights, approvals, a deterministic two-candidate fixture run, independent reviews,
a finding, an approved built report and a fixture-sender delivery that sends no real email.
Only predetermined fixture candidates run; no provider is called.
"""

import contextlib
import io
import json
import secrets
import time

from fastapi.testclient import TestClient

from anvil import worker
from anvil.api import app
from anvil.auth import hashed
from anvil.config import ROOT
from anvil.db import one, transaction, uid
from anvil.operations import new_demo

USERS = json.loads((ROOT / ".local/demo-identities.json").read_text())
ACTORS = [
    "researcher",
    "advisor",
    "data-engineer",
    "reviewer-1",
    "reviewer-2",
    "admin-1",
    "admin-2",
]


class Journey:
    def __init__(self, name):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            new_demo(name)
        self.project = json.loads(output.getvalue())["project_id"]
        self.base = f"/api/v1/projects/{self.project}"
        self.sessions = []
        self.clients = {actor: self.session(actor) for actor in ACTORS}

    def session(self, actor):
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with transaction() as c:
            c.execute(
                "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
                (hashed(token), USERS[actor], hashed(csrf)),
            )
        self.sessions.append(hashed(token))
        client = TestClient(app)
        client.cookies.set("anvil_session", token)
        client.headers.update({"Origin": "http://127.0.0.1:3202", "X-CSRF-Token": csrf})
        return client

    def close(self):
        with transaction() as c:
            for token_hash in self.sessions:
                c.execute(
                    "UPDATE anvil.sessions SET revoked_at=now() WHERE token_hash=%s", (token_hash,)
                )

    def call(self, actor, path, method="GET", body=None, version=None, expected=None):
        headers = {"Idempotency-Key": uid(), **({"If-Match": str(version)} if version else {})}
        response = self.clients[actor].request(method, self.base + path, json=body, headers=headers)
        if expected is None:
            assert response.status_code < 300, response.text
        else:
            assert response.status_code == expected, response.text
        return response.json()["data"]

    def transition(self, actor, collection, record, action, body=None):
        latest = self.call(actor, f"/{collection}/{record['id']}")
        return self.call(
            actor,
            f"/{collection}/{record['id']}/{action}",
            "POST",
            body or {},
            latest["row_version"],
        )

    def approve(self, collection, record):
        # D-SIMPLE: the project Admin is the single approver.
        return self.transition(
            "admin-1",
            collection,
            record,
            "decisions",
            {
                "purpose": "approval",
                "decision": "approve",
                "rationale": "Product Owner approval for local synthetic pipeline verification only.",
            },
        )

    def work_until(self, done, timeout=120):
        """Process only this project's jobs in-process until `done()` holds.

        A running local worker may claim some jobs first; the lease update is atomic,
        so each job is processed once either way.
        """
        deadline = time.monotonic() + timeout
        while not done():
            assert time.monotonic() < deadline, "synthetic journey did not reach expected state"
            with transaction(self.project, worker=True) as c:
                job = one(
                    c,
                    "UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds',attempts=attempts+1 "
                    "WHERE id=(SELECT id FROM anvil.jobs WHERE project_id=%s AND (status='queued' OR (status='leased' AND lease_until<now())) AND attempts<3 "
                    "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *",
                    (self.project,),
                )
            if not job:
                time.sleep(0.2)
                continue
            original = worker.one
            worker.one = lambda c, query, params=(), job=job: (
                job if query == "SELECT * FROM anvil.claim_job()" else original(c, query, params)
            )
            try:
                assert worker.tick()
            finally:
                worker.one = original
            with transaction(self.project, worker=True) as c:
                state = one(c, "SELECT status,error_code FROM anvil.jobs WHERE id=%s", (job["id"],))
            assert state["status"] == "succeeded", (job["kind"], state)

    def idle(self):
        with transaction(self.project, worker=True) as c:
            return not one(
                c,
                "SELECT 1 FROM anvil.jobs WHERE project_id=%s AND status IN ('queued','leased') AND attempts<3",
                (self.project,),
            )

    def fixture_delivery(self, kit):
        """Network-free fixture sender; no real email is sent."""
        contact = self.call(
            "admin-1",
            "/sales-contacts",
            "POST",
            {
                "name": "Synthetic lab contact",
                "email": "evaluation@lab.invalid",
                "organization_label": "Local fixture lab",
                "contact_basis": "Explicit synthetic test contact for network-free workflow verification only.",
            },
        )
        self.call(
            "admin-1",
            f"/sales-contacts/{contact['id']}/decision",
            "POST",
            {"status": "approved"},
            contact["row_version"],
        )
        sender = self.call(
            "admin-1",
            "/fixture-senders",
            "POST",
            {"name": "Synthetic accepted sender", "scenario": "accepted"},
        )
        self.call(
            "admin-2",
            f"/fixture-senders/{sender['id']}/activate",
            "POST",
            {},
            sender["row_version"],
        )
        approval = self.call(
            "admin-1",
            f"/sales-kits/{kit['id']}/delivery-approvals",
            "POST",
            {"recipient_contact_id": contact["id"], "sender_connection_id": sender["id"]},
        )
        mail = self.call(
            "admin-1",
            f"/sales-kits/{kit['id']}/simulate-send",
            "POST",
            {"delivery_approval_id": approval["id"], "content_hash": approval["content_hash"]},
        )

        def delivery():
            return self.call("admin-1", f"/sales-deliveries/{mail['id']}")

        self.work_until(lambda: delivery()["status"] == "fixture_accepted")
        assert delivery()["real_email_sent"] is False

    def run(self):
        objective = self.call(
            "researcher",
            "/objectives",
            "POST",
            {
                "title": "Synthetic commercial-constraint diagnostic " + uid()[:8],
                "origin": "adi_initiated",
                "entry_type": "capability",
                "hypothesis": "Supplied hard constraints are preserved in recommendations.",
                "business_context": "Original synthetic fixture exercise; no measured model performance.",
                "measurement_plan": "Three original cases; two deterministic candidates; one attempt each; anchored rubric and critical overrides; descriptive results only.",
                "researcher_id": USERS["researcher"],
                "advisor_id": USERS["advisor"],
                "product_owner_id": USERS["product-owner"],
            },
        )
        self.transition("researcher", "objectives", objective, "submit")
        self.approve("objectives", objective)
        cases = self.call(
            "data-engineer",
            "/fixtures/import",
            "POST",
            {
                "case_ids": ["MKT-001", "FIN-001", "STR-001"],
                "reviewer_id": USERS["reviewer-1"],
                "advisor_id": USERS["advisor"],
            },
        )
        for source in cases:
            self.call(
                "admin-1",
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
        for rubric in self.call("data-engineer", "/rubrics"):
            if rubric["lifecycle"] == "draft":
                self.transition("data-engineer", "rubrics", rubric, "submit")
                self.approve("rubrics", rubric)
        for task in self.call("data-engineer", "/tasks"):
            if task["lifecycle"] == "draft":
                self.transition("data-engineer", "tasks", task, "submit")
                self.approve("tasks", task)
                self.transition("data-engineer", "tasks", task, "publish")
        tasks = self.call("researcher", "/tasks")
        assert len(tasks) == 3
        suite = self.call(
            "researcher",
            "/suites",
            "POST",
            {
                "title": "Three-case original synthetic suite",
                "objective_revision_id": objective["current_revision_id"],
                "task_revision_ids": [t["current_revision_id"] for t in tasks],
                "selection_method": "All three supplied original fixtures.",
                "exposure_note": "Known development fixtures; no generalization or faculty validation.",
                "advisor_id": USERS["advisor"],
                "planned_source_count": 200,
            },
        )
        self.transition("researcher", "suites", suite, "submit")
        self.approve("suites", suite)
        suite = self.transition("researcher", "suites", suite, "freeze")
        protocol = self.call(
            "researcher",
            "/protocols",
            "POST",
            {
                "title": "Deterministic two-candidate pilot",
                "objective_revision_id": objective["current_revision_id"],
                "suite_revision_id": suite["current_revision_id"],
                "candidates": ["fixture-correct", "fixture-constraint-blind"],
                "reviewer_ids": [USERS["reviewer-1"], USERS["reviewer-2"]],
                "adjudicator_id": USERS["adjudicator"],
                "advisor_id": USERS["advisor"],
                "comparison_policy": "Same frozen actor inputs, descriptive fixture pipeline checks; no model ranking.",
                "pass_policy": "Rubric threshold and critical override; second grader for critical, borderline and sampled outputs.",
            },
        )
        self.transition("researcher", "protocols", protocol, "submit")
        self.approve("protocols", protocol)
        run = self.call(
            "researcher", "/runs", "POST", {"protocol_revision_id": protocol["current_revision_id"]}
        )
        self.call("researcher", f"/runs/{run['id']}/launch", "POST", {}, run["row_version"])

        def episodes():
            return self.call("researcher", f"/runs/{run['id']}")["episodes"]

        self.work_until(lambda: sum(e["state"] == "awaiting_review" for e in episodes()) == 6)
        before = episodes()
        assert all(e["invocation_count"] == 1 for e in before)
        for episode in before:
            for name in ["reviewer-1", "reviewer-2"]:
                # D-SIMPLE: the second grader acts only on critical, borderline or sampled outputs.
                inbox = self.call(name, "/reviews")
                if not any(
                    r["id"] == episode["id"] and not r["my_review_submitted"] for r in inbox
                ):
                    continue
                detail = self.call(name, f"/reviews/{episode['id']}")
                assert "candidate_key" not in json.dumps(detail)
                output = json.loads(detail["output"])
                bad = (
                    "despite" in output["constraint_checks"]
                    or "even though" in output["constraint_checks"]
                )
                quote = '"selected_option": "' + output["selected_option"] + '"'
                self.call(
                    name,
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
        self.work_until(
            lambda: self.call("researcher", f"/runs/{run['id']}")["state"] == "reviewed"
        )
        final = episodes()
        assert sum(e["outcome"] == "pass" for e in final) == 3
        assert all(e["invocation_count"] == 1 for e in final)
        for source in cases:
            self.call(
                "admin-1",
                f"/cases/{source['id']}/rights",
                "POST",
                {
                    "operation": "report_sharing",
                    "destination": "internal_fixture",
                    "status": "approved",
                    "evidence": "Reviewed synthetic aggregate-only internal draft sharing. No raw case redistribution or external customer delivery.",
                },
                source["row_version"],
            )
        evidence = self.call("researcher", f"/episodes/{final[0]['id']}/evidence")
        finding = self.call(
            "researcher",
            "/findings",
            "POST",
            {
                "title": "Reviewed illustrative output observation",
                "episode_id": final[0]["id"],
                "observation": "The scripted fixture output contains the selected option shown in the quoted evidence.",
                "hypothesis": None,
                "alternatives": [
                    "Predetermined fixture behavior; no inference about model reasoning."
                ],
                "confidence": "unknown",
                "criterion": "R2",
                "output_quote": '"selected_option": "'
                + json.loads(evidence["output"])["selected_option"]
                + '"',
                "capability": "constraint_preservation",
                "advisor_id": USERS["advisor"],
            },
        )
        # Findings are approved on submit; the report approval covers them.
        self.transition("researcher", "findings", finding, "submit")
        report = self.call(
            "researcher",
            "/reports",
            "POST",
            {
                "title": "Reviewed synthetic diagnostic",
                "run_id": run["id"],
                "finding_revision_ids": [finding["current_revision_id"]],
                "advisor_id": USERS["advisor"],
                "reviewer_id": USERS["reviewer-1"],
                "product_owner_id": USERS["product-owner"],
                "audience": "internal_fixture",
            },
        )
        self.transition("researcher", "reports", report, "submit")
        report = self.approve("reports", report)

        def approved_kit():
            return any(
                k["content"].get("report_revision_id") == report["current_revision_id"]
                and k["lifecycle"] == "approved"
                for k in self.call("researcher", "/sales-kits")
            )

        self.work_until(approved_kit)
        self.transition("researcher", "reports", report, "build")
        for name in ["sales-kit.pdf", "sales-kit.html", "evidence.zip", "email-draft.txt"]:
            response = self.clients["admin-1"].get(
                self.base + f"/reports/{report['id']}/download/{name}"
            )
            assert response.status_code == 200, (name, response.text)
        kit = next(
            k
            for k in self.call("admin-1", "/sales-kits")
            if k["content"].get("report_revision_id") == report["current_revision_id"]
        )
        assert kit["content"]["artifacts"]["evidence.zip"]
        self.fixture_delivery(kit)
        self.work_until(self.idle)
        return {
            "project_id": self.project,
            "run_id": run["id"],
            "objective": objective,
            "suite": suite,
            "protocol": protocol,
            "report": report,
            "episodes": final,
            "tasks": tasks,
        }


def provision_journey():
    journey = Journey("Synthetic integration journey " + uid()[:12])
    try:
        return journey.run()
    finally:
        journey.close()
