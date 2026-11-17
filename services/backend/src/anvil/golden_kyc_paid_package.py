"""Native planning package from a genuine resolved Praxis task; no Run authority.

Only public actor material enters the ordinary source/package registries. The
original authored reference ZIP remains in the protected benchmark vault.
"""

import hashlib
import io
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from fastapi import HTTPException

from anvil import artifacts
from anvil.db import Jsonb, audit, one, uid
from anvil.golden_kyc_anvil import source_hash, validate
from anvil.golden_kyc_paid_session import task_context
from anvil.praxis_generic_contract import canonical, digest

BINDING = "golden-kyc-openenv-tool-agent-v1"


def prepare(c, project, user, resolved_id, max_calls, *, execution_data=None, resolved_input=None):
    if type(max_calls) is not int or not 1 <= max_calls <= 100:
        raise HTTPException(422, "Select1–100 bounded model turns")
    resolved = one(
        c,
        "SELECT * FROM anvil.praxis_resolved_tasks WHERE project_id=%s AND id=%s",
        (project, resolved_id),
    )
    if not resolved:
        raise HTTPException(404, "Resolved task not found in this project")
    product_task = resolved.get("binding", {}).get("task_mode") == "reusable_application_workflow"
    reusable = resolved.get("binding", {}).get("case_context") or product_task
    if product_task:
        from anvil.golden_kyc_product_context import actor_context
        from anvil.golden_kyc_product_context import load as product_context

        if execution_data:
            raise HTTPException(409, "Prepare a new resolved input for changed product-task data")
        product = product_context(c, project, resolved, resolved_input)
        imported = product["import"]
        actor = actor_context(product, resolved["actor"])
        # Recheck the same current source/template path even for empty partitions.
        task_context(c, project, resolved_id, None, resolved_input=resolved_input)
        case_binding = {"task_mode": "reusable_application_workflow", "resolved_input": resolved_input,
                        "policy_scope": product["scope"].model_dump(mode="json"),
                        "case_selector": {"field": "product", "value": product["scope"].workflow_product},
                        "preparation_binding_id": str(product["scope"].project_binding_id),
                        "preparation_binding_sha256": product["scope"].project_binding_sha256}
    elif reusable:
        from anvil.praxis_case_dataset import CaseDataset, StateTaskContext
        from anvil.praxis_case_registry import lookup as dataset_lookup

        context = StateTaskContext.model_validate(reusable)
        dataset = dataset_lookup(c, project, context.caseDataset)
        if not dataset or not dataset["qualified"]:
            raise HTTPException(409, "Qualified state-task dataset binding required")
        members = CaseDataset.model_validate(dataset["manifest"]).select(
            context.caseDataset, context.caseSelector
        )
        actor = task_context(c, project, resolved_id, members[0].id)
        imported = dataset["import"]
        case_binding = {
            "task_mode": "reusable_state_workflow",
            "case_dataset": context.caseDataset.model_dump(),
            "case_selector": context.caseSelector.model_dump(),
            "case_context_sha256": resolved["binding"]["case_context_sha256"],
        }
    else:
        application = resolved["actor"].get("sections", {}).get("S1", {}).get("applicationId")
        if not isinstance(application, str):
            raise HTTPException(409, "Native assigned-application binding is required")
        actor = task_context(c, project, resolved_id, application)
        imported = one(
            c,
            "SELECT * FROM banking.anvil_imports WHERE project_id=%s AND manifest->>'source_sha256'=%s ORDER BY created_at DESC LIMIT 1",
            (project, source_hash()),
        )
    if not imported:
        raise HTTPException(409, "Current qualified Golden import required")
    validate(c, imported)
    if not reusable:
        snapshot = one(
            c,
            "SELECT snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s AND id=%s",
            (project, imported["pack_id"], application),
        )
        if not snapshot:
            raise HTTPException(409, "Assigned application is absent from the bound Golden pack")
        case_binding = {
            "application_id": application,
            "application_sha256": snapshot["snapshot_sha256"],
        }
    binding = {
        "resolved_task_id": str(resolved_id),
        "resolved_binding_sha256": resolved["binding_sha256"],
        **case_binding,
        "import_id": str(imported["id"]),
        "import_sha256": imported["manifest_sha256"],
        "pack_id": str(imported["pack_id"]),
        "runtime_sha256": source_hash(),
        "evaluator_sha256": digest(imported["manifest"]["evaluators"]),
    }
    if reusable:
        binding["template_sha256"] = resolved["binding"]["template_sha256"]
    if execution_data:
        from anvil.project_inputs import actor_overlay, execution_overlay

        if not reusable:
            raise HTTPException(409, "Execution input selection requires reusable state tasks")
        overlay = execution_overlay(c, project, execution_data)
        if overlay["family"] != "kyc" or not overlay["pack_id"]:
            raise HTTPException(409, "KYC populated execution input required")
        cases = [
            case
            for case in overlay["cases"]
            if case.get("governing_state") == context.caseSelector.value
        ]
        if cases:
            actor = task_context(
                c, project, resolved_id, cases[0]["id"], execution_data=execution_data
            )
        else:
            # Keep the reviewed task even when this input has no cases for it.
            actor = actor | {
                "execution_data": actor_overlay(overlay, context.caseSelector.value),
                "execution_partition_case_count": 0,
            }
        binding.update(
            execution_data=overlay["selection"],
            execution_data_sha256=digest(overlay),
            pack_id=overlay["pack_id"],
        )
    public_source = {
        "schema_version": "anvil.golden-native-public-source.v1",
        "task_id": resolved["task_key"],
        "praxis_revision_id": resolved["revision"],
        "actor": actor,
        "native_binding": binding,
    }
    if len(canonical(public_source)) > 524288:
        raise HTTPException(409, "Native public source exceeds the qualified planning bound")
    fingerprint = digest(public_source)
    revision = resolved["revision"] + ":anvil-native:" + resolved["binding_sha256"][:16]
    if product_task:
        revision += ":input:" + resolved_input["sha256"]
    if execution_data:
        revision += ":data:" + binding["execution_data_sha256"]
    source = one(
        c,
        "SELECT * FROM anvil.praxis_sources WHERE project_id=%s AND task_id=%s AND revision_id=%s",
        (project, resolved["task_key"], revision),
    )
    if source and source["source_sha256"] != fingerprint:
        raise HTTPException(409, "Immutable native source differs; resolve a new binding")
    if not source:
        source_artifact = artifacts.store(
            c, project, canonical(public_source), "actor", origin="adi_executed"
        )
        source = c.execute(
            "INSERT INTO anvil.praxis_sources(id,project_id,task_id,task_version,revision_id,source_sha256,source_artifact_id,actor_spec,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uid(),
                project,
                resolved["task_key"],
                "native-" + resolved["binding_sha256"][:12],
                revision,
                fingerprint,
                source_artifact,
                Jsonb(actor),
                user,
            ),
        ).fetchone()
    admission = {
        "schema_version": "anvil.golden-native-agent-admission.v1",
        "binding": BINDING,
        "runtime_sha256": source_hash(),
        "public_source_sha256": fingerprint,
        "run_authority": "not_granted",
        "provider_credential_to_worker": False,
        "private_reference_to_actor": False,
    }
    files = {"actor.json": canonical(actor), "anvil-agent/admission.json": canonical(admission)}
    manifest = {
        "schema_version": "anvil.golden-native-package.v1",
        "task_id": resolved["task_key"],
        "task_version": source["task_version"],
        "revision_id": revision,
        "praxis_revision_id": resolved["revision"],
        "source_sha256": fingerprint,
        "binding": BINDING,
        "compiler_version": source_hash(),
        "harbor_version": "0.25.0",
        "openenv_version": "0.12.0",
        "stage_order": ["turn-" + str(i) for i in range(max_calls)],
        "native_binding": binding,
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
        "run_authority": "not_granted",
    }
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as zipped:
        for name, raw in sorted((files | {"package-manifest.json": canonical(manifest)}).items()):
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            zipped.writestr(entry, raw)
    raw = buffer.getvalue()
    package_hash = hashlib.sha256(raw).hexdigest()
    package = one(
        c,
        "SELECT * FROM anvil.harbor_packages WHERE project_id=%s AND source_id=%s AND package_sha256=%s",
        (project, source["id"], package_hash),
    )
    if not package:
        artifact = artifacts.store(
            c, project, raw, "actor", mime="application/zip", origin="adi_executed"
        )
        package = c.execute(
            "INSERT INTO anvil.harbor_packages(id,project_id,source_id,package_sha256,package_artifact_id,manifest,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (uid(), project, source["id"], package_hash, artifact, Jsonb(manifest), user),
        ).fetchone()
        audit(
            c,
            project,
            user,
            "golden.native_planning_package_created",
            package["id"],
            {
                "resolved_task_id": str(resolved_id),
                "package_sha256": package_hash,
                "run_authority": "not_granted",
            },
        )
    return {
        "package_id": str(package["id"]),
        "package_sha256": package_hash,
        "source_id": str(source["id"]),
        "native_binding": binding,
        "max_model_calls": max_calls,
        "run_authority": "not_granted",
        "paid_calls": False,
    }


def assignments(c, project, binding, case_ids=None):
    """Derive episode assignments without putting other cases into actor files."""
    if binding.get("task_mode") == "reusable_application_workflow":
        from anvil.golden_kyc_product_context import assignment
        from anvil.golden_kyc_product_context import load as product_context

        resolved = one(c, "SELECT * FROM anvil.praxis_resolved_tasks WHERE project_id=%s AND id=%s",
                       (project, binding["resolved_task_id"]))
        if not resolved or resolved["binding_sha256"] != binding.get("resolved_binding_sha256"):
            raise HTTPException(409, "Exact resolved product task changed")
        context = product_context(c, project, resolved, binding.get("resolved_input"))
        imported = context["import"]
        if (binding.get("case_selector") != {"field": "product", "value": context["scope"].workflow_product}
                or binding.get("runtime_sha256") != source_hash()
                or binding.get("import_id") != str(imported["id"])
                or binding.get("import_sha256") != imported["manifest_sha256"]
                or binding.get("pack_id") != str(imported["pack_id"])
                or binding.get("evaluator_sha256") != digest(imported["manifest"]["evaluators"])
                or binding.get("template_sha256") != context["scope"].template.sha256
                or binding.get("preparation_binding_id") != str(context["scope"].project_binding_id)
                or binding.get("preparation_binding_sha256") != context["scope"].project_binding_sha256):
            raise HTTPException(409, "Exact product task/input/environment/evaluator binding changed")
        members = {row["application_id"] for row in context["members"]}
        selected = sorted(members) if case_ids is None else case_ids
        if len(selected) != len(set(selected)) or set(selected) - members:
            raise HTTPException(422, "Select unique applications in the exact product partition")
        if selected:
            task_context(c, project, binding["resolved_task_id"], selected[0], resolved_input=binding["resolved_input"])
        return [assignment(context, application) for application in selected]
    if binding.get("task_mode") != "reusable_state_workflow":
        if case_ids is not None:
            raise HTTPException(422, "Case selection requires a reusable state task")
        return None
    from anvil.praxis_case_dataset import CaseDataset, StateTaskContext
    from anvil.praxis_case_registry import lookup as dataset_lookup

    resolved = one(
        c,
        "SELECT * FROM anvil.praxis_resolved_tasks WHERE project_id=%s AND id=%s",
        (project, binding["resolved_task_id"]),
    )
    if not resolved or resolved["binding_sha256"] != binding["resolved_binding_sha256"]:
        raise HTTPException(409, "Resolved reusable state task changed")
    context = StateTaskContext.model_validate(resolved["binding"]["case_context"])
    dataset = dataset_lookup(c, project, context.caseDataset)
    if (
        not dataset
        or not dataset["qualified"]
        or binding.get("case_context_sha256") != digest(context.model_dump())
        or binding.get("case_dataset") != context.caseDataset.model_dump()
        or binding.get("case_selector") != context.caseSelector.model_dump()
        or binding.get("template_sha256") != resolved["binding"].get("template_sha256")
    ):
        raise HTTPException(409, "Current immutable state task and dataset binding required")
    imported = dataset["import"]
    if (
        str(imported["id"]) != binding.get("import_id")
        or imported["manifest_sha256"] != binding.get("import_sha256")
        or source_hash() != binding.get("runtime_sha256")
        or digest(imported["manifest"]["evaluators"]) != binding.get("evaluator_sha256")
    ):
        raise HTTPException(409, "Dataset environment or evaluator binding changed")
    data = CaseDataset.model_validate(dataset["manifest"])
    if binding.get("execution_data"):
        from anvil.project_inputs import execution_overlay, overlay_assignment

        overlay = execution_overlay(c, project, binding["execution_data"])
        if (
            digest(overlay) != binding.get("execution_data_sha256")
            or overlay["pack_id"] != binding["pack_id"]
            or overlay["family"] != "kyc"
        ):
            raise HTTPException(409, "Native execution input binding changed")
        members = [
            member
            for member in overlay["cases"]
            if member.get("governing_state") == context.caseSelector.value
        ]
        selected = [member["id"] for member in members] if case_ids is None else case_ids
        if len(selected) != len(set(selected)) or set(selected) - {
            member["id"] for member in members
        }:
            raise HTTPException(422, "Select unique applications in this state task's frozen input")
        if selected:
            task_context(
                c,
                project,
                binding["resolved_task_id"],
                selected[0],
                execution_data=binding["execution_data"],
            )
        return [overlay_assignment(context, overlay, application) for application in selected]
    if str(imported["pack_id"]) != binding.get("pack_id"):
        raise HTTPException(409, "Native default pack binding changed")
    members = data.select(context.caseDataset, context.caseSelector)
    selected = [m.id for m in members] if case_ids is None else case_ids
    if (
        not selected
        or len(selected) != len(set(selected))
        or set(selected) - {m.id for m in members}
    ):
        raise HTTPException(422, "Select unique case IDs belonging to this state task")
    task_context(c, project, binding["resolved_task_id"], selected[0])
    return [context.assignment(data, application) for application in selected]


def task_set_assignments(c, project, packages, case_ids=None):
    """Several state tasks share one execution group and one aggregate budget."""
    modes = {(p["manifest"].get("native_binding") or {}).get("task_mode") for p in packages}
    if "reusable_application_workflow" in modes:
        if modes != {"reusable_application_workflow"} or len(packages) != 4 or len({str(p["id"]) for p in packages}) != 4:
            raise HTTPException(422, "Select the four distinct reusable product-task packages")
        shared, products, members = None, set(), {}
        for package in packages:
            binding = package["manifest"]["native_binding"]
            reference = {key: binding.get(key) for key in ("resolved_input", "preparation_binding_id", "preparation_binding_sha256",
                         "import_id", "import_sha256", "runtime_sha256", "evaluator_sha256", "template_sha256", "pack_id")}
            product = binding["case_selector"]["value"]
            if (shared is not None and shared != reference) or product in products:
                raise HTTPException(409, "Product tasks must share the exact input, template, environment and evaluators")
            shared = reference
            products.add(product)
            for item in assignments(c, project, binding):
                if item["application_id"] in members:
                    raise HTTPException(409, "Application assigned to multiple product tasks")
                members[item["application_id"]] = item | {"package_id": str(package["id"])}
        if products != {"individual", "adult_joint", "teen_joint", "custodial"}:
            raise HTTPException(422, "All four original application product workflows required")
        selected = sorted(members) if case_ids is None else case_ids
        if not selected or len(set(selected)) != len(selected) or set(selected) - members.keys():
            raise HTTPException(422, "Select unique applications from the shared product-task input")
        return [members[key] for key in selected]
    if not 1 <= len(packages) <= 5 or len({str(p["id"]) for p in packages}) != len(packages):
        raise HTTPException(422, "Select unique state-task packages, at most five")
    reference, states, members = None, set(), {}
    for package in packages:
        binding = package["manifest"].get("native_binding") or {}
        if binding.get("task_mode") != "reusable_state_workflow":
            raise HTTPException(422, "A task set accepts only reusable state-task packages")
        shared = {
            k: binding.get(k)
            for k in (
                "case_dataset",
                "import_id",
                "import_sha256",
                "runtime_sha256",
                "evaluator_sha256",
                "template_sha256",
                "execution_data",
                "execution_data_sha256",
                "pack_id",
            )
        }
        if reference is not None and reference != shared:
            raise HTTPException(
                409,
                "State tasks must share one template, dataset, environment import and evaluator library",
            )
        reference = shared
        state = binding["case_selector"]["value"]
        if state in states:
            raise HTTPException(422, "Select one reusable task for each selected state")
        states.add(state)
        for assignment in assignments(c, project, binding):
            key = assignment["application_id"]
            if key in members:
                raise HTTPException(409, "Dataset case was assigned to multiple state tasks")
            members[key] = assignment | {"package_id": str(package["id"])}
    selected = sorted(members) if case_ids is None else case_ids
    if not selected or len(set(selected)) != len(selected) or set(selected) - members.keys():
        raise HTTPException(422, "Select unique case IDs covered by the selected state tasks")
    return [members[key] for key in selected]
