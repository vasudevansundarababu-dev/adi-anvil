"""Validated structured data, immutable selections and exact execution overlays.

No quarantine state is changed. Upload/selection/provisioning make no model
request and never publish a Praxis task, review a policy or qualify a runtime.
"""

import hashlib
import json
import os
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, ValidationError

from anvil import auth
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.golden_targets import family
from anvil.project_bindings import group
from anvil.project_input_contract import (
    INPUT,
    MAX_BYTES,
    PROJECT_QUOTA_BYTES,
    FrozenSelection,
    Sampling,
    select,
)
from anvil.schemas import Strict
from anvil.workspace import READ_ROLES


class Select(Strict):
    input_id: UUID | None = None
    sampling: Sampling = Field(default_factory=Sampling)


def schema_hash():
    return digest(INPUT.json_schema())


def source_family(imported):
    families = {family(task) for task in imported["content"].get("tasks", [])}
    if len(families) != 1 or not families <= {"kyc", "marketing"}:
        raise HTTPException(409, {"code": "AV_INPUT_SCHEMA_UNQUALIFIED", "owner": "anvil"})
    return next(iter(families))


def members(content):
    if content["schema_version"] == "anvil.kyc-actor-input.v1":
        return [
            {
                "id": app["id"],
                "snapshot_sha256": digest(app),
                "governing_state": app["governing_state"],
            }
            for app in content["applications"]
        ]
    return [
        {"id": case["id"], "snapshot_sha256": digest(case), "locale": case["locale"]}
        for case in content["cases"]
    ]


def bounded_records(records):
    output, size = [], 0
    for record in records[:10]:
        encoded_size = len(json.dumps(record, ensure_ascii=False).encode())
        if size + encoded_size > 262144:
            break
        output.append(record)
        size += encoded_size
    return output


def get(c, project, imported, identifier):
    row = one(
        c,
        "SELECT * FROM anvil.project_data_inputs WHERE project_id=%s AND task_group_id=%s AND id=%s",
        (project, imported["id"], identifier),
    )
    if not row:
        raise HTTPException(404, "Input version not found in this Project")
    if (
        row["source_sha256"] != imported["content_sha256"]
        or digest(row["content"]) != row["content_sha256"]
        or row["schema_sha256"] != schema_hash()
    ):
        raise HTTPException(409, {"code": "AV_INPUT_REVALIDATION_REQUIRED", "owner": "anvil"})
    return row


def public(c, row):
    provision = one(
        c,
        "SELECT manifest,manifest_sha256 FROM anvil.project_data_provisions WHERE project_id=%s AND input_id=%s",
        (row["project_id"], row["id"]),
    )
    data = members(row["content"])
    return {
        key: row[key]
        for key in (
            "id",
            "filename",
            "family",
            "schema_version",
            "schema_sha256",
            "raw_sha256",
            "content_sha256",
            "byte_size",
            "created_at",
        )
    } | {
        "case_count": len(data),
        "state_counts": {
            state: sum(member.get("governing_state") == state for member in data)
            for state in ("CA", "NY", "TX", "FL", "IL")
        }
        if row["family"] == "kyc"
        else None,
        "status": "populated_not_runtime_qualified"
        if provision
        else "validated_provisioning_queued",
        "provision": provision,
        "validation": "structured_schema_only_not_antivirus_or_domain_review",
        "private_answers_included": False,
        "paid_calls": False,
    }


def save(c, project, user, imported, content, raw_sha, filename, byte_size):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    kind = "kyc" if content["schema_version"] == "anvil.kyc-actor-input.v1" else "marketing"
    if kind != source_family(imported):
        raise HTTPException(
            422,
            {
                "code": "INPUT_TASK_FAMILY_MISMATCH",
                "owner": "input_owner",
                "fix": "Upload the structured input format advertised for this task family.",
            },
        )
    fingerprint = digest(content)
    old = one(
        c,
        "SELECT * FROM anvil.project_data_inputs WHERE project_id=%s AND task_group_id=%s AND content_sha256=%s AND schema_sha256=%s",
        (project, imported["id"], fingerprint, schema_hash()),
    )
    if old is None:
        quota = one(
            c,
            "SELECT coalesce(sum(byte_size),0) AS size FROM anvil.project_data_inputs WHERE project_id=%s",
            (project,),
        )
        if quota["size"] + byte_size > PROJECT_QUOTA_BYTES:
            raise HTTPException(
                409,
                {
                    "code": "INPUT_PROJECT_QUOTA",
                    "owner": "anvil_admin",
                    "limit_bytes": PROJECT_QUOTA_BYTES,
                },
            )
        identifier = uid()
        c.execute(
            "INSERT INTO anvil.project_data_inputs(id,project_id,task_group_id,source_sha256,family,filename,schema_version,schema_sha256,raw_sha256,content,content_sha256,byte_size,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                identifier,
                project,
                imported["id"],
                imported["content_sha256"],
                kind,
                filename,
                content["schema_version"],
                schema_hash(),
                raw_sha,
                Jsonb(content),
                fingerprint,
                byte_size,
                user,
            ),
        )
        c.execute(
            "INSERT INTO anvil.project_data_input_jobs(input_id,project_id) VALUES(%s,%s)",
            (identifier, project),
        )
        old = get(c, project, imported, identifier)
    audit(
        c,
        project,
        user,
        "project.structured_input_validated",
        old["id"],
        {
            "raw_submission_sha256": raw_sha,
            "content_sha256": fingerprint,
            "filename": filename,
            "task_group_id": str(imported["id"]),
        },
    )
    return public(c, old) | {"submitted_raw_sha256": raw_sha}


def default_dataset(c, project, imported):
    from anvil.praxis_case_dataset import CaseDatasetRef
    from anvil.praxis_case_registry import lookup

    reference = imported["content"].get("case_dataset")
    if not reference:
        raise HTTPException(409, {"code": "AV_DEFAULT_DATA_BINDING_REQUIRED", "owner": "anvil"})
    result = lookup(c, project, CaseDatasetRef.model_validate(reference))
    if not result:
        raise HTTPException(
            409, {"code": "AV_DEFAULT_DATA_PROVISIONING_REQUIRED", "owner": "anvil"}
        )
    return result


def selection(c, project, user, imported, body):
    if body.input_id:
        row = get(c, project, imported, body.input_id)
        eligible, reference = members(row["content"]), row["content_sha256"]
        basis = {
            "kind": "uploaded_input",
            "input_id": str(row["id"]),
            "content_sha256": row["content_sha256"],
            "schema_sha256": row["schema_sha256"],
        }
    else:
        default = default_dataset(c, project, imported)
        eligible = default["manifest"]["cases"]
        reference = default["description"]["sha256"]
        basis = {
            "kind": "shared_default_dataset",
            "case_dataset": imported["content"]["case_dataset"],
        }
    try:
        chosen = select(eligible, reference, body.sampling)
    except ValueError as exc:
        raise HTTPException(
            422, {"code": "INPUT_SELECTION_INVALID", "owner": "input_owner", "fix": str(exc)}
        ) from None
    payload = {
        "schema_version": "anvil.execution-data-selection.v1",
        "source_sha256": imported["content_sha256"],
        "family": source_family(imported),
        "basis": basis,
        "sample": chosen,
    }
    identifier, fingerprint = uid(), digest(payload)
    c.execute(
        "INSERT INTO anvil.project_data_selections(id,project_id,task_group_id,input_id,source_sha256,selection,selection_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            imported["id"],
            body.input_id,
            imported["content_sha256"],
            Jsonb(payload),
            fingerprint,
            user,
        ),
    )
    return {
        "id": identifier,
        "sha256": fingerprint,
        "selection": payload,
        "paid_calls": False,
        "run_authority": "not_granted",
    }


def frozen(c, project, imported, reference):
    """Resolve the exact Project/source-scoped selection, never a caller manifest."""
    ref = FrozenSelection.model_validate(reference)
    row = one(
        c,
        "SELECT * FROM anvil.project_data_selections WHERE project_id=%s AND task_group_id=%s AND id=%s",
        (project, imported["id"], ref.id),
    )
    if row is None:
        raise HTTPException(404, "Input selection not found in this Project")
    if (
        row["selection_sha256"] != ref.sha256
        or digest(row["selection"]) != ref.sha256
        or row["source_sha256"] != imported["content_sha256"]
    ):
        raise HTTPException(409, {"code": "AV_INPUT_SELECTION_CHANGED", "owner": "anvil"})
    payload = row["selection"]
    basis, sample = payload["basis"], payload["sample"]
    if basis["kind"] == "uploaded_input":
        version = get(c, project, imported, basis["input_id"])
        eligible, fingerprint = members(version["content"]), version["content_sha256"]
        if (
            str(row["input_id"]) != basis["input_id"]
            or basis["content_sha256"] != fingerprint
            or basis["schema_sha256"] != version["schema_sha256"]
        ):
            raise HTTPException(409, "Input selection version changed")
    else:
        default = default_dataset(c, project, imported)
        eligible, fingerprint = default["manifest"]["cases"], default["description"]["sha256"]
        if (
            row["input_id"] is not None
            or basis["case_dataset"] != imported["content"]["case_dataset"]
        ):
            raise HTTPException(409, "Default input selection source changed")
    if (
        sample != select(eligible, fingerprint, Sampling.model_validate(sample["sampling"]))
        or payload["source_sha256"] != imported["content_sha256"]
        or payload["family"] != source_family(imported)
    ):
        raise HTTPException(409, "Input selection population or sampling provenance changed")
    return row


def selection_gaps(c, project, imported, reference, workflow=()):
    if os.environ.get("ANVIL_PROJECT_INPUTS_ENABLED") != "true":
        return [{"section": "data", "code": "AV_STRUCTURED_INPUTS_DISABLED", "owner": "anvil"}]
    row = frozen(c, project, imported, reference)
    if row["input_id"]:
        provision = one(
            c,
            "SELECT manifest,manifest_sha256 FROM anvil.project_data_provisions WHERE project_id=%s AND input_id=%s",
            (project, row["input_id"]),
        )
        if not provision:
            return [{"section": "data", "code": "AV_INPUT_PROVISIONING_PENDING", "owner": "anvil"}]
        if digest(provision["manifest"]) != provision["manifest_sha256"]:
            return [{"section": "data", "code": "AV_INPUT_PROVISION_INTEGRITY", "owner": "anvil"}]
    # Admission requires packages that consume this selection, not upload success.
    overlay = execution_overlay(c, project, reference)
    if overlay["family"] != "kyc":
        return [
            {
                "section": "data",
                "code": "AV_CAMPAIGN_INPUT_EXECUTION_BINDING_REQUIRED",
                "owner": "anvil",
            }
        ]
    packages = []
    for ref in workflow:
        if ref["kind"] != "package":
            continue
        package = one(
            c,
            "SELECT * FROM anvil.harbor_packages WHERE project_id=%s AND id=%s",
            (project, ref["id"]),
        )
        if package and package["package_sha256"] == ref["sha256"]:
            packages.append(package)
    expected_tasks = {task["task_id"] for task in imported["content"]["tasks"]}
    product_mode = bool(packages) and all((p["manifest"].get("native_binding") or {}).get("task_mode") == "reusable_application_workflow"
                                         for p in packages)
    if (
        len(packages) != (4 if product_mode else 5)
        or {p["manifest"]["task_id"] for p in packages} != expected_tasks
        or (not product_mode and any(
            (p["manifest"].get("native_binding") or {}).get("execution_data")
            != overlay["selection"]
            or (p["manifest"].get("native_binding") or {}).get("execution_data_sha256")
            != digest(overlay)
            for p in packages
        ))
    ):
        return [
            {"section": "data", "code": "AV_INPUT_EXECUTION_BINDING_REQUIRED", "owner": "anvil"}
        ]
    from anvil.golden_kyc_paid_package import task_set_assignments

    assignments = task_set_assignments(c, project, packages)
    if {a["application_id"]: a["application_sha256"] for a in assignments} != {
        m["id"]: m["snapshot_sha256"] for m in overlay["cases"]
    }:
        return [{"section": "data", "code": "AV_INPUT_CASE_ASSIGNMENT_MISMATCH", "owner": "anvil"}]
    return []


def options(c, project, imported):
    from anvil.project_bindings import current

    bound = current(c, project, imported["id"])
    selected = bound["snapshot"].get("execution_data") if bound else None
    selected_selection = frozen(c, project, imported, selected)["selection"] if selected else None
    return {
        "enabled": os.environ.get("ANVIL_PROJECT_INPUTS_ENABLED") == "true",
        "selected": selected,
        "selected_selection": selected_selection,
        "default_input": imported["content"].get("case_dataset"),
        "default_sampling": {"mode": "all"},
        "selection_field": "execution_data",
        "run_authority": "not_granted",
    }


def execution_overlay(c, project, reference):
    """Rebuild one immutable Anvil data overlay; preserve the authored default."""
    if os.environ.get("ANVIL_PROJECT_INPUTS_ENABLED") != "true":
        raise HTTPException(503, {"code": "AV_STRUCTURED_INPUTS_DISABLED", "owner": "anvil"})
    ref = FrozenSelection.model_validate(reference)
    selected = one(
        c,
        "SELECT task_group_id FROM anvil.project_data_selections WHERE project_id=%s AND id=%s",
        (project, ref.id),
    )
    if selected is None:
        raise HTTPException(404, "Execution input selection not found in this Project")
    imported = group(c, project, selected["task_group_id"])
    row = frozen(c, project, imported, reference)
    if row["input_id"]:
        provision = one(
            c,
            "SELECT * FROM anvil.project_data_provisions WHERE project_id=%s AND input_id=%s",
            (project, row["input_id"]),
        )
        if not provision or digest(provision["manifest"]) != provision["manifest_sha256"]:
            raise HTTPException(409, {"code": "AV_INPUT_PROVISIONING_PENDING", "owner": "anvil"})
        pack = provision["pack_id"]
        if provision["manifest"]["content_sha256"] != row["selection"]["basis"]["content_sha256"]:
            raise HTTPException(409, "Populated input content changed")
    else:
        default = default_dataset(c, project, imported)
        pack = default.get("import", {}).get("pack_id")
    sample = row["selection"]["sample"]
    return {
        "schema_version": "anvil.execution-data-overlay.v1",
        "selection": {"id": str(row["id"]), "sha256": row["selection_sha256"]},
        "task_group_id": str(imported["id"]),
        "source_sha256": imported["content_sha256"],
        "family": row["selection"]["family"],
        "input_id": str(row["input_id"]) if row["input_id"] else None,
        "pack_id": str(pack) if pack else None,
        "case_dataset": {
            "id": "execution-data-" + str(row["id"]),
            "version": "1",
            "sha256": sample["sha256"],
            "case_count": sample["selected_count"],
        },
        "cases": sample["members"],
        "sampling": sample["sampling"],
        "eligible_count": sample["eligible_count"],
        "selected_count": sample["selected_count"],
        "complete_population": sample["complete_population"],
        "authored_default_case_dataset": imported["content"].get("case_dataset"),
    }


def overlay_assignment(context, overlay, application):
    cases = [
        case
        for case in overlay["cases"]
        if case.get("governing_state") == context.caseSelector.value
    ]
    member = next((case for case in cases if case["id"] == application), None)
    if member is None:
        raise HTTPException(409, "Application is outside the frozen state task input selection")
    return {
        "schema_version": "anvil.state-kyc-case-assignment.v1",
        "task_id": context.task_id,
        "revision_id": context.revision_id,
        "task_context_sha256": digest(context.model_dump()),
        "case_dataset_sha256": overlay["case_dataset"]["sha256"],
        "application_id": member["id"],
        "application_sha256": member["snapshot_sha256"],
        "governing_state": member["governing_state"],
        "selector_case_count": len(cases),
        "policy_binding_sha256": digest(
            {
                "federal": [p.model_dump() for p in context.federalPolicies],
                "state": [p.model_dump() for p in context.statePolicies],
            }
        ),
        "environment": context.environment,
        "evaluator_bindings_sha256": context.evaluator_bindings_sha256,
        "execution_data_sha256": digest(overlay),
        "authored_default_case_dataset": context.caseDataset.model_dump(),
        "legal_acceptance": "requires_independent_review",
        "run_authority": "not_granted",
    }


def actor_overlay(overlay, state):
    """One actor receives scope provenance, never the other cases' membership."""
    return {
        key: overlay[key]
        for key in (
            "schema_version",
            "selection",
            "source_sha256",
            "family",
            "input_id",
            "case_dataset",
            "sampling",
            "eligible_count",
            "selected_count",
            "complete_population",
            "authored_default_case_dataset",
        )
    } | {
        "governing_state": state,
        "partition_case_count": sum(
            case.get("governing_state") == state for case in overlay["cases"]
        ),
    }


def routes(context, wrap, idempotent):
    router = APIRouter(
        prefix="/api/v1/projects/{project}/imported-projects/{task_group_id}/data-inputs"
    )

    def enabled():
        if os.environ.get("ANVIL_PROJECT_INPUTS_ENABLED") != "true":
            raise HTTPException(503, {"code": "AV_STRUCTURED_INPUTS_DISABLED", "owner": "anvil"})

    @router.get("")
    def listing(project: UUID, task_group_id: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            imported = group(c, project, task_group_id)
            kind = source_family(imported)
            rows = c.execute(
                "SELECT * FROM anvil.project_data_inputs WHERE project_id=%s AND task_group_id=%s ORDER BY created_at DESC,id DESC LIMIT 20",
                (project, task_group_id),
            ).fetchall()
            return wrap(
                {
                    "enabled": os.environ.get("ANVIL_PROJECT_INPUTS_ENABLED") == "true",
                    "family": kind,
                    "default_input": {
                        "kind": "shared_default_dataset",
                        "location": "Anvil shared dataset",
                        "case_dataset": imported["content"].get("case_dataset"),
                        "status": "source_reference_present_not_runtime_qualified"
                        if imported["content"].get("case_dataset")
                        else "anvil_provisioning_required",
                    },
                    "versions": [public(c, row) for row in rows],
                    "schema": INPUT.json_schema(),
                    "schema_sha256": schema_hash(),
                    "upload": {
                        "content_type": "application/json",
                        "max_bytes": MAX_BYTES,
                        "filename_header": "X-Input-Filename",
                        "validation": "strict_structured_JSON_not_generic_file_scan",
                    },
                    "sampling_schema": Sampling.model_json_schema(),
                    "default_sampling": {"mode": "all"},
                    "paid_calls": False,
                },
                request,
            )

    @router.post("")
    async def upload(project: UUID, task_group_id: UUID, request: Request):
        from anvil.praxis_generic_contract import load
        from anvil.request_limits import RequestBodyTooLarge

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            enabled()
            imported = group(c, project, task_group_id)
            if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
                raise HTTPException(415, "Use the advertised UTF8 structured JSON input format")
            filename = request.headers.get("x-input-filename", "input.json")
            if not 1 <= len(filename) <= 160 or any(char in filename for char in "\r\n\x00/\\"):
                raise HTTPException(422, "Use a bounded filename without a filesystem path")
            chunks, size = [], 0
            try:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise RequestBodyTooLarge()
                    chunks.append(chunk)
                raw = b"".join(chunks)
                content = INPUT.validate_python(load(raw)).model_dump(mode="json")
            except RequestBodyTooLarge:
                raise HTTPException(413, "Structured input exceeds10MiB") from None
            except ValidationError as exc:
                errors = [
                    {
                        "code": "INPUT_SCHEMA",
                        "owner": "input_owner",
                        "path": "/" + "/".join(str(part) for part in error["loc"]),
                        "type": error["type"],
                        "fix": "Use the advertised input schema; correct this field, subject link or duplicate ID.",
                    }
                    for error in exc.errors(include_input=False, include_context=False)
                ]
                raise HTTPException(
                    422, {"code": "INPUT_VALIDATION_FAILED", "valid": False, "errors": errors}
                ) from None
            except (ValueError, UnicodeError, RecursionError):
                raise HTTPException(
                    422,
                    {
                        "code": "INPUT_JSON_INVALID",
                        "owner": "input_owner",
                        "fix": "Use bounded UTF8 JSON without duplicate keys, hidden controls or non-finite numbers.",
                    },
                ) from None
            normalized_size = len(json.dumps(content, ensure_ascii=False).encode())
            if normalized_size > MAX_BYTES:
                raise HTTPException(413, "Normalized structured input exceeds10MiB")
            metadata = {
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "content_sha256": digest(content),
                "filename": filename,
            }
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    metadata,
                    lambda: save(
                        c,
                        project,
                        user,
                        imported,
                        content,
                        metadata["raw_sha256"],
                        filename,
                        normalized_size,
                    ),
                ),
                request,
            )

    @router.post("/selections")
    def choose(project: UUID, task_group_id: UUID, body: Select, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            enabled()
            imported = group(c, project, task_group_id)
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body.model_dump(mode="json"),
                    lambda: selection(c, project, user, imported, body),
                ),
                request,
            )

    @router.get("/default/preview")
    def default_preview(project: UUID, task_group_id: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            imported = group(c, project, task_group_id)
            default = default_dataset(c, project, imported)
            data = default["manifest"]["cases"]
            records = []
            if source_family(imported) == "kyc":
                rows = c.execute(
                    "SELECT snapshot,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id LIMIT 10",
                    (project, default["import"]["pack_id"]),
                ).fetchall()
                if any(digest(row["snapshot"]) != row["snapshot_sha256"] for row in rows):
                    raise HTTPException(409, "Default actor input integrity changed")
                records = bounded_records([row["snapshot"] for row in rows])
            return wrap(
                {
                    "kind": "shared_default_dataset",
                    "case_dataset": imported["content"]["case_dataset"],
                    "actor_records": records,
                    "members": data[:20],
                    "schema": INPUT.json_schema(),
                    "schema_sha256": schema_hash(),
                    "preview_count": len(records),
                    "total_count": len(data),
                    "preview_only": True,
                    "preview_truncated": len(records) < len(data),
                    "private_answers_included": False,
                    "qualified": default["qualified"],
                    "preview_gap": "AV_CAMPAIGN_DEFAULT_ACTOR_PREVIEW_REQUIRED"
                    if source_family(imported) == "marketing"
                    else None,
                },
                request,
            )

    @router.get("/{identifier}/preview")
    def preview(project: UUID, task_group_id: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            row = get(c, project, group(c, project, task_group_id), identifier)
            data = members(row["content"])
            records = row["content"].get("applications", row["content"].get("cases", []))
            preview_records = bounded_records(records)
            return wrap(
                {
                    "version": public(c, row),
                    "members": data[:20],
                    "actor_records": preview_records,
                    "schema": INPUT.json_schema(),
                    "schema_sha256": schema_hash(),
                    "preview_only": True,
                    "preview_count": len(preview_records),
                    "total_count": len(data),
                    "preview_truncated": len(preview_records) < len(data),
                    "private_answers_included": False,
                },
                request,
            )

    return router
