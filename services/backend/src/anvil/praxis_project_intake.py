"""Validated authored export → public Anvil Project; private ZIP stays in vault.

Runtime/qualification/Run authority are NOT manufactured by structural import.
The generic wire has no Praxis Project name/ID; internal batch namespaces are
explicitly marked as Anvil identities, never presented as Praxis Project IDs.
"""

from fastapi import HTTPException

from anvil.benchmark_storage import bind_private
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.praxis_generic_contract import weight_bps


def projection(parsed, package_sha256):
    manifest = parsed["manifest"]
    tasks, environments = [], {}
    for item in parsed["tasks"]:
        entry, actor = item["entry"], item["actor"]
        spec = item["template"]["row"]["spec"]
        authored = item["private"]["authored"]
        execution = spec["execution"]
        marketing = execution["schema_version"] == "anvil.template-execution.v3"
        native_mapping = (
            {e["criterion_id"]: e for e in execution["evaluators"]} if marketing else {}
        )
        environment = execution["environment"]
        environment_key = environment["id"] + "@" + environment["version"]
        environments[environment_key] = {
            "id": environment_key,
            "name": environment["id"],
            "version": environment["version"],
            "kind": "declared_native_capability",
            "enforce": True,
        }
        criteria = [
            {
                "id": native_mapping[criterion["id"]]["native_criterion_id"]
                if marketing
                else criterion["id"],
                "description": criterion.get("name"),
                "weight_bps": weight_bps(criterion["weight"]),
                "critical": criterion.get("critical", False),
                **(
                    {
                        "source_criterion_id": criterion["id"],
                        "group": criterion["group"],
                        "points": native_mapping[criterion["id"]]["weight"],
                    }
                    if marketing
                    else {}
                ),
            }
            for criterion in authored["sections"]["S7"]["criteria"]
        ]
        template = {
            "id": entry.template.id,
            "version": entry.template.version,
            "sha256": entry.template.sha256,
            "profile_id": spec["authoring"]["profile"]["profileId"],
            "catalog_workflow_name": spec["authoring"]["profile"].get("catalogWorkflowName"),
        }
        policies = [
            {
                "id": p["id"],
                "version": p["version"],
                "content_sha256": p["content_sha256"],
                "publication_ref": p["publication_ref"],
                "scope": "template_federal",
            }
            for p in execution.get("federalPolicies", [])
        ]
        if hasattr(entry, "case_selector") and not marketing:
            for policy in actor["sections"].get("S4", {}).get("statePolicies", []):
                policies.append(
                    {
                        "id": policy["ruleId"],
                        "version": policy["ruleVersion"],
                        "content_sha256": policy["contentSha256"],
                        "publication_ref": policy["locator"],
                        "scope": "task_state",
                        **({"governing_state": entry.case_selector.value}
                           if entry.case_selector.field == "governing_state" else
                           {"applicability": "resolve_actual_application_state_charter_date"}),
                    }
                )
        # Execution rules remain distinct from federal and state policy sources.
        # An authored reusable task must not silently lose its template rules.
        policies += [
            {
                "id": p["id"],
                "version": p["version"],
                "content_sha256": p["content_sha256"],
                "publication_ref": p["publication_ref"],
                "scope": "template_execution",
            }
            for p in execution.get("rules", [])
        ]
        source = {
            "schema_version": "anvil.praxis-authored-public-task.v1",
            "original_export_contract": manifest.schema_version,
            "template": template,
            "policy_references": policies,
            "review": entry.review,
            "evaluator_bindings": execution["evaluators"],
        }
        task = {
            "task_id": entry.task_id,
            "task_version": entry.revision_id,
            "revision_id": entry.revision_id,
            "title": actor.get("title") or entry.task_id,
            "payload_sha256": entry.private_assets[0].sha256,
            "source": source,
            "actor": actor,
            "rubric": {
                "scale": "zero_to_four" if marketing else "five_two_zero",
                "criteria": criteria,
                **(
                    {"native_contract": execution["rubric"], "source": execution["rubric_source"]}
                    if marketing
                    else {}
                ),
            },
            "environment_ids": [environment_key],
            "dimensions": {},
            "failure_modes": [],
        }
        if hasattr(entry, "case_selector"):
            task["case_selector"] = entry.case_selector.model_dump()
        if actor.get("workflowGraph") is not None:
            task["workflow"] = actor["workflowGraph"]
        elif marketing:
            task["workflow"] = execution["workflow_graph"]
        tasks.append(task)
    result = {
        "export_contract": manifest.schema_version,
        "package_id": manifest.package_id,
        "package_version": manifest.package_version,
        "package_sha256": package_sha256,
        "batch": manifest.batch.model_dump(),
        "tasks": tasks,
        "environments": [environments[k] for k in sorted(environments)],
    }
    if hasattr(manifest, "case_dataset"):
        result["case_dataset"] = manifest.case_dataset.model_dump()
    return result


def store(c, project, user, result, parsed, prepared):
    if result["valid"] is not True:
        raise HTTPException(422, "Only structurally validated reviewed exports may import")
    manifest = parsed["manifest"]
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    if manifest.batch.part_count > 20:
        raise HTTPException(
            413,
            {
                "code": "AV_PROJECT_CAPACITY",
                "owner": "anvil",
                "message": "Project intake currently supports at most20parts; the source export contract remains unchanged.",
            },
        )
    previous = one(
        c,
        "SELECT * FROM anvil.praxis_project_intakes WHERE project_id=%s AND package_key=%s AND package_version=%s",
        (project, manifest.package_id, manifest.package_version),
    )
    public = projection(parsed, result["package_sha256"])
    if previous and (
        previous["package_sha256"] != result["package_sha256"]
        or previous["public_snapshot_sha256"] != digest(public)
    ):
        raise HTTPException(
            409, "Immutable authored package identity changed; export a new package version"
        )
    if not previous:
        prior = c.execute(
            "SELECT part_count,part_index,public_snapshot FROM anvil.praxis_project_intakes WHERE project_id=%s AND batch_key=%s",
            (project, manifest.batch.id),
        ).fetchall()
        keys = {task["task_id"] for row in prior for task in row["public_snapshot"]["tasks"]}
        if any(
            row["part_count"] != manifest.batch.part_count
            or row["part_index"] == manifest.batch.part_index
            for row in prior
        ) or keys & {task["task_id"] for task in public["tasks"]}:
            raise HTTPException(
                409, "Batch part count/index or task identity conflicts with received parts"
            )
        archive = bind_private(c, prepared, created_by=user)
        c.execute(
            "INSERT INTO anvil.praxis_project_intakes(id,project_id,package_key,package_version,package_sha256,batch_key,part_index,part_count,private_archive_id,public_snapshot,public_snapshot_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                uid(),
                project,
                manifest.package_id,
                manifest.package_version,
                result["package_sha256"],
                manifest.batch.id,
                manifest.batch.part_index,
                manifest.batch.part_count,
                archive,
                Jsonb(public),
                digest(public),
                user,
            ),
        )
    rows = c.execute(
        "SELECT * FROM anvil.praxis_project_intakes WHERE project_id=%s AND batch_key=%s ORDER BY part_index",
        (project, manifest.batch.id),
    ).fetchall()
    if len(rows) != manifest.batch.part_count:
        return {
            "status": "batch_incomplete",
            "received_parts": len(rows),
            "expected_parts": manifest.batch.part_count,
            "project_created": False,
            "run_authority": "not_granted",
        }
    if [r["part_index"] for r in rows] != list(range(1, manifest.batch.part_count + 1)) or any(
        digest(r["public_snapshot"]) != r["public_snapshot_sha256"] for r in rows
    ):
        raise HTTPException(409, "Batch identity or public projection integrity failed")
    snapshots = [r["public_snapshot"] for r in rows]
    datasets = [s.get("case_dataset") for s in snapshots]
    if any(d != datasets[0] for d in datasets):
        raise HTTPException(409, "One imported workload must use one shared case dataset")
    tasks = [t for snapshot in snapshots for t in snapshot["tasks"]]
    if len(tasks) > 1000:
        raise HTTPException(
            413,
            {
                "code": "AV_PROJECT_CAPACITY",
                "owner": "anvil",
                "message": "Project intake currently supports at most1000authored tasks; cases do not count as tasks.",
            },
        )
    campaign = bool(tasks) and all(
        t["source"]["template"]["profile_id"] == "veyra-hush-one-launch-v1" for t in tasks
    )
    if (
        datasets[0] is not None
        and campaign
        and (
            len(tasks) != 1
            or tasks[0].get("case_selector", {}).get("field") != "dataset"
            or tasks[0]["case_selector"]["value"] != "all"
            or tasks[0]["case_selector"]["case_count"] != datasets[0]["case_count"]
        )
    ):
        raise HTTPException(
            409,
            "Reusable Marketing batch requires one five-role task selecting the whole shared campaign dataset",
        )
    if (
        datasets[0] is not None
        and not campaign
        and (
            len(tasks) != 5
            or {t["case_selector"]["value"] for t in tasks} != {"CA", "NY", "TX", "FL", "IL"}
        )
    ):
        raise HTTPException(
            409, "Reusable KYC batch must contain exactly five state tasks; cases are not new tasks"
        )
    packages = [
        {"id": s["package_id"], "version": s["package_version"], "sha256": s["package_sha256"]}
        for s in snapshots
    ]
    # Internal namespace preserves the old table's immutable uniqueness without
    # inventing a source Praxis Project identity absent from its export contract.
    internal_id = "anvil:authored-batch:" + manifest.batch.id
    internal_version = digest(packages)
    old = one(
        c,
        "SELECT * FROM anvil.benchmark_task_groups WHERE project_id=%s AND source_project_id=%s AND source_version=%s",
        (project, internal_id, internal_version),
    )
    if old:
        return {
            "id": str(old["id"]),
            "display_id": old["display_id"],
            "status": "Binding Pending",
            "project_created": True,
            "source_sha256": old["content_sha256"],
            "task_count": len(tasks),
            "case_count": datasets[0]["case_count"] if datasets[0] else None,
            "run_authority": "not_granted",
        }
    label = one(c, "SELECT name FROM anvil.projects WHERE id=%s", (project,))["name"]
    names = {
        t["source"]["template"]["catalog_workflow_name"]
        for t in tasks
        if t["source"]["template"].get("catalog_workflow_name")
    }
    name_source = "anvil_project_name"
    if len(names) == 1:
        label = next(iter(names))
        name_source = "template_catalog_workflow_name"
    envs = {e["id"]: e for s in snapshots for e in s["environments"]}
    content = {
        "source_project": {"id": internal_id, "version": internal_version, "name": label},
        "source_origin": {
            "kind": "praxis_authored_batch",
            "batch_id": manifest.batch.id,
            "packages": packages,
            "source_project_metadata_status": "not_supplied_by_export_contract",
            "display_name_source": name_source,
        },
        "tasks": tasks,
        "environments": [envs[k] for k in sorted(envs)],
        "case_dataset": datasets[0],
    }
    identifier = uid()
    row = c.execute(
        "INSERT INTO anvil.benchmark_task_groups(id,project_id,source_project_id,source_version,name,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING display_id",
        (
            identifier,
            project,
            internal_id,
            internal_version,
            label,
            Jsonb(content),
            digest(content),
            user,
        ),
    ).fetchone()
    audit(
        c,
        project,
        user,
        "praxis_authored.project_imported",
        identifier,
        {
            "batch_id": manifest.batch.id,
            "task_count": len(tasks),
            "case_count": datasets[0]["case_count"] if datasets[0] else None,
            "content_sha256": digest(content),
        },
    )
    return {
        "id": identifier,
        "display_id": row["display_id"],
        "status": "Binding Pending",
        "project_created": True,
        "source_sha256": digest(content),
        "task_count": len(tasks),
        "case_count": datasets[0]["case_count"] if datasets[0] else None,
        "run_authority": "not_granted",
    }


def prepare_native(c, project, user, imported, max_model_calls, *, resolved_input=None):
    """Create five public packages from genuine current resolutions; no episodes/Run."""
    from anvil.golden_kyc_paid_package import prepare, task_set_assignments
    from anvil.praxis_template_registry import source_hash
    from anvil.project_bindings import requirement_descriptors

    origin = imported["content"].get("source_origin", {})
    if digest(imported["content"]) != imported["content_sha256"]:
        raise HTTPException(409, "Imported source projection integrity failed")
    product_mode = bool(imported["content"]["tasks"]) and all(task.get("case_selector", {}).get("field") == "product"
                                                            for task in imported["content"]["tasks"])
    if (origin.get("kind") != "praxis_authored_batch"
            or not (product_mode or imported["content"].get("case_dataset"))):
        raise HTTPException(
            409, "This native package path requires an imported reusable KYC dataset"
        )
    selected, missing = [], []
    for task in imported["content"]["tasks"]:
        rows = c.execute(
            "SELECT t.*,r.package_key,r.version,r.package_sha256 FROM anvil.praxis_resolved_tasks t JOIN anvil.praxis_export_resolutions r ON r.id=t.resolution_id AND r.project_id=t.project_id WHERE t.project_id=%s AND r.batch_key=%s AND t.task_key=%s AND t.revision=%s AND t.private_reference_sha256=%s AND t.binding->>'source_sha256'=%s ORDER BY t.created_at DESC,t.id DESC",
            (
                project,
                origin["batch_id"],
                task["task_id"],
                task["revision_id"],
                task["payload_sha256"],
                source_hash(),
            ),
        ).fetchall()
        row = next(
            (
                r
                for r in rows
                if {"id": r["package_key"], "version": r["version"], "sha256": r["package_sha256"]}
                in origin["packages"]
                and r["binding"].get("template_sha256") == task["source"]["template"]["sha256"]
            ),
            None,
        )
        if row is None:
            missing.append(
                {
                    "code": "AV_TASK_RESOLUTION_REQUIRED",
                    "owner": "anvil",
                    "task_id": task["task_id"],
                }
            )
        else:
            selected.append((task, row))
    if missing:
        raise HTTPException(409, {"anvil_requirements": missing})
    from anvil.project_bindings import current as current_binding
    from anvil.project_inputs import execution_overlay

    selected_binding = current_binding(c, project, imported["id"]) if not product_mode else None
    execution_data = (
        selected_binding["snapshot"].get("execution_data") if selected_binding else None
    )
    overlay = execution_overlay(c, project, execution_data) if execution_data else None
    packages = []
    for task, row in selected:
        package = prepare(
            c, project, user, row["id"], max_model_calls, execution_data=execution_data, resolved_input=resolved_input
        )
        packages.append(package | {"task_id": task["task_id"], "title": task["title"]})
    stored = [
        one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (p["package_id"],))
        for p in packages
    ]
    assignments = task_set_assignments(c, project, stored)
    if product_mode:
        from anvil.golden_kyc_product_context import load as product_context

        full_input = product_context(c, project, selected[0][1], resolved_input)
        expected_count = full_input["body"]["input_count"]
    else:
        expected_count = overlay["selected_count"] if overlay else imported["content"]["case_dataset"]["case_count"]
    expected_tasks = len(imported["content"]["tasks"]) if product_mode else 5
    if (product_mode and not 1 <= expected_tasks <= 4) or len(packages) != expected_tasks or len(assignments) != expected_count:
        raise HTTPException(
            409, "Native preparation must preserve the approved task population and complete shared input"
        )
    native = packages[0]["native_binding"]
    imported_runtime = one(
        c,
        "SELECT manifest,environment_id FROM banking.anvil_imports WHERE project_id=%s AND id=%s",
        (project, native["import_id"]),
    )
    library = imported_runtime["manifest"]["evaluators"]
    environment = one(
        c,
        "SELECT id,manifest_sha256 FROM anvil.environment_versions WHERE id=%s",
        (imported_runtime["environment_id"],),
    )
    by_id = {e["requirement"]: e for e in library if e["kind"] == "rubric"}
    refs = []
    for criterion in requirement_descriptors(c, imported)["rubric_criteria"]:
        evaluator = by_id.get(criterion["criterion_id"])
        if not evaluator:
            raise HTTPException(
                409,
                {
                    "code": "AV_EVALUATOR_BINDING_REQUIRED",
                    "owner": "anvil",
                    "target": criterion["target"],
                },
            )
        refs.append(
            {
                "kind": "evaluator",
                "id": evaluator["configuration_id"],
                "sha256": evaluator["configuration_sha256"],
                "target": criterion["target"],
            }
        )
    return {
        "packages": packages,
        "task_count": len(packages),
        "case_dataset": imported["content"].get("case_dataset"),
        **({"resolved_input": resolved_input} if product_mode else {}),
        "case_count": len(assignments),
        "execution_data": overlay,
        "shared_environment": True,
        "shared_evaluator_count": len(library),
        "restored_workflow_refs": [
            {
                "kind": "package",
                "id": p["package_id"],
                "sha256": p["package_sha256"],
                "target": "task:" + p["task_id"],
            }
            for p in packages
        ],
        "restored_rubric_refs": refs,
        "restored_data_refs": [
            {
                "kind": "environment",
                "id": str(environment["id"]),
                "sha256": environment["manifest_sha256"],
                "target": "shared-case-data-and-environment",
            }
        ],
        "restoration_origin": "exact_package_bindings_not_AI_recommendations",
        "run_authority": "not_granted",
        "model_calls": 0,
    }


def requalification_inputs(c, project, imported):
    """Use Anvil's retained source; never demand a new author revision for code updates."""
    from anvil.benchmark_storage import read_private, stage_private
    from anvil.praxis_case_registry import lookup as dataset_lookup
    from anvil.praxis_generic_export import validate
    from anvil.praxis_template_registry import lookup

    origin = imported["content"].get("source_origin", {})
    if origin.get("kind") != "praxis_authored_batch":
        raise HTTPException(409, "Imported authored-task batch required")
    if not one(
        c,
        "SELECT anvil.benchmark_private_access(%s,'benchmark_eval',NULL::uuid) AS allowed",
        (project,),
    )["allowed"]:
        raise HTTPException(403, "Current private source-review assignment required")
    rows = c.execute(
        "SELECT * FROM anvil.praxis_project_intakes WHERE project_id=%s AND batch_key=%s ORDER BY part_index",
        (project, origin["batch_id"]),
    ).fetchall()
    if len(rows) != len(origin["packages"]) or not 1 <= len(rows) <= 20:
        raise HTTPException(409, "Complete retained source batch required")
    prepared, problems = [], []
    for row in rows:
        if {
            "id": row["package_key"],
            "version": row["package_version"],
            "sha256": row["package_sha256"],
        } not in origin["packages"]:
            raise HTTPException(409, "Retained source identity changed")
        raw = read_private(c, row["private_archive_id"])
        result, parsed = validate(
            raw, lambda ref: lookup(c, project, ref), lambda ref: dataset_lookup(c, project, ref)
        )
        if result["valid"] is not True or result["anvil_requirements"]:
            problems.append({"package_id": row["package_key"], "validation": result})
        else:
            prepared.append(
                (result, parsed, stage_private(project, raw, "benchmark_eval", "application/zip"))
            )
    if problems:
        raise HTTPException(
            409, {"code": "AV_REQUALIFICATION_REQUIRED", "owner": "anvil", "packages": problems}
        )
    return prepared
