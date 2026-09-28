"""Rebuildable Neo4j metadata projection; canonical records control visibility."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable, SessionExpired

from anvil import auth
from anvil.config import setting
from anvil.db import audit, one, transaction

router = APIRouter(prefix="/api/v1/projects/{project}")


def driver():
    return GraphDatabase.driver(
        setting("NEO4J_URI"),
        auth=("neo4j", setting("ANVIL_NEO4J_PASSWORD")),
        connection_timeout=2,
        connection_acquisition_timeout=2,
        max_transaction_retry_time=0,
    )


def canonical(c):
    records = c.execute("""SELECT r.id,r.kind,r.lifecycle,v.id revision_id,v.content_hash,v.content
                          FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id
                          WHERE r.kind IN ('objective','case','task','suite','protocol','finding','report')
                          AND r.lifecycle NOT IN ('withdrawn','revoked') ORDER BY r.id LIMIT 200""").fetchall()
    nodes = [
        {
            "id": str(r["revision_id"]),
            "resource_id": str(r["id"]),
            "kind": r["kind"],
            "label": r["content"].get("title", r["kind"]),
            "status": r["lifecycle"],
            "hash": r["content_hash"],
        }
        for r in records
    ]
    ids = {n["id"] for n in nodes}
    edges = [
        {
            "source": str(x["revision_id"]),
            "target": str(x["target_revision_id"]),
            "relation": x["relation"],
        }
        for x in c.execute(
            "SELECT * FROM anvil.revision_links ORDER BY revision_id LIMIT 500"
        ).fetchall()
        if str(x["revision_id"]) in ids and str(x["target_revision_id"]) in ids
    ]
    return {"nodes": nodes, "edges": edges, "truncated": len(nodes) == 200 or len(edges) == 500}


def project_graph(project):
    with transaction(project, worker=True) as c:
        c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
        snapshot = canonical(c)
        watermark = one(c, "SELECT coalesce(max(id),0) n FROM anvil.graph_outbox")["n"]
        with driver() as d, d.session() as s:

            def write(tx):
                tx.run(
                    "MERGE (p:AnvilProject {id:$p}) SET p.watermark=$w", p=str(project), w=watermark
                ).consume()
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

            s.execute_write(write)
        c.execute("UPDATE anvil.graph_outbox SET status='done' WHERE id<=%s", (watermark,))
        c.execute(
            "INSERT INTO anvil.graph_projection_state(project_id,last_event,status,last_success_at) VALUES(%s,%s,'current',now()) ON CONFLICT(project_id) DO UPDATE SET last_event=excluded.last_event,status='current',last_success_at=now()",
            (project, watermark),
        )
    return snapshot


def project_pending():
    # Queue discovery is narrow; project execution still uses scoped worker transactions.
    with transaction(worker=True) as c:
        projects = c.execute("SELECT id FROM anvil.projects ORDER BY id").fetchall()
    for p in projects:
        with transaction(p["id"], worker=True) as c:
            pending = one(c, "SELECT 1 FROM anvil.graph_outbox WHERE status='pending' LIMIT 1")
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
