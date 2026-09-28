"""Rebuildable Neo4j metadata projection; canonical records control visibility."""

from uuid import UUID, uuid5

from fastapi import APIRouter, HTTPException, Request
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable, SessionExpired

from anvil import auth
from anvil.config import setting
from anvil.db import audit, digest, one, transaction

router = APIRouter(prefix="/api/v1/projects/{project}")
PROJECTION_VERSION = "evidence-v2"


def driver():
    return GraphDatabase.driver(
        setting("NEO4J_URI"),
        auth=("neo4j", setting("ANVIL_NEO4J_PASSWORD")),
        connection_timeout=2,
        connection_acquisition_timeout=2,
        max_transaction_retry_time=0,
    )


def canonical(c):
    records = c.execute("""SELECT r.id,r.project_id,r.kind,r.lifecycle,v.id revision_id,v.content_hash,v.content
                          FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id
                          WHERE r.kind IN ('objective','case','task','suite','protocol','finding','report')
                          AND r.lifecycle NOT IN ('withdrawn','revoked') ORDER BY r.id LIMIT 201""").fetchall()
    nodes = [
        {
            "id": str(r["revision_id"]),
            "resource_id": str(r["id"]),
            "kind": r["kind"],
            "label": r["content"].get("title", r["kind"]),
            "status": r["lifecycle"],
            "hash": r["content_hash"],
        }
        for r in records[:200]
    ]
    ids = {n["id"] for n in nodes}
    linked = c.execute(
        "SELECT * FROM anvil.revision_links WHERE revision_id=ANY(%s::uuid[]) AND target_revision_id=ANY(%s::uuid[]) ORDER BY revision_id,target_revision_id,relation LIMIT 501",
        (list(ids), list(ids)),
    ).fetchall()
    edges = [
        {
            "source": str(x["revision_id"]),
            "target": str(x["target_revision_id"]),
            "relation": x["relation"],
        }
        for x in linked[:500]
    ]
    truncated = len(records) > 200 or len(linked) > 500

    def add_node(node):
        nonlocal truncated
        if node["id"] in ids:
            return True
        if len(nodes) >= 200:
            truncated = True
            return False
        nodes.append(node)
        ids.add(node["id"])
        return True

    def add_edge(source, target, relation):
        nonlocal truncated
        edge = {"source": str(source), "target": str(target), "relation": relation}
        if edge in edges or edge["source"] not in ids or edge["target"] not in ids:
            return
        if len(edges) >= 500:
            truncated = True
        else:
            edges.append(edge)

    for record in records[:200]:
        content = record["content"]
        family = content.get("family_id") or content.get("source_family_key")
        concepts = [("case_family", str(family), "member_of_family")] if family else []
        if record["kind"] == "task":
            concepts += [
                ("capability", str(capability), "measures")
                for capability in content.get("capabilities", [])
            ]
        for kind, label, relation in concepts:
            nid = str(uuid5(record["project_id"], kind + ":" + label))
            node = {
                "id": nid,
                "resource_id": None,
                "kind": kind,
                "label": label,
                "status": "declared_mapping",
                "hash": digest({"kind": kind, "label": label}),
            }
            if add_node(node):
                add_edge(record["revision_id"], nid, relation)
    task_ids = [str(r["revision_id"]) for r in records[:200] if r["kind"] == "task"]
    episodes = c.execute(
        """SELECT e.id,e.task_revision_id,e.state,e.outcome,e.score,r.origin
        FROM anvil.episodes e JOIN anvil.runs r ON r.id=e.run_id
        WHERE e.task_revision_id=ANY(%s::uuid[]) ORDER BY e.id LIMIT 201""",
        (task_ids,),
    ).fetchall()
    if len(episodes) > 200:
        truncated = True
    for episode in episodes[:200]:
        metadata = {
            "state": episode["state"],
            "outcome": episode["outcome"]
            if episode["state"] in ("finalized", "failed_operational")
            else "not_finalized",
            "score": float(episode["score"])
            if episode["state"] == "finalized" and episode["score"] is not None
            else None,
            "origin": episode["origin"],
        }
        if add_node(
            {
                "id": str(episode["id"]),
                "resource_id": None,
                "kind": "episode",
                "label": "Episode "
                + str(episode["id"])[:8]
                + " · "
                + episode["origin"].replace("_", " "),
                "status": episode["state"],
                "hash": digest(metadata),
            }
        ):
            add_edge(episode["id"], episode["task_revision_id"], "evaluates")
    for record in records[:200]:
        if record["kind"] == "finding":
            add_edge(record["revision_id"], record["content"].get("episode_id"), "observes")
    return {"nodes": nodes, "edges": edges, "truncated": truncated}


def ensure_schema(session):
    session.run(
        "CREATE CONSTRAINT anvil_project_identity IF NOT EXISTS FOR (p:AnvilProject) REQUIRE p.id IS UNIQUE"
    ).consume()
    session.run(
        "CREATE CONSTRAINT anvil_record_identity IF NOT EXISTS FOR (v:AnvilRecord) REQUIRE (v.project,v.id,v.generation) IS UNIQUE"
    ).consume()


def write_snapshot(tx, project, snapshot, watermark):
    # Take the Neo4j node write lock before testing the watermark. An older
    # transaction arriving after a newer one may not rewind the cache generation.
    accepted = tx.run(
        "MERGE (p:AnvilProject {id:$p}) ON CREATE SET p.watermark=-1 "
        "SET p.write_lock=coalesce(p.write_lock,0)+1 WITH p WHERE p.watermark <= $w "
        "SET p.watermark=$w RETURN p.watermark AS watermark",
        p=str(project),
        w=watermark,
    ).single()
    if accepted is None:
        return False
    tx.run(
        "UNWIND $nodes AS n MERGE (v:AnvilRecord {project:$p,id:n.id,generation:$w}) "
        "SET v.resource_id=n.resource_id,v.kind=n.kind,v.label=n.label,v.status=n.status,v.hash=n.hash",
        p=str(project),
        w=watermark,
        nodes=snapshot["nodes"],
    ).consume()
    tx.run(
        "UNWIND $edges AS e MATCH (a:AnvilRecord {project:$p,id:e.source,generation:$w}) "
        "MATCH (b:AnvilRecord {project:$p,id:e.target,generation:$w}) "
        "MERGE (a)-[:ANVIL_RELATION {kind:e.relation}]->(b)",
        p=str(project),
        w=watermark,
        edges=snapshot["edges"],
    ).consume()
    # Only disposable cache generations are removed; PostgreSQL owns all history.
    tx.run(
        "MATCH (v:AnvilRecord {project:$p}) WHERE v.generation <> $w DETACH DELETE v",
        p=str(project),
        w=watermark,
    ).consume()
    return True


def project_graph(project):
    with transaction(project, worker=True) as c:
        c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
        snapshot = canonical(c)
        watermark = one(c, "SELECT coalesce(max(id),0) n FROM anvil.graph_outbox")["n"]
        with driver() as d, d.session() as s:
            ensure_schema(s)
            if not s.execute_write(lambda tx: write_snapshot(tx, project, snapshot, watermark)):
                raise ServiceUnavailable("Projection watermark is ahead of this canonical snapshot")
        c.execute("UPDATE anvil.graph_outbox SET status='done' WHERE id<=%s", (watermark,))
        c.execute(
            "INSERT INTO anvil.graph_projection_state(project_id,last_event,status,last_success_at,projection_version) VALUES(%s,%s,'current',now(),%s) ON CONFLICT(project_id) DO UPDATE SET last_event=excluded.last_event,status='current',last_success_at=now(),projection_version=excluded.projection_version",
            (project, watermark, PROJECTION_VERSION),
        )
    return snapshot


def project_pending():
    # Queue discovery is narrow; project execution still uses scoped worker transactions.
    with transaction(worker=True) as c:
        projects = c.execute("SELECT id FROM anvil.projects ORDER BY id").fetchall()
    for p in projects:
        with transaction(p["id"], worker=True) as c:
            pending = one(
                c, "SELECT 1 FROM anvil.graph_outbox WHERE status='pending' LIMIT 1"
            ) or one(
                c,
                "SELECT 1 FROM anvil.graph_projection_state WHERE projection_version<>%s",
                (PROJECTION_VERSION,),
            )
        if pending:
            try:
                project_graph(p["id"])
            except (Neo4jError, ServiceUnavailable, SessionExpired, OSError):
                return False
            return True
    return False


def routes(context, wrap):
    @router.get("/diagnostics")
    @router.get("/graph")
    def read_graph(project: UUID, request: Request, depth: int = 2, root: UUID | None = None):
        if not 1 <= depth <= 3:
            raise HTTPException(422, "Graph depth must be 1..3")
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "advisor")
            data = canonical(c)
            state = one(c, "SELECT * FROM anvil.graph_projection_state")
            watermark = one(c, "SELECT coalesce(max(id),0) n FROM anvil.graph_outbox")["n"]
            data.update(
                {
                    "projection_status": "unavailable",
                    "canonical_sequence": watermark,
                    "as_of_sequence": state["last_event"] if state else 0,
                    "source": "PostgreSQL fallback",
                }
            )
            try:
                with driver() as d, d.session() as s:
                    records = s.run(
                        "MATCH (p:AnvilProject {id:$p}) MATCH (v:AnvilRecord {project:$p,generation:p.watermark}) RETURN v.id AS id,v.hash AS hash LIMIT 200",
                        p=str(project),
                    ).data()
                    projected_edges = s.run(
                        "MATCH (p:AnvilProject {id:$p}) MATCH (a:AnvilRecord {project:$p,generation:p.watermark})-[r:ANVIL_RELATION]->(b:AnvilRecord {project:$p,generation:p.watermark}) RETURN a.id AS source,b.id AS target,r.kind AS relation LIMIT 500",
                        p=str(project),
                    ).data()
                permitted = {n["id"]: n["hash"] for n in data["nodes"]}
                actual = {r["id"]: r["hash"] for r in records if r["id"] in permitted}
                canonical_edges = {(e["source"], e["target"], e["relation"]) for e in data["edges"]}
                actual_edges = {
                    (e["source"], e["target"], e["relation"])
                    for e in projected_edges
                    if e["source"] in permitted and e["target"] in permitted
                }
                current = (
                    actual == permitted
                    and actual_edges == canonical_edges
                    and state
                    and state["projection_version"] == PROJECTION_VERSION
                    and state["last_event"] == watermark
                )
                data["projection_status"] = "current" if current else "lagging"
                data["source"] = (
                    "Neo4j projection verified against PostgreSQL"
                    if current
                    else "PostgreSQL fallback"
                )
            except (Neo4jError, ServiceUnavailable, SessionExpired, OSError):
                pass
            if root is not None:
                root_id = str(root)
                if root_id not in {n["id"] for n in data["nodes"]}:
                    raise HTTPException(404, "Graph root not found in permitted bounded snapshot")
                visited, frontier = {root_id}, {root_id}
                for _ in range(depth):
                    adjacent = {e["target"] for e in data["edges"] if e["source"] in frontier}
                    adjacent |= {e["source"] for e in data["edges"] if e["target"] in frontier}
                    frontier = adjacent - visited
                    visited |= frontier
                data["nodes"] = [n for n in data["nodes"] if n["id"] in visited]
                data["edges"] = [
                    e for e in data["edges"] if e["source"] in visited and e["target"] in visited
                ]
                data["root"] = root_id
                data["depth"] = depth
            return wrap(data, request)

    @router.post("/graph/rebuild")
    def rebuild(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            audit(c, project, user, "graph.rebuild_requested")
        return wrap(project_graph(project), request)

    return router
