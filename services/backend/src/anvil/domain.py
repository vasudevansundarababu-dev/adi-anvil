from fastapi import HTTPException
from psycopg.types.json import Jsonb

from anvil.auth import require
from anvil.db import audit, digest, one, uid
from anvil.schemas import SCHEMAS

CONTENT_ROLES = (
    "researcher",
    "advisor",
    "data-engineer",
    "reviewer",
    "adjudicator",
    "product-owner",
)


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
        "SELECT 1 FROM anvil.memberships WHERE project_id=%s AND user_id=%s AND role=%s AND active",
        (project, user, role),
    ):
        raise HTTPException(422, f"Assigned {role} is not an active project member")


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
        if field in content:
            assigned(c, project, content[field], role)
            people.append(content[field])
    for user in content.get("reviewer_ids", []):
        assigned(c, project, user, "reviewer")
        people.append(user)
    if len(people) != len(set(people)):
        raise HTTPException(409, "Separated assignments require distinct people")
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


def requirements(r):
    return {
        "objective": {
            "research": ("researcher_id", "researcher"),
            "advisor": ("advisor_id", "advisor"),
            "scope": ("product_owner_id", "product-owner"),
        },
        "rubric": {
            "content": ("reviewer_id", "reviewer"),
            "calibration": ("advisor_id", "advisor"),
        },
        "task": {"content": ("reviewer_id", "reviewer"), "research": ("advisor_id", "advisor")},
        "suite": {"technical": ("advisor_id", "advisor")},
        "protocol": {"technical": ("advisor_id", "advisor")},
        "finding": {"technical": ("advisor_id", "advisor")},
        "report": {
            "technical": ("advisor_id", "advisor"),
            "domain": ("reviewer_id", "reviewer"),
            "audience": ("product_owner_id", "product-owner"),
            "release": ("product_owner_id", "product-owner"),
        },
    }.get(r["kind"], {})


def decide(c, r, user, roles, body):
    if r["lifecycle"] != "submitted":
        raise HTTPException(409, "Only submitted revisions can be reviewed")
    req = requirements(r)
    purpose = body.purpose
    if purpose not in req:
        raise HTTPException(422, "Review purpose not applicable")
    field, role = req[purpose]
    require(roles, role)
    if r["content"][field] != str(user):
        raise HTTPException(403, "Review is assigned to another identity")
    if str(r["created_by"]) == str(user) and not (
        r["kind"] == "objective" and purpose == "research"
    ):
        raise HTTPException(409, "Independent review required")
    prior = c.execute(
        "SELECT * FROM anvil.review_decisions WHERE revision_id=%s", (r["current_revision_id"],)
    ).fetchall()
    approved = {d["purpose"] for d in prior if d["decision"] == "approve"}
    if purpose == "scope" and not {"research", "advisor"} <= approved:
        raise HTTPException(409, "Both recommendations required")
    if purpose == "release" and not {"technical", "domain", "audience"} <= approved:
        raise HTTPException(409, "Scientific and audience reviews required")
    if purpose != "release" and any(str(d["reviewer_id"]) == str(user) for d in prior):
        raise HTTPException(409, "One person cannot fill separated review positions")
    c.execute(
        "INSERT INTO anvil.review_decisions(id,project_id,revision_id,subject_hash,reviewer_id,purpose,decision,rationale) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            uid(),
            r["project_id"],
            r["current_revision_id"],
            r["content_hash"],
            user,
            purpose,
            body.decision,
            body.rationale,
        ),
    )
    audit(c, r["project_id"], user, f"review.{purpose}.{body.decision}", r["id"])
    if body.decision != "approve":
        return move(c, r, user, "changes_requested")
    approved.add(purpose)
    if set(req) <= approved:
        return move(c, r, user, "qualified" if r["kind"] == "task" else "approved")
    c.execute("UPDATE anvil.resources SET row_version=row_version+1 WHERE id=%s", (r["id"],))
    return get_resource(c, r["id"])


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


def qualify(c, r):
    b = r["content"]
    kind = r["kind"]
    links = []
    if kind == "task":
        if b["mode"] != "static":
            raise HTTPException(409, "unsupported_execution_mode")
        get_revision(c, b["source_revision_id"], "case")
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
        families = {}
        for tid in b["task_revision_ids"]:
            task = get_revision(c, tid, "task", ["published"])["content"]
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
        links = [(b["objective_revision_id"], "objective"), (b["suite_revision_id"], "suite")]
    for target, relation in links:
        c.execute(
            "INSERT INTO anvil.revision_links VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (r["project_id"], r["current_revision_id"], target, relation),
        )
