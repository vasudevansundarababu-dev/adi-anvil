"""Rebuild restored canonical evidence into a separate retained Neo4j test namespace."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from anvil import graph
from anvil.cli import PROJECT
from anvil.config import ROOT, setting
from anvil.db import digest, transaction

folder = Path((ROOT / ".local/latest-backup").read_text())
assert folder.resolve().is_relative_to((ROOT / ".local/backups").resolve())
verification = json.loads((folder / "restore-verification.json").read_text())
target = verification["target_database"]
assert target.startswith("anvil_restore_")
user = json.loads((ROOT / ".local/demo-identities.json").read_text())["researcher"]
project = PROJECT
namespace = target + ":" + project
original_driver = graph.driver


class TransactionProxy:
    def __init__(self, tx):
        self.tx = tx

    def run(self, query, **parameters):
        assert parameters["p"] == project
        return self.tx.run(query, **{**parameters, "p": namespace})


class SessionProxy:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.session.close()

    def execute_write(self, operation):
        return self.session.execute_write(lambda tx: operation(TransactionProxy(tx)))

    def run(self, query, **parameters):
        assert query.startswith("CREATE CONSTRAINT")
        return self.session.run(query, **parameters)


class DriverProxy:
    def __init__(self):
        self.driver = original_driver()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.driver.close()

    def session(self):
        return SessionProxy(self.driver.session())


saved = {key: setting(key) for key in ("DATABASE_URL", "WORKER_DATABASE_URL")}
with transaction(project, user) as c:
    live_before = digest(graph.canonical(c))
try:
    for key, value in saved.items():
        os.environ[key] = urlsplit(value)._replace(path="/" + target).geturl()
    graph.driver = DriverProxy
    expected = graph.project_graph(project)
    graph.driver = original_driver
    with original_driver() as driver, driver.session() as session:
        nodes = session.run(
            "MATCH (n:AnvilRecord {project:$p}) RETURN n.id AS id,n.hash AS hash", p=namespace
        ).data()
        edges = session.run(
            "MATCH (a:AnvilRecord {project:$p})-[r:ANVIL_RELATION]->(b:AnvilRecord {project:$p}) RETURN a.id AS source,b.id AS target,r.kind AS relation",
            p=namespace,
        ).data()
    assert {n["id"]: n["hash"] for n in nodes} == {n["id"]: n["hash"] for n in expected["nodes"]}
    assert {tuple(e[k] for k in ("source", "target", "relation")) for e in edges} == {
        tuple(e[k] for k in ("source", "target", "relation")) for e in expected["edges"]
    }
finally:
    graph.driver = original_driver
    os.environ.update(saved)
with transaction(project, user) as c:
    assert digest(graph.canonical(c)) == live_before
result = {
    "status": "passed",
    "target_database": target,
    "isolated_neo4j_namespace": namespace,
    "nodes": len(nodes),
    "edges": len(edges),
    "canonical_hashes_match": True,
    "live_canonical_evidence_unchanged": True,
}
(folder / "restore-graph-verification.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result))
