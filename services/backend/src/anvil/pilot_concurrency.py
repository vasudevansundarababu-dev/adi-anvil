"""Database-wide pilot ceilings, independent of model/provider and process count."""

import hashlib
import json
import os
import socket
from contextlib import contextmanager
from pathlib import Path

from anvil import pilot_environment
from anvil.db import one, transaction
from anvil.native_process_identity import process_domain


def limit():
    environment = pilot_environment.current()
    if environment not in {None, "qa", "staging"}:
        raise ValueError("pilot_concurrency_environment_required")
    return 2 if environment == "qa" else 1


@contextmanager
def slot(project, actor):
    # Session locks span IO and are automatically released on process/connection
    # loss. Native containers use a separate retained allocation ledger below.
    namespace = "anvil:pilot:sdk:"
    with transaction(project, actor) as c:
        held = None
        for index in range(limit()):
            key = namespace + str(index)
            if one(c, "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) ok", (key,))["ok"]:
                held = key
                break
        if held is None:
            raise RuntimeError("pilot_environment_concurrency_limit")
        try:
            yield
        finally:
            c.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (held,))


def node_identity(folder):
    return hashlib.sha256(
        json.dumps(
            [
                "anvil.native-node.v2",
                socket.gethostname(),
                os.getuid(),
                str(folder.parent.resolve()),
                os.environ["ANVIL_HARBOR_DOCKER_HOST"],
                process_domain(),
            ]
        ).encode()
    ).hexdigest()


def release_native(job, actor, folder):
    with transaction(job["project_id"], actor, worker=True) as c:
        return one(
            c,
            "SELECT anvil.release_native_slot(%s,%s,%s,%s) n",
            (
                job["id"],
                job["lease_token"],
                folder.name,
                node_identity(folder),
            ),
        )["n"]


def recover_native(job, actor, folder):
    from anvil.environment_harbor import recover

    with transaction(job["project_id"], actor, worker=True) as c:
        rows = c.execute(
            "SELECT attempt_key,node_sha256 FROM anvil.pilot_native_allocations WHERE job_id=%s AND released_at IS NULL",
            (job["id"],),
        ).fetchall()
    for row in rows:
        attempt = folder / row["attempt_key"]
        if node_identity(attempt) != row["node_sha256"]:
            raise RuntimeError("native_cleanup_requires_original_node")
        recover(attempt, host=os.environ["ANVIL_HARBOR_DOCKER_HOST"])
        if release_native(job, actor, attempt) != 1:
            raise RuntimeError("native_cleanup_allocation_changed")


@contextmanager
def native_slot(job, actor, folder):
    from anvil.environment_harbor import owned_json

    folder = Path(folder)
    identity = node_identity(folder)
    with transaction(job["project_id"], actor, worker=True) as c:
        one(
            c,
            "SELECT anvil.reserve_native_slot(%s,%s,%s,%s) id",
            (
                job["id"],
                job["lease_token"],
                folder.name,
                identity,
            ),
        )
    try:
        yield
    finally:
        # A lost receipt/failed cleanup retains capacity even after process death.
        # A fresh lease can reconcile only on the original node and exact paths.
        if (
            folder.is_dir()
            and (folder / "cleanup.json").is_file()
            and owned_json(folder, "cleanup.json").get("complete") is True
        ):
            if release_native(job, actor, folder) != 1:
                raise RuntimeError("native_cleanup_allocation_changed")
