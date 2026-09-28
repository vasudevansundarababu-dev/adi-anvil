"""Bounded local file adapter for the shared durable job queue.

Other source types require separately qualified adapters, not generic URL fetching.
Raw sources are opened only in the submitting active author's scoped app transaction;
the candidate worker DB role cannot query imports or reference answers.
"""

from fastapi import HTTPException
from psycopg import OperationalError

from anvil import auth
from anvil.db import Jsonb, audit, digest, one, transaction, uid

CHUNK_ROWS = 200
SUPPORTED_CONNECTORS = {"csv": "task-text-v1", "jsonl": "task-text-v1"}


def retry_transient(c, job, exc):
    if not isinstance(exc, (OperationalError, OSError)) or job["attempts"] >= 3:
        return False
    # Reuse the queue's lease-expiry scheduling: 2s then 4s, at most three attempts.
    changed = c.execute(
        "UPDATE anvil.jobs SET lease_until=now()+make_interval(secs=>%s),error_code='ingestion_transient_retry' WHERE id=%s AND status='leased' AND lease_token=%s AND lease_until>now() RETURNING id",
        (2 ** job["attempts"], job["id"], job["lease_token"]),
    ).fetchone()
    if not changed:
        return False
    c.execute(
        "UPDATE anvil.ingestion_jobs SET state='queued',error_code='ingestion_transient_retry' WHERE id=%s",
        (job["target_id"],),
    )
    audit(
        c,
        job["project_id"],
        None,
        "ingestion.retry_scheduled",
        job["target_id"],
        {"attempt": job["attempts"]},
    )
    return True


def enqueue(c, project, user, iid, revision):
    count = one(
        c,
        "SELECT count(*) n FROM anvil.ingestion_jobs WHERE state IN ('queued','extracting','validating')",
    )["n"]
    if count >= 10:
        raise HTTPException(
            409,
            "Workspace ingestion quota: finish or cancel a job before starting another (maximum 10)",
        )
    jid = uid()
    c.execute(
        "INSERT INTO anvil.ingestion_jobs(id,project_id,import_id,created_by,import_revision) VALUES(%s,%s,%s,%s,%s)",
        (jid, project, iid, user, revision),
    )
    c.execute(
        "INSERT INTO anvil.jobs(id,project_id,kind,target_id,operation_key) VALUES(%s,%s,'task_ingestion',%s,%s)",
        (uid(), project, jid, "task-ingestion:" + jid),
    )
    audit(c, project, user, "ingestion.created", jid, {"import_revision": revision})
    return jid


def process(job):
    from anvil.task_imports import validate_source

    with transaction(job["project_id"], worker=True) as c:
        owner = one(
            c, "SELECT created_by FROM anvil.ingestion_jobs WHERE id=%s", (job["target_id"],)
        )
    if not owner:
        raise RuntimeError("ingestion_missing")
    with transaction(job["project_id"], owner["created_by"]) as c:
        auth.require(
            auth.project_roles(c, job["project_id"], owner["created_by"]),
            "researcher",
            "data-engineer",
        )
        # Match command lock order, avoiding cancellation/project-FK lock inversion.
        c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (job["project_id"],))
        if not one(
            c,
            "SELECT 1 FROM anvil.jobs WHERE id=%s AND status='leased' AND lease_token=%s AND lease_until>now() FOR UPDATE",
            (job["id"], job["lease_token"]),
        ):
            raise RuntimeError("lease_lost")
        ingestion = one(
            c, "SELECT * FROM anvil.ingestion_jobs WHERE id=%s FOR UPDATE", (job["target_id"],)
        )
        item = one(
            c, "SELECT * FROM anvil.task_imports WHERE id=%s FOR UPDATE", (ingestion["import_id"],)
        )
        if (
            ingestion["state"] in ("cancelled", "ready", "invalid")
            or item["revision"] != ingestion["import_revision"]
        ):
            c.execute("UPDATE anvil.jobs SET status='cancelled' WHERE id=%s", (job["id"],))
            return
        if ingestion["started_at"] is None:
            audit(c, job["project_id"], owner["created_by"], "ingestion.started", ingestion["id"])
        source, result = validate_source(c, item["source_artifact_id"], item["mapping"])
        rows = result.pop("normalized")
        checksum = result.pop("normalized_sha256")
        start = ingestion["checkpoint"]
        chunk = rows[start : start + CHUNK_ROWS]
        end = start + len(chunk)
        c.execute(
            "INSERT INTO anvil.ingestion_chunks VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (job["project_id"], ingestion["id"], start, len(chunk), digest(chunk)),
        )
        complete = end >= len(rows)
        state = ("invalid" if result["errors"] else "ready") if complete else "extracting"
        c.execute(
            """UPDATE anvil.ingestion_jobs SET state=%s,checkpoint=%s,records_total=%s,bytes_processed=%s,
            started_at=coalesce(started_at,now()),finished_at=CASE WHEN %s THEN now() ELSE NULL END,error_code=NULL WHERE id=%s""",
            (
                state,
                end,
                len(rows),
                source["byte_size"] if complete else source["byte_size"] * end // max(1, len(rows)),
                complete,
                ingestion["id"],
            ),
        )
        # Chunk receipts and logical checkpoint commit together. The final canonical normalized
        # materialization is atomic; repeated chunks can never publish or duplicate tasks.
        if complete:
            c.execute(
                "UPDATE anvil.task_imports SET status=%s,normalized=%s,validation=%s,normalized_sha256=%s WHERE id=%s",
                (state, Jsonb(rows), Jsonb(result), checksum, item["id"]),
            )
            audit(
                c,
                job["project_id"],
                owner["created_by"],
                "task_import.validated",
                item["id"],
                result["counts"],
            )
            audit(
                c,
                job["project_id"],
                owner["created_by"],
                "ingestion.completed",
                ingestion["id"],
                {"records": end, "valid": result["counts"]["valid"]},
            )
        else:
            c.execute(
                "UPDATE anvil.task_imports SET status='extracting' WHERE id=%s", (item["id"],)
            )
        updated = c.execute(
            "UPDATE anvil.jobs SET status=%s,attempts=0 WHERE id=%s AND lease_token=%s AND lease_until>now() RETURNING id",
            ("succeeded" if complete else "queued", job["id"], job["lease_token"]),
        ).fetchone()
        if not updated:
            raise RuntimeError("lease_lost")
