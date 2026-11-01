from fastapi import HTTPException
from psycopg.types.json import Jsonb

from anvil.auth import require
from anvil.db import audit, digest, one, uid
from anvil.schemas import SCHEMAS

CONTENT_ROLES = ("admin", "rl-engineer")


def get_resource(c, rid, lock=False):
    r = one(
        c,
        """SELECT r.*,v.content,v.content_hash,v.revision FROM anvil.resources r
                  JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE r.id=%s"""
        + (" FOR UPDATE OF r" if lock else ""),
        (rid,),
    )
    if not r:
        raise HTTPException(404, "Resource not found")
    return r


def get_revision(c, rid, kind=None, lifecycle=None):
    r = one(
        c,
        """SELECT v.*,r.kind,r.lifecycle,r.current_revision_id FROM anvil.revisions v
                  JOIN anvil.resources r ON r.id=v.resource_id WHERE v.id=%s""",
        (rid,),
    )
    if not r or (kind and r["kind"] != kind):
        raise HTTPException(404, "Revision not found")
    if lifecycle and (r["lifecycle"] not in lifecycle or r["current_revision_id"] != r["id"]):
        raise HTTPException(409, "Required revision is not current and qualified")
    return r


def assigned(c, project, user, role):
    if not one(
        c,
        "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.role=%s AND m.active AND u.active",
        (project, user, "admin" if role == "admin" else "rl-engineer"),
    ):
        # Assignments are individual duties, not extra access roles; Admin can fill them.
        if not one(
            c,
            "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.role='admin' AND m.active AND u.active",
            (project, user),
        ):
            raise HTTPException(422, "Assigned person is not an active project member")


def validate_content(c, project, kind, body):
    if kind not in SCHEMAS:
        raise HTTPException(422, "Use the typed import/service for this resource")
    content = SCHEMAS[kind].model_validate(body).model_dump(mode="json")
    assignments = {
        "researcher_id": "researcher",
        "advisor_id": "advisor",
        "reviewer_id": "reviewer",
        "product_owner_id": "product-owner",
        "adjudicator_id": "adjudicator",
    }
    people = []
    for field, role in assignments.items():
        if content.get(field):
            assigned(c, project, content[field], role)
            people.append(content[field])
    owners = set(administrators(c, project)) if content.get("reviewer_ids") else set()
    for user in content.get("reviewer_ids", []):
        # D-SIMPLE: without Reviewers, a Admin grades.
        if str(user) not in owners:
            assigned(c, project, user, "reviewer")
        people.append(user)
    graders = content.get("reviewer_ids", [])
    if len(graders) != len(set(graders)):
        raise HTTPException(409, "Assigned evaluators must be distinct people")
    if content.get("adjudicator_id") in graders:
        raise HTTPException(409, "Adjudication requires a different assigned evaluator")
    return content


def create(c, project, user, kind, content, links=()):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    rid, rev = uid(), uid()
    org = one(c, "SELECT org_id FROM anvil.projects WHERE id=%s", (project,))["org_id"]
    c.execute(
        "INSERT INTO anvil.resources(id,org_id,project_id,kind,created_by) VALUES(%s,%s,%s,%s,%s)",
        (rid, org, project, kind, user),
    )
    c.execute(
        "INSERT INTO anvil.revisions(id,project_id,resource_id,revision,content,content_hash,created_by) VALUES(%s,%s,%s,1,%s,%s,%s)",
        (rev, project, rid, Jsonb(content), digest(content), user),
    )
    c.execute("UPDATE anvil.resources SET current_revision_id=%s WHERE id=%s", (rev, rid))
    for target, relation in links:
        c.execute(
            "INSERT INTO anvil.revision_links VALUES(%s,%s,%s,%s)", (project, rev, target, relation)
        )
    audit(c, project, user, f"{kind}.created", rid, {"content_hash": digest(content)})
    c.execute(
        "INSERT INTO anvil.graph_outbox(project_id,resource_id) VALUES(%s,%s)", (project, rid)
    )
    return get_resource(c, rid)


def revise(c, r, user, content):
    rev = uid()
    c.execute(
        "INSERT INTO anvil.revisions(id,project_id,resource_id,revision,content,content_hash,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (rev, r["project_id"], r["id"], r["revision"] + 1, Jsonb(content), digest(content), user),
    )
    c.execute(
        "INSERT INTO anvil.revision_links VALUES(%s,%s,%s,'supersedes')",
        (r["project_id"], rev, r["current_revision_id"]),
    )
    c.execute(
        "UPDATE anvil.resources SET current_revision_id=%s,lifecycle='draft',row_version=row_version+1 WHERE id=%s",
        (rev, r["id"]),
    )
    for field, relation in [
        ("actor_artifact_ids", "actor"),
        ("reference_artifact_ids", "reference"),
    ]:
        for aid in content.get(field, []):
            c.execute(
                "INSERT INTO anvil.artifact_links VALUES(%s,%s,%s,%s)",
                (r["project_id"], rev, aid, relation),
            )
    c.execute(
        "INSERT INTO anvil.graph_outbox(project_id,resource_id) VALUES(%s,%s)",
        (r["project_id"], r["id"]),
    )
    audit(c, r["project_id"], user, "revision.appended", r["id"], {"content_hash": digest(content)})
    return get_resource(c, r["id"])


def etag(r, expected):
    if expected is None:
        raise HTTPException(428, "If-Match required")
    if expected.strip('"') != str(r["row_version"]):
        raise HTTPException(412, "Revision changed; reload before editing")


def move(c, r, user, state):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (r["project_id"],))
    c.execute(
        "UPDATE anvil.resources SET lifecycle=%s,row_version=row_version+1 WHERE id=%s",
        (state, r["id"]),
    )
    audit(
        c,
        r["project_id"],
        user,
        f"{r['kind']}.{state}",
        r["id"],
        {"content_hash": r["content_hash"]},
    )
    c.execute(
        "INSERT INTO anvil.graph_outbox(project_id,resource_id) VALUES(%s,%s)",
        (r["project_id"], r["id"]),
    )
    return get_resource(c, r["id"])


# D-SIMPLE (AGENTS.md, 1 Oct 2026): the project Admin is the single approver.
APPROVABLE = {"objective", "rubric", "task", "suite", "protocol", "report"}
RECOMMENDATIONS = {
    "research",
    "advisor",
    "scope",
    "content",
    "calibration",
    "technical",
    "domain",
    "audience",
    "release",
}


def administrators(c, project):
    return [
        str(row["user_id"])
        for row in c.execute(
            """SELECT m.user_id FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id
               WHERE m.project_id=%s AND m.role='admin' AND m.active AND u.active""",
            (project,),
        ).fetchall()
    ]


def requirements(r):
    return {"approval": "admin"} if r["kind"] in APPROVABLE else {}


def decide(c, r, user, roles, body):
    if r["lifecycle"] != "submitted":
        raise HTTPException(409, "Only submitted revisions can be reviewed")
    if r["kind"] not in APPROVABLE:
        raise HTTPException(422, "Review purpose not applicable")
    revision_author = get_revision(c, r["current_revision_id"])["created_by"]
    if body.purpose in RECOMMENDATIONS:
        # Optional, non-gating sign-off from another team member; never changes lifecycle.
        require(roles, *CONTENT_ROLES)
        if str(revision_author) == str(user):
            raise HTTPException(409, "A recommendation must come from someone else")
        record_decision(c, r, user, body)
        audit(c, r["project_id"], user, f"recommendation.{body.purpose}.{body.decision}", r["id"])
        c.execute("UPDATE anvil.resources SET row_version=row_version+1 WHERE id=%s", (r["id"],))
        return get_resource(c, r["id"])
    if body.purpose != "approval":
        raise HTTPException(422, "Review purpose not applicable")
    require(roles, "product-owner")
    self_approved = str(revision_author) == str(user)
    if one(
        c,
        "SELECT 1 FROM anvil.review_decisions WHERE revision_id=%s AND purpose='approval' AND reviewer_id=%s",
        (r["current_revision_id"], user),
    ):
        raise HTTPException(409, "This revision already has your decision")
    record_decision(c, r, user, body)
    audit(
        c,
        r["project_id"],
        user,
        f"review.approval.{body.decision}",
        r["id"],
        {"content_hash": r["content_hash"], "self_approved": self_approved},
    )
    if body.decision != "approve":
        return move(c, r, user, "changes_requested")
    return move(c, r, user, "qualified" if r["kind"] == "task" else "approved")


def record_decision(c, r, user, body):
    c.execute(
        "INSERT INTO anvil.review_decisions(id,project_id,revision_id,subject_hash,reviewer_id,purpose,decision,rationale) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            uid(),
            r["project_id"],
            r["current_revision_id"],
            r["content_hash"],
            user,
            body.purpose,
            body.decision,
            body.rationale,
        ),
    )


def rights_ok(c, source, operation="managed_evaluation", destination="local_fixture"):
    return (
        one(
            c,
            """SELECT 1 FROM anvil.rights_grants WHERE source_revision_id=%s AND operation=%s
                    AND destination=%s AND status='approved' AND (expires_at IS NULL OR expires_at>now())""",
            (source, operation, destination),
        )
        is not None
    )


def current_source(c, revision, ready=True):
    source = get_revision(c, revision, "case")
    if source["id"] != source["current_revision_id"] or source["lifecycle"] in (
        "withdrawn",
        "revoked",
    ):
        raise HTTPException(
            409, "Source was superseded or withdrawn; requalify its dependent evidence"
        )
    if ready:
        from anvil.readiness import require_no_declared_gaps

        require_no_declared_gaps(c, revision)
    return source


def qualify(c, r):
    b = r["content"]
    kind = r["kind"]
    links = []
    if kind == "task":
        if b["mode"] == "interactive" and b.get("environment_version") == "MKT-LH-001/1.0":
            from anvil.marketing_pack import verify_task

            verify_task(c, b)
        elif b["mode"] != "static" or b.get("environment_version"):
            raise HTTPException(409, "unsupported_execution_mode")
        source = current_source(c, b["source_revision_id"])
        if source["content"].get("source_origin") != b["origin"]:
            raise HTTPException(
                409,
                "Task origin must preserve its source origin; partner task qualification is not available in this local fixture slice",
            )
        if b["family_id"] != (
            source["content"].get("family_id") or source["content"].get("source_family_key")
        ):
            raise HTTPException(409, "Task family must preserve its source family")
        if source["content"].get("split") == "development" and b["split"] == "protected_test":
            raise HTTPException(409, "Known development fixtures cannot become protected tests")
        get_revision(c, b["rubric_revision_id"], "rubric", ["approved"])
        if not rights_ok(c, b["source_revision_id"]):
            raise HTTPException(409, "Local evaluation rights not reviewed")
        for field, classification in [
            ("actor_artifact_ids", "actor"),
            ("reference_artifact_ids", "hidden_reference"),
        ]:
            for aid in b[field]:
                if not one(
                    c,
                    "SELECT 1 FROM anvil.artifacts a JOIN anvil.artifact_links l ON l.artifact_id=a.id WHERE a.id=%s AND a.classification=%s AND a.scan_status='clean' AND l.revision_id=%s",
                    (aid, classification, b["source_revision_id"]),
                ):
                    raise HTTPException(
                        409, "Required input missing, quarantined or not bound to this source"
                    )
        links = [(b["source_revision_id"], "source"), (b["rubric_revision_id"], "rubric")]
    elif kind == "suite":
        get_revision(c, b["objective_revision_id"], "objective", ["approved"])
        if b.get("benchmark_revision_ids"):
            from anvil.factory import qualify_suite

            qualify_suite(c, b)
            links += [(rid, "benchmark") for rid in b["benchmark_revision_ids"]]
            links.append((b["recommendation_revision_id"], "recommendation"))
        families = {}
        for tid in b["task_revision_ids"]:
            task = get_revision(c, tid, "task", ["published"])["content"]
            current_source(c, task["source_revision_id"])
            if task["family_id"] in families and families[task["family_id"]] != task["split"]:
                raise HTTPException(409, "Related family split conflict")
            families[task["family_id"]] = task["split"]
            links.append((tid, "member"))
        if len(set(b["task_revision_ids"])) != len(b["task_revision_ids"]):
            raise HTTPException(422, "Duplicate task")
        links.append((b["objective_revision_id"], "objective"))
    elif kind == "finding":
        from anvil.artifacts import read

        episode = one(c, "SELECT * FROM anvil.episodes WHERE id=%s", (b["episode_id"],))
        if not episode or episode["state"] != "finalized":
            raise HTTPException(409, "Finding requires a finalized reviewed episode")
        task = get_revision(c, episode["task_revision_id"], "task")
        rubric = get_revision(c, task["content"]["rubric_revision_id"], "rubric")
        if b["criterion"] not in {x["id"] for x in rubric["content"]["criteria"]}:
            raise HTTPException(422, "Finding criterion is not in the bound rubric")
        if b["capability"] not in task["content"]["capabilities"]:
            raise HTTPException(422, "Finding capability is not in the bound task")
        if b["output_quote"] not in read(c, episode["output_artifact_id"]).decode():
            raise HTTPException(422, "Finding requires a verbatim output evidence span")
        links = [(str(task["id"]), "observed_in_task")]
    elif kind == "protocol":
        get_revision(c, b["objective_revision_id"], "objective", ["approved"])
        suite = get_revision(c, b["suite_revision_id"], "suite", ["frozen"])
        if suite["content"]["objective_revision_id"] != b["objective_revision_id"]:
            raise HTTPException(409, "Suite/objective mismatch")
        if len(set(b["candidates"])) != len(b["candidates"]):
            raise HTTPException(422, "Duplicate candidate")
        if b["mode"] == "marketing_interactive_v1":
            from anvil.marketing_pack import verify_protocol

            verify_protocol(c, b, suite["content"])
        links = [(b["objective_revision_id"], "objective"), (b["suite_revision_id"], "suite")]
    for target, relation in links:
        c.execute(
            "INSERT INTO anvil.revision_links VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (r["project_id"], r["current_revision_id"], target, relation),
        )
