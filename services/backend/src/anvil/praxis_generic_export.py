"""Read-only generic conformance, projection and hash checks; private input is ephemeral."""

import io
import stat
import zlib
from copy import deepcopy
from datetime import date
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

from pydantic import ValidationError

from anvil.dataset_export_contract import pointer
from anvil.praxis_generic_contract import (
    EXPORT,
    EXPORT_V2,
    PRIVATE_VISIBILITIES,
    CampaignExport,
    Export,
    ReusableExport,
    TemplateSpec,
    digest,
    load,
    path,
    schema_errors,
    weight_bps,
)


def read_archive(raw):
    if len(raw) > 1048576:
        raise ValueError("Archive compressed limit")
    files, names, size = {}, set(), 0
    with ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.infolist()) > 1200:
            raise ValueError("Archive entry limit")
        for item in archive.infolist():
            path(item.filename)
            size += item.file_size
            if (
                size > 30 * 1048576
                or item.file_size > 10 * 1048576
                or item.filename.casefold() in names
                or stat.S_ISLNK(item.external_attr >> 16)
                or item.flag_bits & 1
                or item.compress_type not in (ZIP_STORED, ZIP_DEFLATED)
            ):
                raise ValueError("Unsafe archive entry")
            names.add(item.filename.casefold())
            with archive.open(item) as stream:
                content = stream.read(item.file_size + 1)
            if len(content) != item.file_size:
                raise ValueError("Archive integrity")
            files[item.filename] = content
    return files


def actor_projection(form, authored):
    def public_fields(definitions, values):
        if not isinstance(values, dict):
            raise ValueError("Section object required")
        result = {}
        for field in definitions:
            key = field["key"]
            if (
                key not in values
                or field.get("visibility") in PRIVATE_VISIBILITIES
                or field["type"] == "criterion"
            ):
                continue
            value = values[key]
            if field["type"] == "policy_citation" and not field.get("itemFields"):
                # Praxis's built-in policy widget has private subfields even
                # without an explicit repeated-array itemFields declaration.
                # Only Praxis's four declared PUBLIC child fields may survive.
                # Binding fields, future extensions and unknown keys are private.
                if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                    raise ValueError("Typed policy citation items required")
                value = [
                    {
                        k: deepcopy(v)
                        for k, v in item.items()
                        if k in {"ruleId", "ruleVersion", "locator", "quote"}
                    }
                    for item in value
                ]
                if any(type(v) is not str for item in value for v in item.values()):
                    raise ValueError("Public policy citation fields must be strings")
            if field.get("itemFields"):
                if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                    raise ValueError("Typed repeated items required at actor boundary")
                value = [public_fields(field["itemFields"], item) for item in value]
            result[key] = deepcopy(value)
        return result

    sections = {}
    source = authored.get("sections", {})
    for section in form["sections"]:
        value = public_fields(section.get("fields", []), source.get(section["key"], {}))
        if value:
            sections[section["key"]] = value
    result = {
        "profile": {"id": form["profileId"], "version": form["version"]},
        "title": authored.get("header", {}).get("title", source.get("S1", {}).get("title", "")),
        "sections": sections,
    }
    if authored.get("workflowGraph") is not None:
        graph = deepcopy(authored["workflowGraph"])
        # Graph source must itself conform to a published public graph contract;
        # unexpected private fields are rejected rather than projected.
        result["workflowGraph"] = graph
    return result


def validate(raw, lookup, dataset_lookup=None):
    errors, needs, reviews, parsed = [], [], [], []
    manifest = None
    files = {}

    def issue(code, file, parts, message, fix):
        item = {
            "code": code,
            "owner": "praxis",
            "file": file,
            "pointer": pointer(parts) if parts else "",
            "message": message,
            "fix": fix,
            "retryable": False,
        }
        if item not in errors:
            errors.append(item)

    def need(code, task=None):
        item = {"code": code, "owner": "anvil", "status": "blocked"}
        if task:
            item["task_id"] = task
        if item not in needs:
            needs.append(item)

    def parse(filename):
        if filename not in files:
            issue(
                "PX_FILE_MISSING",
                filename,
                (),
                "Declared file is absent.",
                "Include the declared file at this path.",
            )
            return None
        try:
            return load(files[filename])
        except (ValueError, UnicodeError, RecursionError):
            issue(
                "PX_JSON_INVALID",
                filename,
                (),
                "File is not bounded JCS-compatible UTF-8 JSON.",
                "Use unique keys, finite JCS-compatible numbers and valid Unicode; no more than32 nesting levels.",
            )
            return None

    try:
        files = read_archive(raw)
    except (ValueError, OSError, EOFError, RuntimeError, BadZipFile, zlib.error):
        issue(
            "PX_ARCHIVE_INVALID",
            "",
            (),
            "Archive safety/integrity checks failed.",
            "Use a bounded STORE/DEFLATE ZIP with safe unique paths, no directory/symlink/encrypted entries.",
        )
    source = parse("praxis-export.json") if not errors else None
    if source is not None:
        from anvil.golden_kyc_v7_export import requested, validate_registered

        if requested(source):
            return validate_registered(raw, files, source, lookup)
    unknown = False
    if source is not None and source.get("schema_version") not in (None, EXPORT, EXPORT_V2):
        need("AV_EXPORT_CONTRACT_UNSUPPORTED")
        unknown = True
    elif source is not None:
        try:
            campaign = any(
                isinstance(task, dict)
                and isinstance(task.get("case_selector"), dict)
                and task["case_selector"].get("field") == "dataset"
                for task in source.get("tasks", [])
            )
            manifest_type = (
                (CampaignExport if campaign else ReusableExport)
                if source.get("schema_version") == EXPORT_V2
                else Export
            )
            manifest = manifest_type.model_validate(source)
        except ValidationError as exc:
            for error in exc.errors():
                issue(
                    "PX_MANIFEST_SCHEMA",
                    "praxis-export.json",
                    error["loc"],
                    "Manifest field violates the generic contract.",
                    "Follow the advertised schema; remove unknown fields and supply required typed fields.",
                )
    canonical_files = {}
    declared = {"praxis-export.json"}
    if source is not None:
        canonical_files["praxis-export.json"] = digest(source)
    dataset_binding = None
    if manifest:
        if isinstance(manifest, (ReusableExport, CampaignExport)):
            dataset_binding = dataset_lookup(manifest.case_dataset) if dataset_lookup else None
            if not dataset_binding:
                need("AV_CASE_DATASET_BINDING_REQUIRED")
            else:
                from anvil.praxis_case_dataset import CaseDataset

                if not dataset_binding["qualified"]:
                    need("AV_CASE_DATASET_QUALIFICATION_REQUIRED")
                from anvil.praxis_marketing_contract import CampaignDataset

                dataset = (
                    CampaignDataset if isinstance(manifest, CampaignExport) else CaseDataset
                ).model_validate(dataset_binding["manifest"])
                if dataset.reference() != manifest.case_dataset:
                    issue(
                        "PX_CASE_DATASET_REFERENCE",
                        "praxis-export.json",
                        ("case_dataset",),
                        "Dataset descriptor differs from Anvil's exact version.",
                        "Copy the complete descriptor unchanged from Anvil discovery, including its actual case count.",
                    )
                for index, item in enumerate(manifest.tasks):
                    try:
                        dataset.select(manifest.case_dataset, item.case_selector)
                    except ValueError:
                        issue(
                            "PX_CASE_SELECTOR_COUNTS",
                            "praxis-export.json",
                            ("tasks", index, "case_selector"),
                            "Selector count differs from actual dataset membership.",
                            "Copy this state's count from the same exact Anvil dataset discovery version.",
                        )
            selectors = [item.case_selector.value for item in manifest.tasks]
            if isinstance(manifest, ReusableExport) and set(selectors) != {
                "CA",
                "NY",
                "TX",
                "FL",
                "IL",
            }:
                issue(
                    "PX_CASE_SELECTOR_PARTITION",
                    "praxis-export.json",
                    ("tasks",),
                    "Reusable KYC needs exactly one task for each of the five states.",
                    "Export CA, NY, TX, FL and IL once each; cases do not create additional tasks.",
                )
            if (
                sum(item.case_selector.case_count for item in manifest.tasks)
                != manifest.case_dataset.case_count
            ):
                issue(
                    "PX_CASE_SELECTOR_COUNTS",
                    "praxis-export.json",
                    ("case_dataset", "case_count"),
                    "Selector counts do not partition the selected dataset count.",
                    "Copy dataset and per-state counts from the same Anvil discovery version.",
                )
        if (
            manifest.execution != {"location": "anvil_only", "paid_calls": False}
            or manifest.execution.get("paid_calls") is not False
        ):
            issue(
                "PX_MANIFEST_SCHEMA",
                "praxis-export.json",
                ("execution",),
                "Execution must remain Anvil-only with paid calls false.",
                "Use only location:anvil_only and the JSON Boolean paid_calls:false.",
            )
        task_ids, references = set(), set()
        for index, entry in enumerate(manifest.tasks):
            root = ("tasks", index)
            if entry.task_id in task_ids:
                issue(
                    "PX_DUPLICATE_ID",
                    "praxis-export.json",
                    (*root, "task_id"),
                    "Task ID repeats in this package.",
                    "Export each selected task once.",
                )
            task_ids.add(entry.task_id)
            values = {}
            refs = [
                ("form", entry.form),
                ("actor", entry.actor),
                ("private", entry.private_assets[0]),
            ]
            for kind, ref in refs:
                try:
                    path(ref.path)
                except ValueError:
                    issue(
                        "PX_MANIFEST_SCHEMA",
                        "praxis-export.json",
                        (*root, kind),
                        "Unsafe file path.",
                        "Use safe relative paths in the declared contract layout.",
                    )
                    continue
                if (
                    kind == "actor"
                    and ref.path != f"tasks/{entry.task_id}/actor.json"
                    or kind == "private"
                    and ref.path != f"private/{entry.task_id}/reference.json"
                    or kind == "form"
                    and not ref.path.startswith("forms/")
                ):
                    issue(
                        "PX_MANIFEST_SCHEMA",
                        "praxis-export.json",
                        (*root, kind),
                        "File is outside the required visibility layout.",
                        "Use forms/, tasks/<id>/actor.json and private/<id>/reference.json.",
                    )
                if kind != "form" and ref.path in references:
                    issue(
                        "PX_DUPLICATE_ID",
                        "praxis-export.json",
                        (*root, kind),
                        "Task asset is reused by another task.",
                        "Use a separate actor/reference path per task.",
                    )
                references.add(ref.path)
                declared.add(ref.path)
                value = parse(ref.path)
                if value is not None:
                    canonical_files[ref.path] = digest(value)
                    values[kind] = value
                    if digest(value) != ref.sha256:
                        issue(
                            "PX_HASH_MISMATCH",
                            "praxis-export.json",
                            (*root, kind, "sha256"),
                            "Canonical file hash differs.",
                            "Hash the exact JSON object using RFC8785 then SHA256.",
                        )
            resolved = lookup(entry.template)
            if resolved is None:
                need("AV_TEMPLATE_NOT_REGISTERED", entry.task_id)
                unknown = True
                continue
            if resolved.get("integrity", True) is not True:
                need("AV_TEMPLATE_INTEGRITY_REQUIRED", entry.task_id)
                unknown = True
                continue
            spec_raw = resolved["row"]["spec"]
            spec = TemplateSpec.model_validate(spec_raw)
            reusable = spec.execution.schema_version == "anvil.template-execution.v2"
            campaign = spec.execution.schema_version == "anvil.template-execution.v3"
            if reusable != isinstance(manifest, ReusableExport) or campaign != isinstance(
                manifest, CampaignExport
            ):
                issue(
                    "PX_TASK_MODE_CONTRACT",
                    "praxis-export.json",
                    (*root, "template"),
                    "Template execution mode and export contract differ.",
                    "Use export v2 with five state selectors for KYC or one whole-dataset MULTI selector for Marketing; preserve legacy tasks under v1.",
                )
            if values.get("form") is not None and digest(values["form"]) != digest(
                spec_raw["authoring"]["profile"]
            ):
                issue(
                    "PX_TEMPLATE_REFERENCE_MISMATCH",
                    entry.form.path,
                    (),
                    "Form differs from the exact registered template version.",
                    "Export the published form bound to the template receipt; do not edit it during export.",
                )
            if not resolved["qualified"]:
                need(
                    "AV_TEMPLATE_QUALIFICATION_REVOKED"
                    if resolved["revoked"]
                    else "AV_TEMPLATE_NOT_QUALIFIED",
                    entry.task_id,
                )
            if not all(k in values for k in ("form", "actor", "private")):
                continue
            private = values["private"]
            if (
                private.get("access") != "private_rubric"
                or private.get("purpose") != "grader_only_reference_and_rubric"
                or not isinstance(private.get("authored"), dict)
            ):
                issue(
                    "PX_PRIVATE_EXPECTATION_MISSING",
                    entry.private_assets[0].path,
                    (),
                    "A classified grader-only authored reference is required.",
                    "Include purpose, access:private_rubric and the complete authored record.",
                )
                continue
            authored = private["authored"]
            if reusable and isinstance(manifest, ReusableExport):
                reusable_task_check(spec, entry, authored, issue)
                # Membership, installed environment and policy qualification are
                # Anvil responsibilities; an opaque reference is not runtime proof.
            try:
                self_check(spec, entry, authored, values["actor"], issue, need)
            except (TypeError, ValueError, AttributeError):
                issue(
                    "PX_FIELD_TYPE",
                    entry.private_assets[0].path,
                    ("authored",),
                    "Authored structure violates the published field contract.",
                    "Use the published field types and reference structures without coercion.",
                )
            if (
                entry.review.get("status") != "approved"
                or entry.review.get("revision_id") != entry.revision_id
                or not isinstance(entry.review.get("receipt_ref"), str)
            ):
                issue(
                    "PX_SOURCE_REVIEW_REQUIRED",
                    "praxis-export.json",
                    (*root, "review"),
                    "Praxis acceptance provenance must bind this exact revision.",
                    "Export an approved task and its opaque review receipt; do not include personnel data.",
                )
            parsed.append(
                {"entry": entry, "actor": values["actor"], "private": private, "template": resolved}
            )
        for filename in sorted(set(files) - declared):
            issue(
                "PX_UNDECLARED_FILE",
                filename,
                (),
                "Undeclared file in execution package.",
                "Remove extra files or declare supported assets; never upload code or credentials.",
            )
    valid = False if errors else None if unknown else True
    if manifest:
        reviews = [
            {"code": "REVIEW_DOMAIN_SIGNOFF", "owner": "human_review", "status": "pending"},
            {"code": "REVIEW_DATA_RIGHTS", "owner": "human_review", "status": "pending"},
            {"code": "REVIEW_CASE_EXPECTATIONS", "owner": "human_review", "status": "pending"},
        ]
    package_hash = (
        digest({"manifest": source, "files": dict(sorted(canonical_files.items()))})
        if manifest
        else None
    )
    result = {
        "schema_version": "anvil.generic-export-validation.v1",
        "contract": manifest.schema_version
        if manifest
        else source.get("schema_version", EXPORT)
        if source
        else EXPORT,
        "valid": valid,
        "status": "export_invalid"
        if errors
        else "validation_blocked"
        if unknown
        else "export_valid",
        "errors": errors,
        "error_count": len(errors),
        "errors_truncated": False,
        "anvil_requirements": needs,
        "review_gates": reviews,
        "package_sha256": package_hash,
        "validation_coverage": "incomplete"
        if unknown
        else "registered_template_conformance"
        if manifest
        else "not_evaluated",
        "run_authority": "not_granted",
        "paid_calls": False,
    }
    return result, {
        "manifest": manifest,
        "tasks": parsed,
        "files": files,
        "case_dataset_binding": dataset_binding,
    }


def reusable_task_check(spec, entry, authored, issue):
    """Author-fixable state/policy shape only; never provision or approve policy."""
    from anvil.praxis_case_dataset import PolicyRef

    filename = entry.private_assets[0].path
    sections = authored.get("sections", {})
    state = sections.get("S1", {}).get("governingState")
    if state != entry.case_selector.value:
        issue(
            "PX_CASE_SELECTOR_MISMATCH",
            filename,
            ("authored", "sections", "S1", "governingState"),
            "Authored state and exported state selector differ.",
            "Export this task with the selector matching its reviewed governingState.",
        )
    forbidden = {
        "S1": {"applicationId", "applicationRevision", "scenarioSlot", "product"},
        "S2": {"evidence", "parties", "accountTerms", "knownGaps"},
        "S5": {"findings", "partyFindings", "followUps"},
        "S6": {"recommendation", "decisionFields"},
    }
    for section in spec.authoring["profile"]["sections"]:
        for field in section.get("fields", []):
            if field["key"] in forbidden.get(section["key"], set()):
                issue(
                    "PX_CASE_SPECIFIC_TASK",
                    entry.form.path,
                    ("sections", section["key"], field["key"]),
                    "The selected profile still authors application-specific facts or answers.",
                    "Use the corrected reusable state-task template; keep case facts and answers in the dataset.",
                )
    policies = sections.get("S4", {}).get("statePolicies")
    if not isinstance(policies, list) or not policies:
        issue(
            "PX_STATE_POLICY_REFERENCE",
            filename,
            ("authored", "sections", "S4", "statePolicies"),
            "State-task policy references are missing.",
            "Supply reviewed state policy ruleId, ruleVersion, locator and contentSha256 references.",
        )
        return
    seen = set()
    for index, item in enumerate(policies):
        try:
            reference = PolicyRef.model_validate(
                {
                    "id": item.get("ruleId"),
                    "version": item.get("ruleVersion"),
                    "publication_ref": item.get("locator"),
                    "content_sha256": item.get("contentSha256"),
                }
            )
            if reference.id in seen:
                raise ValueError("duplicate")
            seen.add(reference.id)
        except (ValueError, TypeError, AttributeError):
            issue(
                "PX_STATE_POLICY_REFERENCE",
                filename,
                ("authored", "sections", "S4", "statePolicies", index),
                "State policy reference is malformed or duplicates an ID.",
                "Use unique ruleId, a ruleVersion, locator and lowercase64hex contentSha256; Anvil qualifies policy content separately.",
            )


def self_check(spec, entry, authored, actor, issue, need):
    private_file = entry.private_assets[0].path
    sections = authored.get("sections", {})
    if authored.get("profile") != {
        "id": spec.authoring["profile"]["profileId"],
        "version": spec.authoring["profile"]["version"],
    }:
        issue(
            "PX_TEMPLATE_REFERENCE_MISMATCH",
            private_file,
            ("authored", "profile"),
            "Authored profile does not match the bound form.",
            "Export the accepted task under its exact template/form version.",
        )
    if (
        set(authored) - {"profile", "header", "sections", "workflowGraph"}
        or not isinstance(authored.get("header", {}), dict)
        or set(authored.get("header", {})) - {"title"}
    ):
        issue(
            "PX_PERSONAL_METADATA",
            private_file,
            ("authored",),
            "Only task content and opaque provenance belong in this export.",
            "Remove personnel/account metadata; keep only profile, title header, sections and an optional graph.",
        )
    if not isinstance(sections, dict):
        issue(
            "PX_REQUIRED_FIELD_MISSING",
            private_file,
            ("authored", "sections"),
            "Authored sections are missing.",
            "Include the complete accepted authored record.",
        )
        return
    if set(sections) - {"S" + str(i) for i in range(1, 9)}:
        issue(
            "PX_FIELD_UNKNOWN",
            private_file,
            ("authored", "sections"),
            "Unpublished authored section.",
            "Export only the published S1–S8 sections.",
        )

    def required(field):
        rule = field.get("required", False)
        if rule is True:
            return True
        if isinstance(rule, dict):
            for test in rule.get("anyOf", []):
                parts = test.get("field", "").split(".")
                value = sections.get(parts[0], {})
                for part in parts[1:]:
                    value = value.get(part) if isinstance(value, dict) else None
                if digest(value) == digest(test.get("equals")):
                    return True
        return False

    def check_fields(fields, values, location):
        known = {field["key"] for field in fields}
        if set(values) - known:
            issue(
                "PX_FIELD_UNKNOWN",
                private_file,
                location,
                "Source contains fields outside the published form.",
                "Export only the registered form fields; do not include personnel or hidden metadata.",
            )
        for field in fields:
            key, kind = field["key"], field["type"]
            value = values.get(key)
            at = (*location, key)
            if required(field) and (value is None or value == "" or value == []):
                issue(
                    "PX_REQUIRED_FIELD_MISSING",
                    private_file,
                    at,
                    "Required authored field is empty.",
                    "Complete this published form field before export.",
                )
            if value is None:
                continue
            matches = {
                "text": type(value) is str,
                "long_text": type(value) is str,
                "date": type(value) is str,
                "number": type(value) in (int, float),
                "pick_list": type(value) in (str, int, float, bool),
                "multi_select": isinstance(value, list),
                "repeated_array": isinstance(value, list),
                "criterion": isinstance(value, list),
                "evidence_record": isinstance(value, list),
                "policy_citation": isinstance(value, list),
                "tool_call": isinstance(value, list),
                "graph_binding": value is None or isinstance(value, (str, dict)),
            }
            invalid = not matches.get(kind, False)
            if kind == "date" and value:
                try:
                    invalid |= date.fromisoformat(value).isoformat() != value
                except (ValueError, TypeError):
                    invalid = True
            if kind == "number" and not invalid:
                invalid |= value < field.get("min", float("-inf")) or value > field.get(
                    "max", float("inf")
                )
            if kind == "pick_list" and field.get("options") and value != "":
                allowed = [
                    opt.get("value") if isinstance(opt, dict) else opt for opt in field["options"]
                ]
                invalid |= value not in allowed
            if invalid:
                issue(
                    "PX_FIELD_TYPE",
                    private_file,
                    at,
                    "Authored value violates its published field type or range.",
                    "Use the field's type, allowed values and bounds without coercion.",
                )
            if field.get("itemFields") and isinstance(value, list):
                for index, child in enumerate(value):
                    if isinstance(child, dict):
                        check_fields(field["itemFields"], child, (*at, index))
                    else:
                        issue(
                            "PX_FIELD_TYPE",
                            private_file,
                            (*at, index),
                            "Repeated item must be an object.",
                            "Use the published repeated-item fields.",
                        )

    for section in spec.authoring["profile"]["sections"]:
        values = sections.get(section["key"], {})
        if not isinstance(values, dict):
            issue(
                "PX_REQUIRED_FIELD_MISSING",
                private_file,
                ("authored", "sections", section["key"]),
                "Section must be an object.",
                "Use the published section structure.",
            )
            continue
        check_fields(section.get("fields", []), values, ("authored", "sections", section["key"]))
    sections = {k: v if isinstance(v, dict) else {} for k, v in sections.items()}
    try:
        projection = actor_projection(spec.authoring["profile"], authored)
        if digest(projection) != digest(actor):
            issue(
                "PX_PRIVATE_FIELD_EXPOSED",
                entry.actor.path,
                (),
                "Actor differs from the recomputed public projection.",
                "Regenerate the agent projection from the exact form; remove private reference/rubric fields and restore public fields.",
            )
    except (ValueError, TypeError, AttributeError):
        issue(
            "PX_PRIVATE_FIELD_EXPOSED",
            entry.actor.path,
            (),
            "Cannot verify actor visibility projection.",
            "Use a conforming authored record and published form.",
        )
    evidence = sections.get("S2", {}).get("evidence", [])
    evidence = evidence if isinstance(evidence, list) else []
    evidence_ids = {
        v.get("id") for v in evidence if isinstance(v, dict) and isinstance(v.get("id"), str)
    }
    if len(evidence_ids) != len(evidence):
        issue(
            "PX_EVIDENCE_REFERENCE",
            private_file,
            ("authored", "sections", "S2", "evidence"),
            "Evidence IDs are missing, malformed or repeated.",
            "Use unique stable string IDs for every evidence record.",
        )
    if spec.execution.schema_version == "anvil.template-execution.v3":
        marketing_self_check(spec, entry, authored, evidence_ids, issue, need)
        return
    calls = sections.get("S3", {}).get("recordedResponses", [])
    tools = {t.id: t for t in spec.execution.tools}
    call_ids, call_tools = set(), {}
    if not isinstance(calls, list):
        calls = []
        issue(
            "PX_TOOL_CALL_MISSING",
            private_file,
            ("authored", "sections", "S3", "recordedResponses"),
            "Recorded calls must be an array.",
            "Include each authored tool step's recorded call.",
        )
    for index, call in enumerate(calls):
        root = ("authored", "sections", "S3", "recordedResponses", index)
        if (
            not isinstance(call, dict)
            or not isinstance(call.get("id"), str)
            or call["id"] in call_ids
        ):
            issue(
                "PX_DUPLICATE_ID",
                private_file,
                root,
                "Recorded call needs a unique ID.",
                "Give every recorded call a distinct stable ID.",
            )
            continue
        call_ids.add(call["id"])
        call_tools[call["id"]] = call.get("tool")
        if isinstance(call.get("evidenceRef"), str):
            evidence_ids.add(call["evidenceRef"])
        tool = tools.get(call.get("tool")) if isinstance(call.get("tool"), str) else None
        if not tool:
            issue(
                "PX_TOOL_CALL_MISSING",
                private_file,
                root,
                "Recorded tool is not declared by the template.",
                "Use a tool from this execution profile or request a new template version.",
            )
            continue
        status = call.get("http_status", 200)
        if (
            status not in (200, 202, 429, 503)
            or status == 202
            and not tool.pending
            or status in (429, 503)
            and status not in tool.error_statuses
        ):
            issue(
                "PX_TOOL_CALL_SCHEMA",
                private_file,
                root,
                "Recorded service status is not declared by the tool contract.",
                "Use declared completed/pending429/503 behavior; do not infer an accepted call from a timeout.",
            )
        response_schema = tool.error_schema if status in (429, 503) else tool.output_schema
        for field, schema in (("arguments", tool.input_schema), ("response", response_schema)):
            for bad in schema_errors(call.get(field), schema):
                issue(
                    "PX_TOOL_CALL_SCHEMA",
                    private_file,
                    (*root, field),
                    "Recorded call violates the bound tool schema.",
                    "Correct the typed arguments/response according to the template schema.",
                )
    steps = sections.get("S5", {}).get("steps", [])
    for index, step in enumerate(steps if isinstance(steps, list) else []):
        if (
            spec.execution.schema_version == "anvil.template-execution.v2"
            and isinstance(step, dict)
            and step.get("tool")
        ):
            if step["tool"] not in tools:
                issue(
                    "PX_TOOL_CALL_MISSING",
                    private_file,
                    ("authored", "sections", "S5", "steps", index, "tool"),
                    "Procedure references a tool outside the template's declared runtime.",
                    "Select a declared environment tool; application-specific responses are captured during each run.",
                )
            continue
        if (
            isinstance(step, dict)
            and step.get("tool")
            and (
                not isinstance(step.get("toolCallId"), str)
                or step.get("toolCallId") not in call_ids
                or call_tools.get(step.get("toolCallId")) != step.get("tool")
            )
        ):
            issue(
                "PX_TOOL_CALL_MISSING",
                private_file,
                ("authored", "sections", "S5", "steps", index),
                "Tool step lacks a recorded call.",
                "Bind this step's toolCallId to an existing recorded response.",
            )
    rules = {(r.id, r.version) for r in spec.execution.rules}
    citations = sections.get("S4", {}).get("policies", [])
    for index, citation in enumerate(citations if isinstance(citations, list) else []):
        if (
            not isinstance(citation, dict)
            or not isinstance(citation.get("ruleId"), str)
            or not isinstance(citation.get("ruleVersion"), str)
            or (citation.get("ruleId"), citation.get("ruleVersion")) not in rules
        ):
            issue(
                "PX_POLICY_REFERENCE",
                private_file,
                ("authored", "sections", "S4", "policies", index),
                "Rule citation does not resolve to a bound published version.",
                "Select the exact rule ID/version from this template's rule catalogue.",
            )
    criteria = sections.get("S7", {}).get("criteria", [])
    weights, ids, critical = [], set(), False
    mappings = {v.criterion_id: v for v in spec.execution.evaluators}
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 100:
        criteria = []
        issue(
            "PX_CRITERIA_WEIGHTS",
            private_file,
            ("authored", "sections", "S7", "criteria"),
            "One to100 rubric criteria required.",
            "Supply the authored rubric with stable IDs and weights totalling100.",
        )
    for index, criterion in enumerate(criteria):
        root = ("authored", "sections", "S7", "criteria", index)
        if not isinstance(criterion, dict):
            issue(
                "PX_CRITERIA_WEIGHTS",
                private_file,
                root,
                "Criterion must be an object.",
                "Use the published criterion widget structure.",
            )
            continue
        cid = criterion.get("id")
        if not isinstance(cid, str) or cid in ids:
            issue(
                "PX_DUPLICATE_ID",
                private_file,
                root,
                "Criterion ID is missing or repeated.",
                "Use unique stable criterion IDs.",
            )
        else:
            ids.add(cid)
        cid = cid if isinstance(cid, str) else None
        if cid not in mappings:
            need("AV_EVALUATOR_BINDING_REQUIRED", entry.task_id)
        try:
            weights.append(weight_bps(criterion.get("weight")))
        except ValueError:
            issue(
                "PX_CRITERIA_WEIGHTS",
                private_file,
                (*root, "weight"),
                "Weight must be positive with at most two decimals.",
                "Use numeric weights totalling exactly100.",
            )
        if not all(
            isinstance(criterion.get(key), str) and criterion[key].strip()
            for key in ("passCondition", "partialCredit", "failCondition")
        ):
            issue(
                "PX_CRITERIA_ANCHORS",
                private_file,
                root,
                "Explicit5/2/0 conditions are incomplete.",
                "Supply passCondition(5), partialCredit(2) and failCondition(0); Anvil will not invent an anchor.",
            )
        if type(criterion.get("critical")) is not bool:
            issue(
                "PX_FIELD_TYPE",
                private_file,
                (*root, "critical"),
                "Critical flag must be a JSON Boolean.",
                "Use true or false, not a number or string.",
            )
        critical |= criterion.get("critical") is True
        refs = criterion.get("evidenceRefs")
        if (
            not isinstance(refs, list)
            or any(ref not in evidence_ids for ref in refs if isinstance(ref, str))
            or any(not isinstance(ref, str) for ref in refs)
        ):
            issue(
                "PX_EVIDENCE_REFERENCE",
                private_file,
                (*root, "evidenceRefs"),
                "Criterion references missing evidence.",
                "Use existing evidence IDs or recorded response evidence IDs.",
            )
        mapping = mappings.get(cid)
        if mapping and (
            criterion.get("evaluatorKind") != mapping.capability.id
            or criterion.get("evaluatorVersion") != mapping.capability.version
        ):
            issue(
                "PX_EVALUATOR_REFERENCE",
                private_file,
                root,
                "Criterion evaluator ID/version differs from the bound execution mapping.",
                "Copy evaluatorKind and evaluatorVersion from this criterion's published execution binding.",
            )
        if (
            mapping
            and mapping.evidence_source == "output"
            and (not criterion.get("outputField") or "expectedValue" not in criterion)
        ):
            issue(
                "PX_PRIVATE_EXPECTATION_MISSING",
                private_file,
                root,
                "Output-reference criterion needs a private expected value and output field.",
                "Complete private expectedValue/outputField; never put the answer in actor.json.",
            )
        elif mapping and mapping.evidence_source == "output":
            field = criterion.get("outputField")
            output_fields = spec.execution.output_schema.get("properties", {})
            if (
                not isinstance(field, str)
                or field not in output_fields
                or schema_errors(criterion["expectedValue"], output_fields[field])
            ):
                issue(
                    "PX_PRIVATE_EXPECTATION_MISSING",
                    private_file,
                    root,
                    "Private output reference does not satisfy the bound output field schema.",
                    "Use an existing output field and a private expected value of its declared type.",
                )
            elif "partialValues" in criterion and (
                not isinstance(criterion["partialValues"], list)
                or len(criterion["partialValues"]) > 100
                or any(schema_errors(v, output_fields[field]) for v in criterion["partialValues"])
            ):
                issue(
                    "PX_PRIVATE_EXPECTATION_MISSING",
                    private_file,
                    root,
                    "Explicit partial-credit reference values violate the output schema.",
                    "Use a bounded private partialValues array of typed accepted alternatives; prose is never inferred.",
                )
    if sum(weights) != 10000 or not critical:
        issue(
            "PX_CRITERIA_WEIGHTS",
            private_file,
            ("authored", "sections", "S7", "criteria"),
            "Weights must total100 and at least one criterion must be critical.",
            "Correct weights and mark the template-required critical criterion.",
        )
    if entry.agent_mode == "MULTI" or authored.get("workflowGraph"):
        need("AV_GRAPH_RUNTIME_UNQUALIFIED", entry.task_id)
        graph_check(authored.get("workflowGraph"), entry, issue)


def marketing_self_check(spec, entry, authored, evidence_ids, issue, need):
    """Distinct 0–4/campaign checks; no KYC anchors or recorded service answers."""
    from anvil.marketing_task2_contract import GROUPS
    from anvil.praxis_marketing_contract import fingerprint
    from anvil.praxis_marketing_contract import graph_check as marketing_graph_check

    filename = entry.private_assets[0].path

    def bad(code, parts, message, fix):
        issue(code, filename, ("authored", *parts), message, fix)

    if entry.agent_mode != "MULTI" or entry.case_selector.field != "dataset":
        bad(
            "PX_TASK_MODE_CONTRACT",
            (),
            "One reusable MULTI campaign with a whole-dataset selector is required.",
            "Export one five-role task; cases and weeks do not create more tasks.",
        )
    graph = authored.get("workflowGraph", spec.execution.workflow_graph)
    try:
        marketing_graph_check(graph)
        if fingerprint(graph) != spec.execution.workflow_graph_sha256:
            raise ValueError("Published graph changed")
    except ValueError:
        bad(
            "PX_GRAPH_REFERENCE",
            ("workflowGraph",),
            "Workflow graph differs from the exact published Marketing protocol.",
            "Use the unchanged five-role graph and its source hash; Task3 remains external and approvals simulated.",
        )
    sections = authored["sections"]
    mappings = {x.criterion_id: x for x in spec.execution.evaluators}
    criteria = sections.get("S7", {}).get("criteria", [])
    ids, groups = [], dict.fromkeys(GROUPS, 0)
    for index, criterion in enumerate(criteria if isinstance(criteria, list) else []):
        at = ("sections", "S7", "criteria", index)
        if not isinstance(criterion, dict):
            bad(
                "PX_CRITERIA_ANCHORS",
                at,
                "Native criterion object required.",
                "Preserve the published criterion mapping, group, weight and anchors.",
            )
            continue
        identifier = criterion.get("id")
        ids.append(identifier)
        mapping = mappings.get(identifier)
        if (
            mapping is None
            or criterion.get("group") != mapping.group
            or criterion.get("weight") != mapping.weight
        ):
            bad(
                "PX_CRITERIA_WEIGHTS",
                at,
                "Criterion identity/group/weight differs from the native Marketing mapping.",
                "Preserve exact A1..G4 mappings and group weights; do not split groups or convert to KYC points.",
            )
        else:
            groups[mapping.group] += mapping.weight
        if not all(
            isinstance(criterion.get(key), str) and criterion[key].strip()
            for key in ("passCondition", "partialCredit", "failCondition")
        ):
            bad(
                "PX_CRITERIA_ANCHORS",
                at,
                "Explicit 4/2/0 reference anchors are required; levels1/3 remain optional.",
                "Supply passCondition(4), partialCredit(2), failCondition(0); never invent missing intermediate anchors.",
            )
        for key in ("level1", "level3"):
            if key in criterion and not isinstance(criterion[key], str):
                bad(
                    "PX_CRITERIA_ANCHORS",
                    (*at, key),
                    "Optional intermediate anchor must be text.",
                    "Keep a reviewed anchor or leave it absent.",
                )
        if mapping and (
            criterion.get("evaluatorKind") != mapping.capability.id
            or criterion.get("evaluatorVersion") != mapping.capability.version
        ):
            bad(
                "PX_EVALUATOR_REFERENCE",
                at,
                "Criterion evaluator differs from the exact Marketing capability.",
                "Copy the ID/version from this published native mapping.",
            )
        refs = criterion.get("evidenceRefs", [])
        if not isinstance(refs, list) or any(
            type(ref) is not str or ref not in evidence_ids for ref in refs
        ):
            bad(
                "PX_EVIDENCE_REFERENCE",
                (*at, "evidenceRefs"),
                "Criterion evidence reference does not resolve.",
                "Use an existing authored evidence identity; runtime evidence is collected by Anvil.",
            )
    if set(ids) != set(mappings) or len(ids) != len(set(ids)) or groups != GROUPS:
        bad(
            "PX_CRITERIA_WEIGHTS",
            ("sections", "S7", "criteria"),
            "Exactly23 native criterion mappings and original group totals are required.",
            "Restore the unchanged native rubric; this does not add authored tasks or application cases.",
        )
    need("AV_GRAPH_RUNTIME_UNQUALIFIED", entry.task_id)


def graph_check(graph, entry, issue):
    filename = entry.private_assets[0].path

    def bad(message, parts=()):
        issue(
            "PX_GRAPH_REFERENCE",
            filename,
            ("authored", "workflowGraph", *parts),
            message,
            "Use the published graph schema and resolve every role, node, edge and artifact reference.",
        )

    if not isinstance(graph, dict) or graph.get("schemaVersion") != "praxis.workflow_graph.v1":
        bad(
            "Published generic graph schema required; proposed/legacy schemas are not silently converted."
        )
        return
    if set(graph) - {
        "schemaVersion",
        "templateId",
        "templateVersion",
        "agentMode",
        "roles",
        "artifacts",
        "nodes",
        "edges",
        "loops",
        "limits",
    }:
        bad("Unexpected graph metadata/private fields are not actor material.")
    groups = {}
    for name, bound in (
        ("nodes", 100),
        ("edges", 300),
        ("roles", 30),
        ("artifacts", 100),
        ("loops", 20),
    ):
        items = graph.get(name, [])
        if (
            not isinstance(items, list)
            or len(items) > bound
            or any(
                not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in items
            )
        ):
            bad("Graph collection is malformed or exceeds its bound.", (name,))
            groups[name] = {}
            continue
        groups[name] = {item["id"]: item for item in items}
        if len(groups[name]) != len(items):
            bad("Duplicate graph ID.", (name,))
    allowed = {
        "id",
        "type",
        "label",
        "policyRuleVersionIds",
        "provides",
        "roleId",
        "instruction",
        "inputRefs",
        "outputArtifact",
        "requiredInputs",
        "optionalInputs",
        "question",
        "outcomes",
        "prompt",
        "actorRole",
        "responseSchema",
        "timeoutMinutes",
        "deliverable",
        "completionCondition",
        "permittedEvidence",
        "reason",
    }
    for nid, node in groups["nodes"].items():
        if (
            not isinstance(node.get("type"), str)
            or node.get("type")
            not in {"input", "agent_step", "decision", "join", "human_step", "output", "escalation"}
            or set(node) - allowed
        ):
            bad("Unsupported node type or private/unknown node field.", ("nodes",))
        if node.get("roleId") and (
            not isinstance(node["roleId"], str) or node["roleId"] not in groups["roles"]
        ):
            bad("Node role is unresolved.", ("nodes",))
        refs = node.get("inputRefs", [])
        if not isinstance(refs, list) or any(
            not isinstance(ref, str) or ref not in groups["artifacts"] for ref in refs
        ):
            bad("Node artifact input is unresolved.", ("nodes",))
        for key in ("requiredInputs", "optionalInputs"):
            values = node.get(key, [])
            if not isinstance(values, list) or any(
                not isinstance(v, str) or v not in groups["nodes"] for v in values
            ):
                bad("Join dependency is unresolved.", ("nodes",))
    for edge in groups["edges"].values():
        if (
            not isinstance(edge.get("from"), str)
            or not isinstance(edge.get("to"), str)
            or edge["from"] not in groups["nodes"]
            or edge["to"] not in groups["nodes"]
        ):
            bad("Edge endpoint is unresolved.", ("edges",))
    if (
        not isinstance(graph.get("limits"), dict)
        or type(graph["limits"].get("maxTransitions")) is not int
        or not 1 <= graph["limits"]["maxTransitions"] <= 10000
    ):
        bad("Bounded graph transitions are required.", ("limits",))
