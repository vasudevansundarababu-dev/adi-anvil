"""Import reported executions without dispatching a candidate or inventing evidence."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, model_validator

from anvil import artifacts, auth, domain
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.evaluation import EXTERNAL_GRAPH_VERSION, enqueue, get_run
from anvil.intake import Commit
from anvil.schemas import Strict


class CandidateDescriptor(Strict):
    model_requested: str | None = Field(max_length=300)
    model_returned: str | None = Field(max_length=300)
    harness_version: str | None = Field(max_length=300)
    graph_version: str | None = Field(max_length=300)
    tools: list[str] | None
    parameters: dict | None


class Attempt(Strict):
    task_revision_id: UUID
    repetition: Literal[1]
    attempt: Literal[1]
    execution_state: Literal["completed", "failed_operational", "execution_unknown"]
    output_artifact_id: UUID | None = None
    trace_artifact_id: UUID | None = None
    trace_coverage: Literal["none", "partial", "producer_claimed_complete"] = "none"
    usage: dict | None = None
    reported_cost_micro_usd: int | None = Field(default=None, ge=0, strict=True)
    source_score: float | None = Field(default=None, allow_inf_nan=False)
    source_rubric_version: str | None = Field(default=None, max_length=300)
    limitations: list[str] = Field(max_length=30)

    @model_validator(mode="after")
    def coverage(self):
        if bool(self.trace_artifact_id) != (self.trace_coverage != "none"):
            raise ValueError("Trace coverage must describe only a supplied trace")
        if self.source_score is not None and not self.source_rubric_version:
            raise ValueError("Reported score requires its reported rubric version")
        return self


class Manifest(Strict):
    schema_version: Literal["anvil.external_results.v1"]
    run_id: UUID
    origin: Literal["customer_reported", "partner_reported"]
    producer: str = Field(min_length=1, max_length=300)
    executed_at: datetime
    protocol_hash: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    producer_manifest_hash: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    incomparability_reasons: list[str] = Field(max_length=30)
    candidate_descriptor: CandidateDescriptor
    attempts: list[Attempt] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def provenance(self):
        if self.executed_at.utcoffset() is None:
            raise ValueError("Execution date requires a timezone")
        if self.protocol_hash is None and not any(x.strip() for x in self.incomparability_reasons):
            raise ValueError("Unknown protocol requires explicit incomparability reasons")
        return self


def validate(c, manifest):
    errors = []
    run = get_run(c, manifest["run_id"])
    if run.get("dataset_version_id"):
        raise HTTPException(
            409, "Dataset-bound runs require a qualified imported-task execution binding"
        )
    protocol = domain.get_revision(c, run["protocol_revision_id"], "protocol", ["approved"])
    suite = domain.get_revision(c, protocol["content"]["suite_revision_id"], "suite", ["frozen"])
    domain.get_revision(c, protocol["content"]["objective_revision_id"], "objective", ["approved"])
    if (
        protocol["content"]["mode"] != "external_result_import_v1"
        or run["origin"] != manifest["origin"]
    ):
        errors.append({"code": "execution_origin_mismatch"})
    if run["state"] != "draft" or run["cancel_requested"]:
        errors.append({"code": "run_not_open_for_import"})
    if manifest["protocol_hash"] and manifest["protocol_hash"] != protocol["content_hash"]:
        errors.append({"code": "protocol_hash_mismatch"})
    seen = set()
    for index, attempt in enumerate(manifest["attempts"]):
        tid = attempt["task_revision_id"]
        if tid in seen:
            errors.append({"row": index, "code": "duplicate_attempt"})
        seen.add(tid)
        if tid not in suite["content"]["task_revision_ids"]:
            errors.append({"row": index, "code": "task_not_in_frozen_suite"})
            continue
        try:
            task = domain.get_revision(c, tid, "task", ["published"])["content"]
            domain.current_source(c, task["source_revision_id"])
            # This local import path cannot authorize a new data destination or exposure.
            if task["split"] == "protected_test" or not domain.rights_ok(
                c, task["source_revision_id"]
            ):
                errors.append({"row": index, "code": "rights_or_exposure_blocked"})
            for field in ("output_artifact_id", "trace_artifact_id"):
                aid = attempt[field]
                if not aid:
                    continue
                a = one(c, "SELECT * FROM anvil.artifacts WHERE id=%s", (aid,))
                if not a or a["classification"] != "internal" or a["origin"] != manifest["origin"]:
                    raise HTTPException(409, "External evidence classification/origin mismatch")
                data = artifacts.read(c, aid)
                if field == "output_artifact_id":
                    if (
                        a["mime_type"] not in ("text/plain", "application/json")
                        or len(data) > 1024 * 1024
                    ):
                        raise HTTPException(409, "Unsupported external output")
                    data.decode("utf-8")
        except (HTTPException, OSError, UnicodeError):
            errors.append({"row": index, "code": "evidence_unavailable_or_unqualified"})
    return errors


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}")

    @router.post("/runs/{rid}/external-results/validate")
    def preview(project: UUID, rid: UUID, body: Manifest, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "data-engineer")
            if rid != body.run_id:
                raise HTTPException(422, "Manifest run must match the route")

            def act():
                manifest = body.model_dump(mode="json")
                errors = validate(c, manifest)
                bid, h = uid(), digest(manifest)
                status = "rejected" if errors else "validated"
                c.execute(
                    "INSERT INTO anvil.import_batches(id,project_id,created_by,manifest,manifest_hash,status,validation_errors) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (bid, project, user, Jsonb(manifest), h, status, Jsonb(errors)),
                )
                audit(c, project, user, "external_results.validated", bid, {"status": status})
                return {
                    "id": bid,
                    "manifest_hash": h,
                    "status": status,
                    "errors": errors,
                    "origin": body.origin,
                    "independently_reproduced": False,
                }

            return wrap(idempotent(c, project, user, request, body, act), request)

    @router.post("/imports/{iid}/commit-results")
    def commit(project: UUID, iid: UUID, body: Commit, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "data-engineer")

            def act():
                batch = one(c, "SELECT * FROM anvil.import_batches WHERE id=%s FOR UPDATE", (iid,))
                if not batch:
                    raise HTTPException(404, "Import not found")
                m = batch["manifest"]
                if (
                    m.get("schema_version") != "anvil.external_results.v1"
                    or body.manifest_hash != batch["manifest_hash"]
                ):
                    raise HTTPException(409, "Exact external manifest hash required")
                if batch["status"] == "committed":
                    return one(
                        c, "SELECT * FROM anvil.external_result_receipts WHERE import_id=%s", (iid,)
                    )
                run = get_run(c, m["run_id"], True)
                errors = validate(c, m)
                if batch["status"] != "validated" or errors:
                    raise HTTPException(409, "External evidence no longer qualifies")
                receipt_id = uid()
                receipt_hash = digest(
                    {
                        "schema_version": "anvil.external_receipt.v1",
                        "manifest_hash": batch["manifest_hash"],
                        "run_id": str(run["id"]),
                        "origin": m["origin"],
                    }
                )
                c.execute(
                    "INSERT INTO anvil.external_result_receipts(id,project_id,run_id,import_id,manifest_hash,receipt_hash) VALUES(%s,%s,%s,%s,%s,%s)",
                    (receipt_id, project, run["id"], iid, batch["manifest_hash"], receipt_hash),
                )
                pending = False
                for attempt in m["attempts"]:
                    eid = uid()
                    reviewable = attempt["execution_state"] == "completed" and bool(
                        attempt["output_artifact_id"]
                    )
                    state = (
                        "queued"
                        if reviewable
                        else "unscorable"
                        if attempt["execution_state"] == "completed"
                        else attempt["execution_state"]
                    )
                    outcome = (
                        "pending_review"
                        if reviewable
                        else "unscorable"
                        if state == "unscorable"
                        else "invalid"
                        if state == "failed_operational"
                        else "unknown"
                    )
                    provenance = {k: v for k, v in m.items() if k not in ("attempts", "run_id")}
                    provenance.update(
                        {
                            "attempt": attempt,
                            "receipt_hash": receipt_hash,
                            "manifest_hash": batch["manifest_hash"],
                            "independently_reproduced": False,
                        }
                    )
                    c.execute(
                        "INSERT INTO anvil.episodes(id,project_id,run_id,task_revision_id,candidate_key,state,outcome,output_artifact_id,thread_id,graph_version,external_provenance) VALUES(%s,%s,%s,%s,'external-reported',%s,%s,%s,%s,%s,%s)",
                        (
                            eid,
                            project,
                            run["id"],
                            attempt["task_revision_id"],
                            state,
                            outcome,
                            attempt["output_artifact_id"],
                            uid(),
                            EXTERNAL_GRAPH_VERSION,
                            Jsonb(provenance),
                        ),
                    )
                    if reviewable:
                        pending = True
                        enqueue(c, project, "episode", eid, f"external-review:{eid}")
                c.execute(
                    "UPDATE anvil.runs SET state=%s,cost_status='externally_reported',row_version=row_version+1 WHERE id=%s",
                    ("queued" if pending else "execution_complete", run["id"]),
                )
                c.execute("UPDATE anvil.import_batches SET status='committed' WHERE id=%s", (iid,))
                enqueue(
                    c, project, "sales_kit_prepare", run["id"], "provisional-kit:" + str(run["id"])
                )
                audit(
                    c,
                    project,
                    user,
                    "external_results.committed",
                    receipt_id,
                    {"origin": m["origin"], "receipt_hash": receipt_hash},
                )
                return one(
                    c, "SELECT * FROM anvil.external_result_receipts WHERE id=%s", (receipt_id,)
                )

            return wrap(idempotent(c, project, user, request, body, act), request)

    return router
