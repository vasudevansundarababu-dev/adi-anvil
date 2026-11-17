"""Generic protected intake and version-bound resolution. Never queues a Run."""

from fastapi import HTTPException

from anvil.benchmark_storage import bind_private
from anvil.db import Jsonb, audit, uid
from anvil.praxis_generic_contract import digest
from anvil.praxis_template_registry import lookup, source_hash


def resolve(c, project, user, result, parsed, prepared, *, client_id=None, auth_kind=None):
    manifest = parsed["manifest"]
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    dataset_binding = None
    if manifest.schema_version == "praxis.authored-task-export.v2":
        from anvil.praxis_case_registry import lookup as dataset_lookup

        dataset_binding = dataset_lookup(c, project, manifest.case_dataset)
        if dataset_binding:
            from anvil.praxis_case_dataset import CaseDataset
            from anvil.praxis_generic_contract import CampaignExport
            from anvil.praxis_marketing_contract import CampaignDataset

            if (
                CampaignDataset if isinstance(manifest, CampaignExport) else CaseDataset
            ).model_validate(dataset_binding["manifest"]).reference() != manifest.case_dataset:
                return conflict(
                    result,
                    "PX_CASE_DATASET_REFERENCE",
                    "/case_dataset",
                    "Copy Anvil's exact dataset descriptor; do not alter its count or version.",
                )
        if not dataset_binding or not dataset_binding["qualified"]:
            return result | {
                "status": "anvil_blocked",
                "anvil_requirements": [
                    {
                        "code": "AV_CASE_DATASET_QUALIFICATION_REQUIRED",
                        "owner": "anvil",
                        "status": "blocked",
                    }
                ],
            }
    for item in parsed["tasks"]:
        current = lookup(c, project, item["entry"].template)
        if not current or not current["qualified"]:
            return result | {
                "status": "anvil_blocked",
                "anvil_requirements": [
                    {
                        "code": "AV_TEMPLATE_QUALIFICATION_REVOKED"
                        if current and current["revoked"]
                        else "AV_TEMPLATE_NOT_QUALIFIED",
                        "owner": "anvil",
                        "status": "blocked",
                    }
                ],
            }
        item["template"] = current
    history = c.execute(
        "SELECT * FROM anvil.praxis_export_resolutions WHERE project_id=%s AND package_key=%s AND version=%s ORDER BY created_at,id",
        (project, manifest.package_id, manifest.package_version),
    ).fetchall()
    if any(row["package_sha256"] != result["package_sha256"] for row in history):
        return conflict(
            result,
            "PX_VERSION_CONFLICT",
            "/package_version",
            "Use the original immutable package or a new package version.",
        )
    resolution_context_sha256 = digest(
        {
            "source_sha256": source_hash(),
            "templates": sorted(
                [
                    {
                        "task_id": item["entry"].task_id,
                        "template_sha256": item["template"]["row"]["spec_sha256"],
                        "qualification_id": str(item["template"]["qualification"]["id"]),
                        "qualification_sha256": item["template"]["qualification"]["receipt_sha256"],
                    }
                    for item in parsed["tasks"]
                ],
                key=lambda v: v["task_id"],
            ),
            "dataset_import_sha256": dataset_binding["import"]["manifest_sha256"]
            if dataset_binding
            else None,
        }
    )
    old = next(
        (row for row in history if row["execution_binding_key"] == resolution_context_sha256), None
    )
    if old:
        if (
            digest(old["receipt"]) != old["receipt_sha256"]
            or old["receipt"]["source_sha256"] != source_hash()
        ):
            raise HTTPException(
                409, "Stored resolution source/integrity changed; Anvil requalification required"
            )
        stored = c.execute(
            "SELECT task_key,binding,binding_sha256 FROM anvil.praxis_resolved_tasks WHERE project_id=%s AND resolution_id=%s",
            (project, old["id"]),
        ).fetchall()
        expected = {item["entry"].task_id: item["template"] for item in parsed["tasks"]}
        if len(stored) != len(expected) or any(
            row["task_key"] not in expected
            or digest(row["binding"]) != row["binding_sha256"]
            or row["binding"]["qualification_id"]
            != str(expected[row["task_key"]]["qualification"]["id"])
            for row in stored
        ):
            return result | {
                "status": "anvil_blocked",
                "anvil_requirements": [
                    {
                        "code": "AV_RESOLUTION_REQUALIFICATION_REQUIRED",
                        "owner": "anvil",
                        "status": "blocked",
                    }
                ],
            }
        return response(c, project, result, old)
    batch = c.execute(
        "SELECT part_index,part_count,package_sha256 FROM anvil.praxis_export_resolutions WHERE project_id=%s AND batch_key=%s AND NOT(package_key=%s AND version=%s)",
        (project, manifest.batch.id, manifest.package_id, manifest.package_version),
    ).fetchall()
    if any(
        v["part_count"] != manifest.batch.part_count or v["part_index"] == manifest.batch.part_index
        for v in batch
    ):
        return conflict(
            result,
            "PX_BATCH_CONFLICT",
            "/batch",
            "Use consistent batch count and a unique part index; do not overwrite a received part.",
        )
    ids = [item["entry"].task_id for item in parsed["tasks"]]
    if c.execute(
        "SELECT 1 FROM anvil.praxis_resolved_tasks t JOIN anvil.praxis_export_resolutions r ON r.id=t.resolution_id AND r.project_id=t.project_id WHERE t.project_id=%s AND r.batch_key=%s AND NOT(r.package_key=%s AND r.version=%s) AND t.task_key=ANY(%s) LIMIT 1",
        (project, manifest.batch.id, manifest.package_id, manifest.package_version, ids),
    ).fetchone():
        return conflict(
            result,
            "PX_BATCH_TASK_DUPLICATE",
            "/tasks",
            "Export each task once across this batch; repair the part partition.",
        )
    private_archive = bind_private(c, prepared, created_by=user)
    identifier = uid()
    bindings = []
    for item in parsed["tasks"]:
        template = item["template"]
        qualification = template["qualification"]
        binding = {
            "schema_version": "anvil.generic-task-binding.v1",
            "task_id": item["entry"].task_id,
            "revision_id": item["entry"].revision_id,
            "template_sha256": template["row"]["spec_sha256"],
            "qualification_id": str(qualification["id"]),
            "qualification_sha256": qualification["receipt_sha256"],
            "actor_sha256": digest(item["actor"]),
            "private_reference_sha256": item["entry"].private_assets[0].sha256,
            "execution_sha256": template["row"]["part_hashes"]["execution"],
            "catalogue_sha256": template["row"]["catalogue_sha256"],
            "source_sha256": source_hash(),
            "environment": template["row"]["spec"]["execution"]["environment"],
            "evaluator_bindings": template["row"]["spec"]["execution"]["evaluators"],
            "run_authority": "not_granted",
            "paid_calls": False,
        }
        if parsed.get("application_workflow") is not None:
            # The original v1 package has no authored case-dataset reference.
            # Anvil binds selected immutable inputs separately; source intake
            # cannot choose a latest dataset or infer policy/runtime readiness.
            binding.update(task_mode="reusable_application_workflow",
                           case_selector=item["entry"].case_selector.model_dump(),
                           source_manifest_sha256=parsed["source_manifest_sha256"],
                           authored_sha256=digest(item["private"]["authored"]),
                           source_review_provenance=item["entry"].review,
                           input_binding_status="anvil_input_binding_required")
        if dataset_binding and item["entry"].case_selector.field == "dataset":
            context = {
                "schema_version": "anvil.campaign-context.v1",
                "task_id": item["entry"].task_id,
                "revision_id": item["entry"].revision_id,
                "caseDataset": manifest.case_dataset.model_dump(),
                "caseSelector": item["entry"].case_selector.model_dump(),
                "environment": binding["environment"],
                "workflow_graph_sha256": template["row"]["spec"]["execution"][
                    "workflow_graph_sha256"
                ],
                "evaluator_bindings_sha256": digest(binding["evaluator_bindings"]),
            }
            binding.update(
                schema_version="anvil.generic-task-binding.v2",
                task_mode="reusable_campaign_workflow",
                case_context=context,
                case_context_sha256=digest(context),
                case_import_id=str(dataset_binding["import"]["id"]),
                case_import_sha256=dataset_binding["import"]["manifest_sha256"],
            )
        elif dataset_binding:
            from anvil.praxis_case_dataset import StateTaskContext

            actor = item["actor"]
            state = actor["sections"]["S1"]["governingState"]
            state_policies = [
                {
                    "id": p["ruleId"],
                    "version": p["ruleVersion"],
                    "content_sha256": p["contentSha256"],
                    "publication_ref": p["locator"],
                    "state": state,
                }
                for p in actor["sections"]["S4"]["statePolicies"]
            ]
            context = StateTaskContext.model_validate(
                {
                    "schema_version": "anvil.state-kyc-context.v1",
                    "task_id": item["entry"].task_id,
                    "revision_id": item["entry"].revision_id,
                    "caseDataset": manifest.case_dataset.model_dump(),
                    "caseSelector": item["entry"].case_selector.model_dump(),
                    "federalPolicies": template["row"]["spec"]["execution"]["federalPolicies"],
                    "statePolicies": state_policies,
                    "environment": binding["environment"],
                    "evaluator_bindings_sha256": digest(
                        dataset_binding["import"]["manifest"]["evaluators"]
                    ),
                }
            ).model_dump()
            binding.update(
                schema_version="anvil.generic-task-binding.v2",
                task_mode="reusable_state_workflow",
                case_context=context,
                case_context_sha256=digest(context),
                case_import_id=str(dataset_binding["import"]["id"]),
                case_import_sha256=dataset_binding["import"]["manifest_sha256"],
            )
        bindings.append(
            {
                "id": uid(),
                "binding": binding,
                "template_id": str(template["row"]["id"]),
                "actor": item["actor"],
            }
        )
    receipt = {
        "binding_context_sha256": resolution_context_sha256,
        "schema_version": "anvil.generic-export-resolution.v1",
        "package_sha256": result["package_sha256"],
        "source_sha256": source_hash(),
        "batch": manifest.batch.model_dump(),
        "bindings": [
            {
                "id": b["id"],
                "task_id": b["binding"]["task_id"],
                "binding_sha256": digest(b["binding"]),
            }
            for b in bindings
        ],
        "private_storage": "protected_benchmark_vault_not_public_download",
        "review_gates": result["review_gates"],
        "authenticated_actor": {
            "kind": auth_kind or ("project_export_client" if client_id else "user_session"),
            "client_id": client_id,
            "sponsor_user_id": str(user),
        },
        "run_authority": "not_granted",
        "paid_calls": False,
    }
    row = c.execute(
        "INSERT INTO anvil.praxis_export_resolutions(id,project_id,package_key,version,package_sha256,batch_key,part_index,part_count,private_archive_id,receipt,receipt_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            identifier,
            project,
            manifest.package_id,
            manifest.package_version,
            result["package_sha256"],
            manifest.batch.id,
            manifest.batch.part_index,
            manifest.batch.part_count,
            private_archive,
            Jsonb(receipt),
            digest(receipt),
            user,
        ),
    ).fetchone()
    for bound in bindings:
        value = bound["binding"]
        c.execute(
            "INSERT INTO anvil.praxis_resolved_tasks(id,project_id,resolution_id,template_id,task_key,revision,actor,actor_sha256,private_reference_sha256,binding,binding_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                bound["id"],
                project,
                identifier,
                bound["template_id"],
                value["task_id"],
                value["revision_id"],
                Jsonb(bound["actor"]),
                value["actor_sha256"],
                value["private_reference_sha256"],
                Jsonb(value),
                digest(value),
                user,
            ),
        )
    audit(
        c,
        project,
        user,
        "praxis_export.resolved",
        identifier,
        {"package_sha256": result["package_sha256"], "export_client_id": client_id},
    )
    return response(c, project, result, row)


def conflict(result, code, pointer, fix):
    return result | {
        "valid": False,
        "status": "export_invalid",
        "errors": [
            {
                "code": code,
                "owner": "praxis",
                "file": "praxis-export.json",
                "pointer": pointer,
                "message": "Immutable package/batch identity conflicts with received content.",
                "fix": fix,
                "retryable": False,
            }
        ],
        "error_count": 1,
    }


def response(c, project, result, row):
    count = c.execute(
        "SELECT count(DISTINCT part_index) AS n FROM anvil.praxis_export_resolutions WHERE project_id=%s AND batch_key=%s",
        (project, row["batch_key"]),
    ).fetchone()["n"]
    needs = (
        []
        if count == row["part_count"]
        else [{"code": "AV_BATCH_INCOMPLETE", "owner": "anvil", "status": "waiting"}]
    )
    return result | {
        "status": "import_resolved",
        "receipt_id": str(row["id"]),
        "receipt": row["receipt"],
        "receipt_sha256": row["receipt_sha256"],
        "anvil_requirements": needs,
        "batch_received_parts": count,
    }
