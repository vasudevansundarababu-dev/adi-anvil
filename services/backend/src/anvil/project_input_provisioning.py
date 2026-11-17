"""Atomic actor-data population by the existing scheduler; no new authored tasks.

Uploaded documents are not screening services or independently verified facts.
Private answers/approvals are never manufactured from an uploaded application.
"""

import os

from anvil.db import Jsonb, digest, uid
from anvil.golden_kyc_data import VERSION
from anvil.golden_kyc_policy import library
from anvil.project_input_contract import INPUT


def populate(c, row):
    content = INPUT.validate_python(row["content"]).model_dump(mode="json")
    if digest(content) != row["content_sha256"]:
        raise ValueError("Immutable structured input integrity changed")
    pack = None
    if row["family"] == "kyc":
        applications = content["applications"]
        pack = uid()
        manifest = {
            "version": VERSION,
            "seed": None,
            "origin": "user_supplied_actor_input_unreviewed",
            "input_id": str(row["id"]),
            "input_sha256": row["content_sha256"],
            "application_count": len(applications),
            "public_sha256": digest(applications),
            "policy_sha256": digest(library()),
            "expectation_review": "not_supplied",
            "data_rights": "requires_existing_run_rights_review",
            "paid_calls": False,
            "model_performance": False,
        }
        c.execute(
            "INSERT INTO banking.packs(id,project_id,manifest,created_by) VALUES(%s,%s,%s,%s)",
            (pack, row["project_id"], Jsonb(manifest), row["created_by"]),
        )
        for app in applications:
            c.execute(
                "INSERT INTO banking.applications VALUES(%s,%s,%s,%s,%s)",
                (app["id"], row["project_id"], pack, Jsonb(app), digest(app)),
            )
            controls = {
                "pattern": "uploaded_unreviewed",
                "tags": {"api_disturbance": None, "safety_exposure": None},
                "response_mode": "none",
                "future_documents": [],
                "snapshot_sha256": digest(app),
            }
            c.execute(
                "INSERT INTO banking_private.scenarios VALUES(%s,%s,%s,%s)",
                (row["project_id"], pack, app["id"], Jsonb(controls)),
            )
        cases = [
            {"id": a["id"], "snapshot_sha256": digest(a), "governing_state": a["governing_state"]}
            for a in applications
        ]
    else:
        cases = [
            {"id": a["id"], "snapshot_sha256": digest(a), "locale": a["locale"]}
            for a in content["cases"]
        ]
    result = {
        "schema_version": "anvil.populated-project-input.v1",
        "input_id": str(row["id"]),
        "content_sha256": row["content_sha256"],
        "family": row["family"],
        "pack_id": str(pack) if pack else None,
        "case_count": len(cases),
        "cases": sorted(cases, key=lambda case: case["id"]),
        "qualification": "not_runtime_or_reference_qualified",
        "private_expectations": "not_supplied",
    }
    c.execute(
        "INSERT INTO anvil.project_data_provisions(input_id,project_id,pack_id,manifest,manifest_sha256) VALUES(%s,%s,%s,%s,%s)",
        (row["id"], row["project_id"], pack, Jsonb(result), digest(result)),
    )
    c.execute(
        "UPDATE anvil.project_data_input_jobs SET state='completed' WHERE input_id=%s AND state='queued'",
        (row["id"],),
    )
    return result


def scheduler_once(connections):
    if os.environ.get("ANVIL_PROJECT_INPUTS_ENABLED") != "true":
        return None
    with connections() as c:
        job = c.execute(
            "SELECT input_id FROM anvil.project_data_input_jobs WHERE state='queued' ORDER BY created_at,input_id FOR UPDATE SKIP LOCKED LIMIT 1"
        ).fetchone()
        if not job:
            return None
        row = c.execute(
            "SELECT * FROM anvil.project_data_inputs WHERE id=%s", (job["input_id"],)
        ).fetchone()
        if row is None:
            raise ValueError("Input job has no scoped immutable input")
        return populate(c, row)
