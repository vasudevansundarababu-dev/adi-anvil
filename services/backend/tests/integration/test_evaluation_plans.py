"""D-SIMPLE wizard: five steps, one Product Owner decision, explicit launch."""

from test_api_security import BASE, USERS

from anvil.cli import PROJECT
from anvil.db import one, transaction

RUBRIC = {
    "criteria": [
        {
            "id": "R1",
            "label": "Accuracy",
            "weight_bps": 6000,
            "anchors": {str(i): f"Accuracy level {i}" for i in range(5)},
        },
        {
            "id": "R2",
            "label": "Constraints",
            "weight_bps": 4000,
            "anchors": {str(i): f"Constraint level {i}" for i in range(5)},
        },
    ],
    "threshold": 70,
}


def call(client_factory, name):
    client, _ = client_factory(name)

    def go(method, path, body=None, version=None, expected=200):
        headers = {"Idempotency-Key": __import__("uuid").uuid4().hex}
        if version is not None:
            headers["If-Match"] = str(version)
        r = client.request(method, BASE + path, json=body, headers=headers)
        assert r.status_code == expected, (path, r.status_code, r.text)
        return r.json().get("data")

    return go


def new_plan(researcher, title="Constraint preservation under budget limits"):
    return researcher(
        "POST",
        "/evaluations",
        {
            "title": title,
            "hypothesis": "Candidates preserve hard budget constraints when recommending options.",
            "success_criteria": "Score at least 70 on every task with no critical constraint violation.",
        },
        expected=201,
    )


def test_wizard_single_product_owner_approval_prepares_run(client_factory):
    researcher = call(client_factory, "researcher")
    owner = call(client_factory, "admin-1")
    options = researcher("GET", "/evaluations/options")
    assert {c["id"] for c in options["cases"]} == {"MKT-001", "FIN-001", "STR-001"}
    assert options["default_graders"], "a grader is always proposed"

    plan = new_plan(researcher)
    assert plan["state"] == "draft" and plan["objective"]["lifecycle"] == "draft"
    researcher("POST", f"/evaluations/{plan['id']}/submit", {}, plan["row_version"], 422)

    plan = researcher(
        "PATCH",
        f"/evaluations/{plan['id']}",
        {
            "background_notes": "Prior fixture runs show constraint drift on long option lists.",
            "sources": [{"label": "Internal note", "url": "https://example.test/note"}],
            "case_ids": ["MKT-001", "FIN-001"],
            "rubric": RUBRIC,
        },
        plan["row_version"],
    )
    assert plan["missing"] == []
    bad = dict(RUBRIC, threshold=70, criteria=[{**RUBRIC["criteria"][0], "weight_bps": 5000}])
    researcher("PATCH", f"/evaluations/{plan['id']}", {"rubric": bad}, plan["row_version"], 422)

    owner(
        "POST",
        f"/evaluations/{plan['id']}/decision",
        {"decision": "approve", "rationale": "Not yet submitted."},
        plan["row_version"],
        409,
    )
    plan = researcher("POST", f"/evaluations/{plan['id']}/submit", {}, plan["row_version"])
    assert plan["state"] == "submitted" and len(plan["task_ids"]) == 2
    researcher(
        "PATCH", f"/evaluations/{plan['id']}", {"case_ids": ["STR-001"]}, plan["row_version"], 409
    )
    # Only a Product Owner decides; the author cannot approve their own plan without that role.
    researcher(
        "POST",
        f"/evaluations/{plan['id']}/decision",
        {"decision": "approve", "rationale": "Author attempting approval."},
        plan["row_version"],
        403,
    )
    plan = owner(
        "POST",
        f"/evaluations/{plan['id']}/decision",
        {"decision": "approve", "rationale": "Plan, tasks, rubric and data rights reviewed."},
        plan["row_version"],
    )
    assert plan["state"] == "approved" and plan["self_approved"] is False
    lifecycles = {(c["kind"], c["lifecycle"]) for c in plan["components"]}
    assert lifecycles == {
        ("task", "published"),
        ("rubric", "approved"),
        ("suite", "frozen"),
        ("protocol", "approved"),
    }
    assert plan["objective"]["lifecycle"] == "approved"
    assert plan["run"]["state"] == "draft"

    with transaction(PROJECT, USERS["researcher"]) as c:
        rubric = one(
            c,
            """SELECT v.content FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id
               WHERE r.kind='rubric' AND v.content->>'title'=%s LIMIT 1""",
            (plan["title"] + " rubric",),
        )
        assert rubric["content"]["threshold"] == 70
        assert [x["id"] for x in rubric["content"]["criteria"]] == ["R1", "R2"]
        decisions = c.execute(
            "SELECT DISTINCT reviewer_id,purpose FROM anvil.review_decisions d JOIN anvil.revisions v ON v.id=d.revision_id JOIN anvil.resources r ON r.id=v.resource_id WHERE r.id IN (SELECT (jsonb_array_elements_text(task_ids))::uuid FROM anvil.evaluation_plans WHERE id=%s)",
            (plan["id"],),
        ).fetchall()
        assert {(str(d["reviewer_id"]), d["purpose"]) for d in decisions} == {
            (USERS["admin-1"], "approval")
        }

    run = researcher("POST", f"/runs/{plan['run']['id']}/launch", {}, plan["run"]["row_version"])
    assert run["state"] == "queued"
    with transaction(PROJECT, USERS["researcher"]) as c:
        episodes = one(c, "SELECT count(*) n FROM anvil.episodes WHERE run_id=%s", (run["id"],))
        assert episodes["n"] == 4  # two tasks x two fixture candidates


def approved_single_episode_plan(researcher, owner, title):
    plan = new_plan(researcher, title)
    plan = researcher(
        "PATCH",
        f"/evaluations/{plan['id']}",
        {
            "case_ids": ["STR-001"],
            "rubric": RUBRIC,
            "candidates": ["fixture-correct"],
            "grader_ids": [USERS["reviewer-1"], USERS["reviewer-2"]],
        },
        plan["row_version"],
    )
    plan = researcher("POST", f"/evaluations/{plan['id']}/submit", {}, plan["row_version"])
    plan = owner(
        "POST",
        f"/evaluations/{plan['id']}/decision",
        {"decision": "approve", "rationale": "Grading rule verification plan."},
        plan["row_version"],
    )
    run = researcher("POST", f"/runs/{plan['run']['id']}/launch", {}, plan["run"]["row_version"])
    return plan, run


def wait_for_review(run_id):
    import time

    from anvil import worker

    for _ in range(60):
        worker.tick()
        with transaction(PROJECT, USERS["researcher"]) as c:
            row = one(c, "SELECT id,state FROM anvil.episodes WHERE run_id=%s", (run_id,))
        if row["state"] == "awaiting_review":
            return str(row["id"])
        time.sleep(0.25)
    raise AssertionError("Episode never reached review")


def judgment(detail, critical):
    output = detail["output"]
    span = output.strip()[:12]
    return {
        "scores": {"R1": 4, "R2": 4},
        "critical": critical,
        "evidence": {"R1": span, "R2": span},
        "rationale": "Scripted grading-rule verification on a synthetic fixture output.",
    }


def test_second_grader_on_critical_and_owner_adjudicates_dispute(client_factory):
    researcher = call(client_factory, "researcher")
    owner = call(client_factory, "admin-1")
    graders = {name: call(client_factory, name) for name in ("reviewer-1", "reviewer-2")}
    plan, run = approved_single_episode_plan(researcher, owner, "Grading rule verification")
    eid = wait_for_review(run["id"])

    def inbox(name):
        return {r["id"]: r for r in graders[name]("GET", "/reviews")}

    first, second = (
        ("reviewer-1", "reviewer-2")
        if eid in inbox("reviewer-1")
        else (
            "reviewer-2",
            "reviewer-1",
        )
    )
    detail = graders[first]("GET", f"/reviews/{eid}")
    rule = detail["rubric"]["critical_rules"][0]
    # A critical violation always needs a second grader.
    graders[first](
        "POST", f"/episodes/{eid}/assessments", judgment(detail, [rule]), detail["row_version"]
    )
    assert eid in inbox(second) and not inbox(second)[eid]["my_review_submitted"]
    detail = graders[second]("GET", f"/reviews/{eid}")
    graders[second](
        "POST", f"/episodes/{eid}/assessments", judgment(detail, []), detail["row_version"]
    )
    # Disagreement on the critical rule becomes a dispute; with no named adjudicator, a
    # Product Owner who did not grade adjudicates.
    detail = owner("GET", f"/reviews/{eid}")
    assert detail["state"] == "disputed" and detail["adjudication_allowed"] is True
    graders[first](
        "POST", f"/episodes/{eid}/adjudicate", judgment(detail, [rule]), detail["row_version"], 403
    )
    result = owner(
        "POST", f"/episodes/{eid}/adjudicate", judgment(detail, [rule]), detail["row_version"]
    )
    assert result["final"] is True and result["outcome"] == "fail"


def test_clear_result_is_final_after_one_grade_unless_sampled(client_factory):
    from anvil.evaluation import sampled

    researcher = call(client_factory, "researcher")
    owner = call(client_factory, "admin-1")
    graders = {name: call(client_factory, name) for name in ("reviewer-1", "reviewer-2")}
    plan, run = approved_single_episode_plan(researcher, owner, "Single grade verification")
    eid = wait_for_review(run["id"])
    first = (
        "reviewer-1"
        if eid in {r["id"] for r in graders["reviewer-1"]("GET", "/reviews")}
        else "reviewer-2"
    )
    second = "reviewer-2" if first == "reviewer-1" else "reviewer-1"
    detail = graders[first]("GET", f"/reviews/{eid}")
    result = graders[first](
        "POST", f"/episodes/{eid}/assessments", judgment(detail, []), detail["row_version"]
    )
    with transaction(PROJECT, USERS["researcher"]) as c:
        protocol_revision = one(
            c, "SELECT protocol_revision_id FROM anvil.runs WHERE id=%s", (run["id"],)
        )
    expected_second = sampled(protocol_revision["protocol_revision_id"], eid)
    assert result["final"] is (not expected_second)
    assert (eid in {r["id"] for r in graders[second]("GET", "/reviews")}) is expected_second


def test_changes_requested_reopens_the_plan(client_factory):
    researcher = call(client_factory, "researcher")
    owner = call(client_factory, "admin-1")
    plan = new_plan(researcher, "Changes requested evaluation plan")
    plan = researcher(
        "PATCH",
        f"/evaluations/{plan['id']}",
        {"case_ids": ["STR-001"], "rubric": RUBRIC},
        plan["row_version"],
    )
    plan = researcher("POST", f"/evaluations/{plan['id']}/submit", {}, plan["row_version"])
    plan = owner(
        "POST",
        f"/evaluations/{plan['id']}/decision",
        {"decision": "changes_requested", "rationale": "Narrow the hypothesis first."},
        plan["row_version"],
    )
    assert plan["state"] == "changes_requested"
    assert plan["objective"]["lifecycle"] == "changes_requested"
    plan = researcher(
        "PATCH",
        f"/evaluations/{plan['id']}",
        {"hypothesis": "Candidates preserve the stated budget cap in every recommendation."},
        plan["row_version"],
    )
    assert plan["objective"]["lifecycle"] == "draft"


def test_plan_is_project_scoped_and_role_checked(client_factory):
    researcher = call(client_factory, "researcher")
    outsider = call(client_factory, "outsider")
    sales = call(client_factory, "sales")
    plan = new_plan(researcher, "Scoped evaluation plan")
    outsider("GET", f"/evaluations/{plan['id']}", expected=404)
    sales(
        "POST",
        "/evaluations",
        {
            "title": "Sales cannot author",
            "hypothesis": "Not permitted for this role at all.",
            "success_criteria": "Not permitted for this role to define at all.",
        },
        expected=201,
    )
    reviewer = call(client_factory, "reviewer-1")
    reviewer(
        "PATCH",
        f"/evaluations/{plan['id']}",
        {"case_ids": ["MKT-001"]},
        plan["row_version"],
        403,
    )


def test_support_bot_answers_locally_audits_and_is_project_scoped(client_factory):
    researcher = call(client_factory, "researcher")
    outsider = call(client_factory, "outsider")
    body = {
        "question": "Which fields are required on this step?",
        "screen": {
            "path": "/p/x/evaluations",
            "title": "Evaluations",
            "fields": [{"label": "Hypothesis", "type": "textarea", "required": True}],
        },
    }
    answer = researcher("POST", "/support/ask", body)
    assert "Hypothesis" in answer["answer"] and answer["model"] == "local-help-pack"
    outsider("POST", "/support/ask", body, expected=404)
    with transaction(PROJECT, USERS["researcher"]) as c:
        events = c.execute(
            "SELECT action,metadata FROM anvil.audit_events WHERE actor_id=%s AND action LIKE 'support.%%' ORDER BY event_seq DESC LIMIT 2",
            (USERS["researcher"],),
        ).fetchall()
    assert {e["action"] for e in events} == {"support.asked", "support.answered"}
    assert all("question" not in e["metadata"] for e in events)  # content is never stored
