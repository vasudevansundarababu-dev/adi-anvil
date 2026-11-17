"""Qualified application-type extension of the unchanged authored-export v1.

Selection requires an exact current registry qualification. A ZIP selector or a
version number alone never registers this extension or grants Run readiness.
"""

from pydantic import ValidationError

from anvil.golden_kyc_v7_candidate import (
    CandidateConformanceError,
    CandidateExport,
    PublishedVariant,
    decode_candidate,
)
from anvil.praxis_generic_contract import TemplateRef, canonical, digest, load


def product_template(spec):
    """Exact proposed v7-or-successor semantics, never legacy v6 migration."""
    if type(spec) is not dict or type(spec.get("version")) is not int or spec["version"] < 7:
        return False
    execution, authoring = spec.get("execution"), spec.get("authoring")
    if type(execution) is not dict or type(authoring) is not dict or type(authoring.get("template")) is not dict:
        return False
    selector = authoring["template"].get("caseSelector")
    return (execution.get("schema_version") == "anvil.template-execution.v2"
            and execution.get("environment", {}).get("id") == "golden-kyc-openenv-v2"
            and type(selector) is dict and selector.get("field") == "product"
            and selector.get("source") == "S1.applicationType"
            and type(selector.get("values")) is list
            and len(selector["values"]) == 4
            and all(type(value) is str for value in selector["values"])
            and set(selector["values"]) == {"individual", "adult_joint", "teen_joint", "custodial"})


def requested(source):
    return (type(source) is dict and source.get("schema_version") == "praxis.authored-task-export.v1"
            and type(source.get("tasks")) is list
            and any(type(task) is dict and type(task.get("case_selector")) is dict
                    and task["case_selector"].get("field") == "product" for task in source["tasks"]))


def qualified_variants(connection, project):
    """Advertise this additive shape only after exact current qualification."""
    from anvil.praxis_template_registry import lookup

    rows = connection.execute("SELECT template_key,version,spec_sha256 FROM anvil.praxis_template_versions "
                              "WHERE project_id=%s AND version>=7 AND spec#>>'{authoring,template,caseSelector,field}'='product' "
                              "AND spec#>>'{execution,environment,id}'='golden-kyc-openenv-v2' ORDER BY template_key,version LIMIT 21",
                              (project,)).fetchmany(21)
    if len(rows)>20:
        return []
    variants = []
    for row in rows:
        reference = TemplateRef(id=row["template_key"],version=row["version"],sha256=row["spec_sha256"])
        current = lookup(connection,project,reference)
        if current and current.get("qualified") and current.get("integrity") and product_template(current["row"]["spec"]):
            variants.append({"template":reference.model_dump(mode="json"),"selector_field":"product",
                             "qualification_receipt_sha256":current["qualification"]["receipt_sha256"]})
    return variants


def validate_registered(raw, files, source, lookup):
    errors, needs, variants, registered = [], [], [], {}
    manifest, decoded, tasks = None, None, []

    def need(code, task=None):
        value = {"code": code, "owner": "anvil", "status": "blocked"}
        if task:
            value["task_id"] = task
        if value not in needs:
            needs.append(value)

    def issue(parts, code="PX_MANIFEST_SCHEMA"):
        errors.append({"code": code, "owner": "praxis", "file": "praxis-export.json",
                       "pointer": "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts),
                       "message": "Package violates the exact published application workflow contract.",
                       "fix": "Export the approved exact revision and declared assets under its published form; preserve product selectors and immutable hashes.",
                       "retryable": False})

    try:
        manifest = CandidateExport.model_validate(source)
    except ValidationError as exc:
        for error in exc.errors():
            issue(error["loc"])
    if manifest:
        for entry in manifest.tasks:
            key = (entry.template.id, entry.template.version, entry.template.sha256)
            if key in registered:
                continue
            current = lookup(entry.template)
            registered[key] = current
            if not current or current.get("integrity", True) is not True:
                need("AV_TEMPLATE_INTEGRITY_REQUIRED" if current else "AV_TEMPLATE_NOT_REGISTERED", entry.task_id)
            elif not product_template(current["row"]["spec"]):
                need("AV_EXPORT_CONTRACT_UNSUPPORTED", entry.task_id)
            elif (current.get("qualified") is not True
                  or (current.get("qualification") or {}).get("receipt", {}).get("conformance", {}).get("export_selector_field") != "product"):
                need("AV_TEMPLATE_QUALIFICATION_REVOKED" if current.get("revoked") else "AV_TEMPLATE_NOT_QUALIFIED", entry.task_id)
            else:
                variants.append(PublishedVariant(TemplateRef.model_validate(entry.template.model_dump()),
                                                 current["qualification"]["receipt_sha256"], canonical(current["row"]["spec"])))
        if not needs:
            try:
                decoded = decode_candidate(raw, tuple(variants))
            except CandidateConformanceError as exc:
                errors.extend(exc.errors)
            except (ValueError, TypeError, KeyError, AttributeError):
                issue(("tasks",), "PX_PACKAGE_CONFORMANCE")
            if decoded:
                for code, task in decoded.anvil_requirements:
                    need(code, task)
                for entry in manifest.tasks:
                    tasks.append({"entry": entry, "actor": load(files[entry.actor.path]),
                                  "private": load(files[entry.private_assets[0].path]),
                                  "template": registered[(entry.template.id, entry.template.version, entry.template.sha256)]})
    unknown = decoded is None and not errors
    result = {
        "schema_version": "anvil.generic-export-validation.v1", "contract": "praxis.authored-task-export.v1",
        "valid": False if errors else None if unknown else True,
        "status": "export_invalid" if errors else "validation_blocked" if unknown else "export_valid",
        "errors": errors, "error_count": len(errors), "errors_truncated": False,
        "anvil_requirements": needs,
        "review_gates": [{"code": code, "owner": "human_review", "status": "pending"}
                         for code in ("REVIEW_DOMAIN_SIGNOFF", "REVIEW_DATA_RIGHTS", "REVIEW_CASE_EXPECTATIONS")],
        # Preserve the decoder's exact original ZIP fingerprint. It is not a
        # reference to a selected dataset, an authenticated review or a Run.
        "package_sha256": decoded.package_sha256 if decoded else None,
        "validation_coverage": "incomplete" if unknown else "registered_template_conformance" if decoded else "not_evaluated",
        "run_authority": "not_granted", "paid_calls": False,
    }
    return result, {"manifest": manifest, "tasks": tasks, "files": files,
                    "case_dataset_binding": None, "application_workflow": decoded,
                    "source_manifest_sha256": digest(source)}
