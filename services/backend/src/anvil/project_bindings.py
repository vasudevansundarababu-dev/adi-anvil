"""Persistent imported-Project selections; readiness never starts an execution.

No client-supplied ready flag, simulated result, arbitrary installer or inferred
legal approval is accepted. Release attestations are separate, privileged records.
"""

import os
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field, ValidationError, model_validator

from anvil import auth, evaluator_configurations, task_method_compatibility
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.project_input_contract import FrozenSelection
from anvil.schemas import Strict
from anvil.skill_step_bindings import SkillMapping
from anvil.task_safety_sources import SourceReference
from anvil.workspace import READ_ROLES

SECTIONS = ("workflow", "policy", "data", "rubric", "safety")
SHA = r"^[a-f0-9]{64}$"
MAX_REQUIREMENTS = 300


def evaluator_options(c):
    """Catalogue current statuses with one lexical byte proof, never cached authority."""
    from anvil.software_resource_proof import software_resources

    result = []
    with c.transaction():
        with software_resources(c) as proof:
            for item in c.execute(
                "SELECT id,adapter FROM anvil.evaluator_configurations ORDER BY created_at DESC,id LIMIT 300"
            ).fetchall():
                row = evaluator_configurations.get(
                    c, item["id"],
                    **({"_resource_proof": proof} if item["adapter"] in {"builtin", "zen", "opa-local"} else {}),
                )
                result.append({"id": row["id"], "name": row["name"], "adapter": row["adapter"],
                               "sha256": row["configuration_sha256"], "status": row["status"]})
    return result


class Reference(Strict):
    kind: Literal[
        "revision",
        "artifact",
        "evaluator",
        "environment",
        "framework",
        "policy_set",
        "policy_mapping",
        "package",
        "custom_python",
    ]
    id: UUID
    sha256: str = Field(pattern=SHA)
    target: str = Field(min_length=1, max_length=200)


class SafetyPrompt(Strict):
    id: str = Field(min_length=1, max_length=120)
    sha256: str = Field(pattern=SHA)


class SafetyCategory(Strict):
    id: str = Field(min_length=1, max_length=120)
    prompts: list[SafetyPrompt] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def distinct(self):
        if len({p.id for p in self.prompts}) != len(self.prompts):
            raise ValueError("Duplicate safety prompt ID")
        return self


class Selection(Strict):
    expected_sha256: str | None = Field(default=None, pattern=SHA)
    source_sha256: str = Field(pattern=SHA)
    workflow: list[Reference] = Field(default_factory=list, max_length=100)
    policy: list[Reference] = Field(default_factory=list, max_length=300)
    data: list[Reference] = Field(default_factory=list, max_length=100)
    execution_data: FrozenSelection | None = None
    rubric: list[Reference] = Field(default_factory=list, max_length=300)
    safety: list[Reference] = Field(default_factory=list, max_length=300)
    safety_categories: list[SafetyCategory] = Field(default_factory=list, max_length=30)
    safety_source: SourceReference | None = None
    method: str = Field(default="task-rubric-v1", min_length=1, max_length=100)
    skill_mappings: list[SkillMapping] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def distinct(self):
        for section in SECTIONS:
            refs = getattr(self, section)
            if len({(r.kind, r.id, r.target) for r in refs}) != len(refs):
                raise ValueError("Duplicate binding reference")
        if len({c.id for c in self.safety_categories}) != len(self.safety_categories):
            raise ValueError("Duplicate safety category ID")
        return self


class FrozenBinding(Strict):
    task_group_id: UUID
    id: UUID
    snapshot_sha256: str = Field(pattern=SHA)


class NativeInputReference(Strict):
    """HTTP JSON reference; domain registry models retain strict Python types."""

    id: UUID
    sha256: str = Field(pattern=SHA)


class NativePreparation(Strict):
    max_model_calls: int = Field(ge=1, le=100, strict=True)
    resolved_input: NativeInputReference | None = None


def group(c, project, identifier):
    row = one(
        c,
        "SELECT * FROM anvil.benchmark_task_groups WHERE project_id=%s AND id=%s",
        (project, identifier),
    )
    if not row:
        raise HTTPException(404, "Imported Project not found")
    return row


def current(c, project, identifier):
    return one(
        c,
        "SELECT * FROM anvil.project_binding_versions WHERE project_id=%s AND task_group_id=%s ORDER BY version DESC LIMIT 1",
        (project, identifier),
    )


def reference_status(c, ref):
    """Fixed queries only; RLS and project-scoped FKs reject foreign references."""
    kind, identifier = ref["kind"], ref["id"]
    if kind == "custom_python":
        from anvil.custom_evaluators import get

        try:
            program = get(c, identifier)
        except HTTPException as exc:
            if exc.status_code == 404:
                return "not_found"
            raise
        if program["sha256"] != ref["sha256"]:
            return "hash_mismatch"
        return "available" if program["status"] == "tested" else program["status"]
    if kind == "evaluator":
        try:
            row = evaluator_configurations.get(c, identifier)
        except HTTPException as exc:
            if exc.status_code == 404:
                return "not_found"
            raise
        if row["configuration_sha256"] != ref["sha256"]:
            return "hash_mismatch"
        return "available" if row["status"] == "ready" else row["status"]
    queries = {
        "package": "SELECT package_sha256 AS sha FROM anvil.harbor_packages WHERE id=%s",
        "environment": "SELECT manifest_sha256 AS sha FROM anvil.environment_versions WHERE id=%s",
        "framework": "SELECT config_hash AS sha FROM anvil.workspace_framework_profiles WHERE id=%s",
        "policy_set": "SELECT content_sha256 AS sha FROM anvil.benchmark_policy_sets WHERE id=%s",
        "policy_mapping": "SELECT id FROM anvil.benchmark_policy_mappings WHERE id=%s",
        "revision": "SELECT v.content_hash AS sha,r.lifecycle,r.current_revision_id,v.id FROM anvil.revisions v JOIN anvil.resources r ON r.id=v.resource_id WHERE v.id=%s",
        "artifact": "SELECT sha256 AS sha,scan_status,classification FROM anvil.artifacts WHERE id=%s",
    }
    row = one(c, queries[kind], (identifier,))
    if not row:
        return "not_found"
    if kind == "policy_mapping":
        # Mapping identity alone is not a content/version binding. Bind its full
        # immutable database record, excluding its generated timestamp.
        mapping = one(
            c,
            "SELECT policy_set_id,policy_id,policy_version,rule_id,configuration_id,evidence_field,scope FROM anvil.benchmark_policy_mappings WHERE id=%s",
            (identifier,),
        )
        from fastapi.encoders import jsonable_encoder

        row["sha"] = digest(jsonable_encoder(mapping))
    if str(row["sha"]) != ref["sha256"]:
        return "hash_mismatch"
    if kind == "revision" and (
        row["lifecycle"] != "approved" or row["id"] != row["current_revision_id"]
    ):
        return "not_current_approved"
    if kind == "artifact" and (row["scan_status"] != "clean" or row["classification"] != "actor"):
        return "not_clean_actor_input"
    return "available"


def method_options(imported, c=None):
    from anvil.benchmark_runs import METHODS

    tasks = imported["content"].get("tasks", [])
    registered = {method["id"]: method for method in METHODS}
    qualified = {}
    if c is not None:
        from anvil.governed_ai_catalogue import catalogue

        pool = catalogue(c, imported)
        qualified = {
            item["candidate_id"]: item
            for item in pool["qualifications"]
            if item["kind"] == "method"
        }
    return [
        {
            "id": key,
            "name": registered.get(key, {}).get("name", key),
            "version": registered.get(key, {}).get("version"),
            "sha256": digest(registered[key]) if key in registered else None,
            "compatible": bool(tasks)
            and all(
                task_method_compatibility.check(t, registered.get(key, {"id": key}))["compatible"]
                for t in tasks
            ),
            "runtime_qualified": key in qualified
            and qualified[key]["candidate_sha256"] == digest(registered.get(key)),
            "qualification": qualified.get(key),
            "default": key == "task-rubric-v1",
        }
        for key in sorted(
            task_method_compatibility.BUSINESS_METHODS | task_method_compatibility.ORIGINAL_METHODS
        )
    ]


def requirement_descriptors(c, imported):
    from anvil.golden_targets import requirements as skill_requirements

    """Public descriptors from exact imported sources; no private rule values.

    Target IDs bind task identity/version/payload as well as rule identity. The
    same evaluator may be deliberately bound to several different targets.
    """
    criteria, policy_rules, tasks = [], [], []

    def bounded_append(items, value):
        if len(items) >= MAX_REQUIREMENTS:
            raise HTTPException(
                422,
                {
                    "code": "binding_requirement_limit_exceeded",
                    "limit": MAX_REQUIREMENTS,
                    "message": "Expanded requirements exceed the current binding capacity; no targets were silently omitted.",
                },
            )
        items.append(value)

    for task in imported["content"].get("tasks", []):
        identity = {key: task.get(key) for key in ("task_id", "task_version", "payload_sha256")}
        source = task.get("source", {})
        tasks.append(
            identity
            | {
                "title": task.get("title"),
                "source_schema_version": source.get("schema_version"),
                "template": source.get("template")
                if source.get("schema_version") == "anvil.praxis-authored-public-task.v1"
                else None,
                "template_metadata_status": "exact_export_reference"
                if source.get("schema_version") == "anvil.praxis-authored-public-task.v1"
                else "not_supplied_by_import_contract",
            }
        )
        rubric = task.get("rubric") or source.get("rubric") or {}
        for criterion in rubric.get("criteria", []):
            if not isinstance(criterion.get("id"), str):
                continue
            bounded_append(
                criteria,
                {
                    "target": "criterion:" + digest(identity | {"criterion_id": criterion["id"]}),
                    **identity,
                    "criterion_id": criterion["id"],
                    **{
                        key: criterion[key]
                        for key in ("description", "weight_bps", "points")
                        if key in criterion
                    },
                    "scale": rubric.get("scale"),
                },
            )
        for constraint in source.get("constraints", []):
            if not isinstance(constraint.get("id"), str):
                continue
            subject = identity | {"constraint_id": constraint["id"]}
            bounded_append(
                policy_rules,
                subject
                | {
                    "target": "policy-rule:" + digest(subject),
                    "source_kind": "task_constraint",
                    "requirement": constraint.get("description"),
                    "hard_failure": constraint.get("hard_failure"),
                    "visibility": "agent_instruction",
                },
            )
        for ref in source.get("policy_references", []):
            subject = identity | {
                "policy_id": ref["id"],
                "policy_version": ref["version"],
                "content_sha256": ref["content_sha256"],
                "scope": ref["scope"],
            }
            bounded_append(
                policy_rules,
                subject
                | {
                    "target": "policy-rule:" + digest(subject),
                    "source_kind": "versioned_policy_reference",
                    "rule_id": ref["id"],
                    "source_location": ref["publication_ref"],
                    "requirement": None,
                    "policy_text_status": "requires_qualified_content_lookup",
                },
            )
    for policy_set in c.execute(
        "SELECT id,content,content_sha256 FROM anvil.benchmark_policy_sets WHERE task_group_id=%s ORDER BY created_at,id",
        (imported["id"],),
    ).fetchall():
        manifest = policy_set["content"].get("manifest", {})
        defaults = {
            (p["policy_id"], p["version"]) for p in manifest.get("project_default_policy_refs", [])
        }
        sources = {s["id"]: s for s in manifest.get("sources", [])}
        policies = {(p["policy_id"], p["version"]): p for p in manifest.get("policies", [])}
        for binding in manifest.get("task_bindings", []):
            task_identity = {
                key: binding[key] for key in ("task_id", "task_version", "payload_sha256")
            }
            for ref in binding.get("policy_refs", []):
                policy = policies[(ref["policy_id"], ref["version"])]
                for rule in policy.get("rules", []):
                    subject = task_identity | {
                        "policy_set_sha256": policy_set["content_sha256"],
                        "policy_id": policy["policy_id"],
                        "policy_version": policy["version"],
                        "rule_id": rule["rule_id"],
                    }
                    public_rule = rule.get("visibility") == "agent_instruction"
                    bounded_append(
                        policy_rules,
                        {
                            **subject,
                            "target": "policy-rule:" + digest(subject),
                            "policy_set_id": str(policy_set["id"]),
                            "policy_title": policy.get("title"),
                            "source_sha256": sources.get(policy.get("source_id"), {}).get("sha256"),
                            "inheritance": "project_default"
                            if (policy["policy_id"], policy["version"]) in defaults
                            else "task_explicit",
                            "severity": rule.get("severity"),
                            "visibility": rule.get("visibility"),
                            "requirement": rule.get("requirement") if public_rule else None,
                            "source_location": rule.get("source_location") if public_rule else None,
                            "rubric_criterion_ids": rule.get("rubric_criterion_ids", []),
                        },
                    )
    return {
        "project": {
            "id": str(imported["id"]),
            "display_id": imported.get("display_id"),
            "name": imported["name"],
            "source_project_id": None
            if imported["content"].get("source_origin", {}).get("kind") == "praxis_authored_batch"
            else imported["source_project_id"],
            "source_version": None
            if imported["content"].get("source_origin", {}).get("kind") == "praxis_authored_batch"
            else imported["source_version"],
            "source_origin": imported["content"].get("source_origin", {"kind": "praxis_project"}),
            "source_sha256": imported["content_sha256"],
        },
        "tasks": tasks,
        "policy_rules": policy_rules,
        "rubric_criteria": criteria,
        "skill_requirements": [
            descriptor
            for task in imported["content"].get("tasks", [])
            for descriptor in skill_requirements(task)
        ],
    }


def evaluation_targets(descriptors, *, include_policy=False):
    """One exact target per official row, additional diagnostic and policy checks."""
    targets = list(descriptors["rubric_criteria"])
    targets += [x for x in descriptors.get("skill_requirements", []) if not x["official"]]
    if include_policy:
        targets += descriptors.get("policy_rules", [])
    return targets


def public(row):
    if row is None:
        return None
    return {
        key: row[key]
        for key in ("id", "task_group_id", "version", "snapshot", "snapshot_sha256", "created_at")
    }


def save(c, project, user, identifier, body):
    # Imported source rows are immutable and intentionally have no UPDATE grant.
    # Use the same project lock/order as the existing idempotency ledger.
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    imported = group(c, project, identifier)
    old = current(c, project, identifier)
    if body.expected_sha256 != (old["snapshot_sha256"] if old else None):
        raise HTTPException(409, "Bindings changed; reload before saving")
    if body.source_sha256 != imported["content_sha256"]:
        raise HTTPException(409, "Imported source hash changed")
    option = next((m for m in method_options(imported, c) if m["id"] == body.method), None)
    if not option or not option["compatible"]:
        raise HTTPException(422, "Benchmark method is incompatible with these imported tasks")
    snapshot = body.model_dump(mode="json", exclude={"expected_sha256"})
    if "skill_mappings" not in body.model_fields_set and old:
        snapshot["skill_mappings"] = old["snapshot"].get("skill_mappings", [])
    if "safety_source" not in body.model_fields_set and old:
        snapshot["safety_source"] = old["snapshot"].get("safety_source")
    from anvil.task_safety_sources import freeze as freeze_safety

    try:
        snapshot["safety_binding"] = freeze_safety(
            c, imported, snapshot["safety_source"], snapshot["safety_categories"]
        )
    except ValueError as exc:
        raise HTTPException(
            422, {"code": "invalid_safety_source_binding", "message": str(exc)}
        ) from None
    if body.execution_data:
        from anvil.project_inputs import frozen

        frozen(c, project, imported, body.execution_data)
    from anvil.benchmark_runs import METHODS

    definition = next(method for method in METHODS if method["id"] == body.method)
    snapshot["method_binding"] = {
        "id": body.method,
        "sha256": option["sha256"],
        "definition": definition,
        "qualification": option["qualification"],
        "task_rubrics": [
            {key: task.get(key) for key in ("task_id", "task_version", "payload_sha256", "rubric")}
            for task in imported["content"].get("tasks", [])
        ],
    }
    if any(
        ref["kind"] == "custom_python"
        for section in SECTIONS
        if section not in {"rubric", "policy"}
        for ref in snapshot[section]
    ):
        raise HTTPException(422, {"code": "custom_python_policy_or_rubric_only"})
    overrides = [
        ref["target"]
        for section in ("policy", "rubric")
        for ref in snapshot[section]
        if ref["kind"] == "custom_python"
    ]
    if len(overrides) != len(set(overrides)):
        raise HTTPException(422, {"code": "duplicate_custom_python_override"})
    descriptors = requirement_descriptors(c, imported)
    from anvil.skill_step_bindings import options as step_options
    from anvil.skill_step_bindings import resolve_all

    try:
        snapshot["skill_mapping_bindings"] = resolve_all(
            [SkillMapping.model_validate(value) for value in snapshot["skill_mappings"]],
            descriptors["skill_requirements"],
            step_options(c, project, imported),
        )
    except ValueError as exc:
        raise HTTPException(
            422, {"code": "invalid_authored_skill_mapping", "message": str(exc)}
        ) from None
    for section, key in (("policy", "policy_rules"), ("rubric", "rubric_criteria")):
        targets = {
            r["target"]
            for r in (evaluation_targets(descriptors) if section == "rubric" else descriptors[key])
        }
        if any(
            ref["kind"] in {"evaluator", "custom_python"} and ref["target"] not in targets
            for ref in snapshot[section]
        ):
            raise HTTPException(422, {"code": "unknown_requirement_target", "section": section})
    errors = [
        {"section": section, "target": ref["target"], "code": status}
        for section in SECTIONS
        for ref in snapshot[section]
        if (status := reference_status(c, ref))
        in {"not_found", "hash_mismatch", "not_clean_actor_input"}
    ]
    if errors:
        raise HTTPException(422, {"code": "invalid_binding_references", "errors": errors})
    from anvil.campaign_ordinal import binding_record, supports_target

    native_ordinal = []
    native_targets = {
        item["target"] for item in descriptors["skill_requirements"] if supports_target(item)
    }
    native_profiles = {}
    for section, ref in ((section, ref) for section in SECTIONS for ref in snapshot[section]):
        if ref["kind"] == "evaluator":
            if ref["id"] not in native_profiles:
                native_profiles[ref["id"]] = evaluator_configurations.get(c, ref["id"])
            record = binding_record(ref, native_profiles[ref["id"]])
            if record:
                if section != "rubric" or ref["target"] not in native_targets:
                    raise HTTPException(
                        422,
                        {"code": "native_ordinal_target_not_supported", "target": ref["target"]},
                    )
                if (
                    sum(
                        other["target"] == ref["target"]
                        and other["kind"] in {"evaluator", "custom_python"}
                        for other in snapshot["rubric"]
                    )
                    != 1
                ):
                    raise HTTPException(
                        422, {"code": "ambiguous_native_ordinal_binding", "target": ref["target"]}
                    )
                native_ordinal.append(record)
    if native_ordinal:
        snapshot["native_ordinal_bindings"] = native_ordinal
    from anvil.campaign_semantic_bindings import freeze as freeze_semantic

    snapshot.update(freeze_semantic(c, project, imported, snapshot, descriptors))
    from anvil.diagnostic_bindings import freeze as freeze_diagnostics

    snapshot.update(freeze_diagnostics(c, snapshot, descriptors))
    from anvil.kyc_expectation_reviews import freeze as freeze_expectations

    snapshot.update(freeze_expectations(c, project, snapshot))
    sha = digest(snapshot)
    if old and old["snapshot_sha256"] == sha:
        return public(old)
    identifier_new = uid()
    c.execute(
        "INSERT INTO anvil.project_binding_versions(id,project_id,task_group_id,version,snapshot,snapshot_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier_new,
            project,
            identifier,
            old["version"] + 1 if old else 1,
            Jsonb(snapshot),
            sha,
            user,
        ),
    )
    audit(
        c,
        project,
        user,
        "project.bindings.saved",
        identifier_new,
        {"task_group_id": str(identifier), "snapshot_sha256": sha},
    )
    return public(current(c, project, identifier))


def evidence_gaps(snapshot, evidence):
    """Check exact-snapshot, trace-backed qualification, never UI booleans."""
    gaps = []
    if not isinstance(evidence, dict):
        return [{"section": "runtime", "code": "qualification_invalid"}]
    if evidence.get("schema_version") != "anvil.project-binding-qualification.v1" or evidence.get(
        "snapshot_sha256"
    ) != digest(snapshot):
        return [{"section": "runtime", "code": "qualification_snapshot_mismatch"}]
    checks = evidence.get("checks", {})
    if not isinstance(checks, dict):
        return [{"section": "runtime", "code": "qualification_invalid"}]
    for key in (*SECTIONS, "runtime", "mcp", "recovery", "recommendations"):
        item = checks.get(key, {})
        if not (
            isinstance(item, dict)
            and item.get("status") == "passed"
            and valid_hash(item.get("evidence_sha256"))
        ):
            gaps.append({"section": key, "code": "qualification_check_missing"})
    actual = evidence.get("safety_trials", [])
    if not isinstance(actual, list) or any(not isinstance(t, dict) for t in actual):
        return gaps + [{"section": "safety", "code": "qualification_invalid"}]
    if any(
        t.get("evaluator_valid") is True and t.get("containment_outcome") == "fail" for t in actual
    ):
        gaps.append({"section": "safety", "code": "environment_containment_failed"})
    for category in snapshot["safety_categories"]:
        for prompt in category["prompts"]:
            trials = [
                t
                for t in actual
                if t.get("category_id") == category["id"]
                and t.get("prompt_id") == prompt["id"]
                and t.get("prompt_sha256") == prompt["sha256"]
            ]
            if not any(
                t.get("applicable") is True
                and t.get("exposed") is True
                and t.get("evaluator_valid") is True
                and valid_hash(t.get("injection_trace_sha256"))
                and valid_hash(t.get("evaluation_sha256"))
                and t.get("candidate_outcome") in ("pass", "fail")
                and t.get("containment_outcome") in ("pass", "fail")
                for t in trials
            ):
                gaps.append(
                    {
                        "section": "safety",
                        "code": "prompt_not_exercised",
                        "category_id": category["id"],
                        "prompt_id": prompt["id"],
                    }
                )
    from anvil.campaign_ordinal import qualification_gaps as ordinal_gaps
    from anvil.custom_python_grading import qualification_gaps
    from anvil.diagnostic_bindings import qualification_gaps as diagnostic_gaps

    semantic_gaps = snapshot.get("semantic_judge_gaps", [])
    if not isinstance(semantic_gaps, list) or any(
        not isinstance(gap, dict) for gap in semantic_gaps
    ):
        semantic_gaps = [
            {"section": "rubric", "code": "native_semantic_binding_invalid", "owner": "anvil"}
        ]
    return (
        gaps
        + qualification_gaps(snapshot, evidence)
        + ordinal_gaps(snapshot, evidence)
        + semantic_gaps
        + diagnostic_gaps(snapshot, evidence)
    )


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(SHA, value) is not None


def require_ready(c, project, task_group_id, binding_id, snapshot_sha256):
    """Fresh selection/revocation check; existing model/budget gates still apply."""
    result = readiness(c, project, task_group_id)
    bound = result["binding"]
    if (
        not bound
        or str(bound["id"]) != str(binding_id)
        or bound["snapshot_sha256"] != snapshot_sha256
    ):
        raise HTTPException(
            409,
            {
                "code": "project_binding_changed",
                "message": "Reload bindings and prepare a new frozen execution.",
            },
        )
    if not result["ready"]:
        raise HTTPException(409, {"code": "project_binding_pending", "gaps": result["gaps"]})
    return {
        "task_group_id": str(task_group_id),
        "id": str(bound["id"]),
        "snapshot_sha256": bound["snapshot_sha256"],
        "qualification_id": str(result["qualification_id"]),
    }


def execution_issues(c, project, frozen, packages):
    """Fresh readiness and exact-package fence for the existing dispatch path."""
    if not frozen:
        return ["project_binding_required"]
    try:
        parsed = FrozenBinding.model_validate(frozen)
        require_ready(c, project, parsed.task_group_id, parsed.id, parsed.snapshot_sha256)
        bound = current(c, project, parsed.task_group_id)
        selected = {
            (str(r["id"]), r["sha256"])
            for r in bound["snapshot"]["workflow"]
            if r["kind"] == "package"
        }
        if any((str(p["id"]), p["package_sha256"]) not in selected for p in packages):
            return ["project_binding_package_mismatch"]
        from anvil.golden_kyc_binding_ancestry import verify_packages

        try:
            verify_packages(c, project, bound, packages)
        except (ValueError, KeyError, TypeError):
            return ["kyc_exact_preparation_to_run_binding_required"]
    except HTTPException as exc:
        if exc.status_code in (403, 404, 409):
            return ["project_binding_pending_or_changed"]
        raise
    except ValidationError:
        return ["project_binding_invalid"]
    return []


def readiness(c, project, identifier, reference_cache=None):
    imported = group(c, project, identifier)
    row = current(c, project, identifier)
    gaps = []
    cache = {} if reference_cache is None else reference_cache
    if not row:
        return {
            "status": "Binding Pending",
            "ready": False,
            "binding": None,
            "gaps": [{"section": s, "code": "binding_missing"} for s in SECTIONS],
            "paid_dispatch_authorized": False,
        }
    snapshot = row["snapshot"]
    selected_method = next(
        (item for item in method_options(imported, c) if item["id"] == snapshot.get("method")), None
    )
    frozen_method = snapshot.get("method_binding") or {}
    if (
        not selected_method
        or not selected_method["runtime_qualified"]
        or frozen_method.get("sha256") != selected_method["sha256"]
        or digest(frozen_method.get("definition")) != selected_method["sha256"]
        or frozen_method.get("qualification") != selected_method["qualification"]
    ):
        gaps.append(
            {"section": "rubric", "code": "exact_method_qualification_required", "owner": "anvil"}
        )
    try:
        descriptors = requirement_descriptors(c, imported)
    except HTTPException as exc:
        if (
            not isinstance(exc.detail, dict)
            or exc.detail.get("code") != "binding_requirement_limit_exceeded"
        ):
            raise
        return {
            "status": "Binding Pending",
            "ready": False,
            "binding": public(row),
            "gaps": [
                {
                    "section": "source",
                    "code": "binding_requirement_limit_exceeded",
                    "limit": MAX_REQUIREMENTS,
                }
            ],
            "paid_dispatch_authorized": False,
        }
    if (
        snapshot["source_sha256"] != imported["content_sha256"]
        or digest(snapshot) != row["snapshot_sha256"]
    ):
        gaps.append({"section": "source", "code": "source_or_binding_hash_mismatch"})
    for section in SECTIONS:
        if (
            not snapshot[section]
            and not (section == "data" and snapshot.get("execution_data"))
            and (section != "policy" or descriptors["policy_rules"])
        ):
            gaps.append({"section": section, "code": "binding_missing"})
        for ref in snapshot[section]:
            key = (ref["kind"], ref["id"], ref["sha256"])
            if key not in cache:
                cache[key] = reference_status(c, ref)
            status = cache[key]
            if status != "available":
                gaps.append({"section": section, "target": ref["target"], "code": status})
            elif ref["kind"] == "evaluator":
                native_key = ("native_program_configuration", ref["id"], ref["sha256"])
                if native_key not in cache:
                    configuration = one(
                        c,
                        "SELECT configuration FROM anvil.evaluator_configurations WHERE id=%s",
                        (ref["id"],),
                    )
                    cache[native_key] = (configuration or {}).get("configuration", {})
                program = cache[native_key].get("native_ordinal")
                if program is not None:
                    from anvil.campaign_ordinal import supports_target

                    if section != "rubric" or not any(
                        item["target"] == ref["target"] and supports_target(item)
                        for item in descriptors["skill_requirements"]
                    ):
                        gaps.append(
                            {
                                "section": section,
                                "target": ref["target"],
                                "code": "native_ordinal_target_not_supported",
                                "owner": "anvil",
                            }
                        )
                    record = {
                        "target": ref["target"],
                        "configuration_id": str(ref["id"]),
                        "configuration_sha256": ref["sha256"],
                        "program_sha256": digest(program),
                    }
                    if record not in snapshot.get("native_ordinal_bindings", []):
                        gaps.append(
                            {
                                "section": section,
                                "target": ref["target"],
                                "code": "native_ordinal_frozen_program_binding_required",
                                "owner": "anvil",
                            }
                        )
                semantic = cache[native_key].get("native_semantic")
                if semantic is not None:
                    from anvil.campaign_semantic_bindings import compatible

                    config = {"configuration": cache[native_key]}
                    if section != "rubric" or not any(
                        item["target"] == ref["target"] and compatible(config, item)
                        for item in descriptors["skill_requirements"]
                    ):
                        gaps.append(
                            {
                                "section": section,
                                "target": ref["target"],
                                "code": "native_semantic_target_not_supported",
                                "owner": "anvil",
                            }
                        )
                    record = {
                        "target": ref["target"],
                        "configuration_id": str(ref["id"]),
                        "configuration_sha256": ref["sha256"],
                        "program_sha256": digest(semantic),
                    }
                    if record not in snapshot.get("native_semantic_bindings", []):
                        gaps.append(
                            {
                                "section": section,
                                "target": ref["target"],
                                "code": "native_semantic_frozen_program_binding_required",
                                "owner": "anvil",
                            }
                        )
                    if not snapshot.get("semantic_judge_batches"):
                        gaps.append(
                            {
                                "section": section,
                                "target": ref["target"],
                                "code": "native_semantic_qualified_case_batches_required",
                                "owner": "anvil",
                            }
                        )
    if snapshot.get("execution_data"):
        from anvil.project_inputs import selection_gaps

        gaps.extend(
            selection_gaps(c, project, imported, snapshot["execution_data"], snapshot["workflow"])
        )
    mapped_targets = {mapping["target"] for mapping in snapshot.get("skill_mapping_bindings", [])}
    from anvil.kyc_expectation_reviews import binding_gaps as expectation_gaps

    gaps.extend(expectation_gaps(c, project, snapshot))
    for descriptor in descriptors["skill_requirements"]:
        if descriptor["target"] not in mapped_targets:
            gaps.append(
                {
                    "section": "rubric",
                    "target": descriptor["target"],
                    "code": "authored_skill_mapping_required",
                }
            )
    from anvil.diagnostic_bindings import freeze as freeze_diagnostics

    diagnostic_selection = freeze_diagnostics(c, snapshot, descriptors)
    gaps.extend(diagnostic_selection["diagnostic_binding_gaps"])
    for record in diagnostic_selection["native_diagnostic_bindings"]:
        if record not in snapshot.get("native_diagnostic_bindings", []):
            gaps.append(
                {
                    "section": "rubric",
                    "target": record["target"],
                    "code": "native_diagnostic_frozen_binding_required",
                    "owner": "anvil",
                }
            )
    if (
        any(
            ref["kind"] == "custom_python"
            for section in ("policy", "rubric")
            for ref in snapshot[section]
        )
        and os.environ.get("ANVIL_CUSTOM_PYTHON_SCORING_ENABLED") != "true"
    ):
        gaps.append({"section": "rubric", "code": "private_python_scoring_not_enabled"})
    for section, key in (("policy", "policy_rules"), ("rubric", "rubric_criteria")):
        mapped = {
            r["target"] for r in snapshot[section] if r["kind"] in {"evaluator", "custom_python"}
        }
        for descriptor in (
            evaluation_targets(descriptors) if section == "rubric" else descriptors[key]
        ):
            if descriptor["target"] not in mapped:
                gaps.append(
                    {
                        "section": section,
                        "target": descriptor["target"],
                        "code": "requirement_evaluator_missing",
                    }
                )
    if not descriptors["rubric_criteria"]:
        gaps.append({"section": "rubric", "code": "rubric_descriptors_unavailable"})
    categories = snapshot["safety_categories"]
    from anvil.task_safety_sources import gaps as safety_source_gaps

    gaps.extend(safety_source_gaps(c, imported, snapshot))
    if len(categories) < 5:
        gaps.append({"section": "safety", "code": "five_applicable_categories_required"})
    for category in categories:
        if len(category["prompts"]) < 3:
            gaps.append(
                {
                    "section": "safety",
                    "code": "three_prompts_per_category_required",
                    "category_id": category["id"],
                }
            )
    release = os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256", "")
    receipt = (
        one(
            c,
            "SELECT q.* FROM anvil.project_binding_qualifications q WHERE q.project_id=%s AND q.binding_id=%s AND q.release_sha256=%s AND q.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id) ORDER BY q.created_at DESC,q.id DESC LIMIT 1",
            (project, row["id"], release),
        )
        if release
        else None
    )
    if not receipt:
        gaps.append({"section": "runtime", "code": "current_deployment_qualification_required"})
    elif digest(receipt["evidence"]) != receipt["evidence_sha256"]:
        gaps.append({"section": "runtime", "code": "qualification_hash_mismatch"})
    else:
        gaps.extend(evidence_gaps(snapshot, receipt["evidence"]))
    return {
        "status": "Binding Pending" if gaps else "Ready to Run",
        "ready": not gaps,
        "binding": public(row),
        "gaps": gaps,
        "qualification_id": receipt["id"] if receipt else None,
        "paid_dispatch_authorized": False,
        "admission": "Fresh access, revocation, exact model and aggregate budget checks remain mandatory at Run.",
    }


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/imported-projects")

    @router.post("/{task_group_id}/native-packages")
    def native_packages(
        project: UUID, task_group_id: UUID, body: NativePreparation, request: Request
    ):
        from anvil.praxis_generic_resolution import resolve
        from anvil.praxis_project_intake import prepare_native, requalification_inputs

        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin")
            imported = group(c, project, task_group_id)
            inputs = requalification_inputs(c, project, imported)

            def prepare():
                for validation, parsed, staged in inputs:
                    resolved = resolve(c, project, user, validation, parsed, staged)
                    if resolved["status"] != "import_resolved":
                        raise HTTPException(409, resolved)
                return prepare_native(c, project, user, imported, body.max_model_calls,
                                      resolved_input=body.resolved_input.model_dump(mode="json") if body.resolved_input else None)

            return wrap(idempotent(c, project, user, request, body, prepare), request)

    @router.get("")
    def listing(
        project: UUID,
        request: Request,
        limit: int = Query(10, ge=1, le=20),
        after_display_id: int = Query(0, ge=0),
        ready_only: bool = False,
        include_tasks: bool = False,
        q: str = Query("", max_length=200),
    ):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            query = q.strip()
            pattern = (
                "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            )
            rows = c.execute(
                "SELECT * FROM anvil.benchmark_task_groups WHERE project_id=%s AND display_id>%s AND (%s='' OR name ILIKE %s OR display_id::text=%s) ORDER BY display_id LIMIT %s",
                (project, after_display_id, query, pattern, query, limit + 1),
            ).fetchall()
            items, cache = [], {}
            for imported in rows[:limit]:
                ready = readiness(c, project, imported["id"], reference_cache=cache)
                if ready_only and not ready["ready"]:
                    continue
                binding = ready["binding"]
                packages = []
                if binding:
                    for ref in binding["snapshot"]["workflow"]:
                        if ref["kind"] != "package":
                            continue
                        package = one(
                            c,
                            "SELECT id,package_sha256,manifest FROM anvil.harbor_packages WHERE id=%s",
                            (ref["id"],),
                        )
                        if package and package["package_sha256"] == ref["sha256"]:
                            packages.append(
                                {
                                    "id": str(package["id"]),
                                    "package_sha256": package["package_sha256"],
                                    "task_id": package["manifest"].get("task_id"),
                                    "task_version": package["manifest"].get("task_version"),
                                    "binding": package["manifest"].get("binding"),
                                }
                            )
                items.append(
                    {
                        "id": str(imported["id"]),
                        "display_id": imported["display_id"],
                        "name": imported["name"],
                        "source_project_id": None
                        if imported["content"].get("source_origin", {}).get("kind")
                        == "praxis_authored_batch"
                        else imported["source_project_id"],
                        "source_version": None
                        if imported["content"].get("source_origin", {}).get("kind")
                        == "praxis_authored_batch"
                        else imported["source_version"],
                        "source_origin": imported["content"].get(
                            "source_origin", {"kind": "praxis_project"}
                        ),
                        "case_dataset": imported["content"].get("case_dataset"),
                        "source_sha256": imported["content_sha256"],
                        "readiness": ready,
                        "packages": packages,
                        "project_binding": {
                            "task_group_id": str(imported["id"]),
                            "id": str(binding["id"]),
                            "snapshot_sha256": binding["snapshot_sha256"],
                        }
                        if binding
                        else None,
                    }
                )
                if include_tasks:
                    from anvil.benchmark_project_import import public_group

                    items[-1]["tasks"] = public_group(imported)["tasks"]
            return wrap(
                {
                    "items": items,
                    "scanned": min(len(rows), limit),
                    "next_after_display_id": rows[limit - 1]["display_id"]
                    if len(rows) > limit
                    else None,
                    "ready_only": ready_only,
                    "paid_dispatch_authorized": False,
                },
                request,
            )

    @router.get("/{task_group_id}")
    def detail(project: UUID, task_group_id: UUID, request: Request):
        from anvil.benchmark_project_import import public_group

        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            imported = group(c, project, task_group_id)
            return wrap(
                public_group(imported)
                | {
                    "source_sha256": imported["content_sha256"],
                    "readiness": readiness(c, project, task_group_id),
                },
                request,
            )

    @router.get("/{task_group_id}/bindings")
    def get(project: UUID, task_group_id: UUID, request: Request):
        from anvil.project_inputs import options as input_options
        from anvil.skill_step_bindings import mapped
        from anvil.skill_step_bindings import options as step_options

        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            imported = group(c, project, task_group_id)
            bound = current(c, project, task_group_id)
            descriptors = requirement_descriptors(c, imported)
            if bound:
                descriptors["skill_requirements"] = mapped(
                    descriptors["skill_requirements"],
                    bound["snapshot"]
                    | {
                        "project_binding": {
                            "id": str(bound["id"]),
                            "task_group_id": str(task_group_id),
                            "snapshot_sha256": bound["snapshot_sha256"],
                        }
                    },
                )
            return wrap(
                {
                    "binding": public(bound),
                    "source_sha256": imported["content_sha256"],
                    "descriptors": descriptors,
                    "methods": method_options(imported, c),
                    "execution_data_options": input_options(c, project, imported),
                    "workflow_step_options": step_options(c, project, imported),
                },
                request,
            )

    @router.put("/{task_group_id}/bindings")
    def put(project: UUID, task_group_id: UUID, body: Selection, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: save(c, project, user, task_group_id, body),
                ),
                request,
            )

    @router.get("/{task_group_id}/binding-options")
    def options(project: UUID, task_group_id: UUID, request: Request):
        from anvil.governed_ai_runtime import recommendation_status
        from anvil.project_inputs import options as input_options
        from anvil.skill_step_bindings import options as step_options

        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            imported = group(c, project, task_group_id)
            evaluators = evaluator_options(c)
            return wrap(
                {
                    "source_sha256": imported["content_sha256"],
                    "descriptors": requirement_descriptors(c, imported),
                    "frameworks": c.execute(
                        "SELECT id,name,framework,config_hash AS sha256 FROM anvil.workspace_framework_profiles ORDER BY created_at DESC,id LIMIT 100"
                    ).fetchall(),
                    "packages": c.execute(
                        "SELECT id,manifest->>'task_id' AS title,package_sha256 AS sha256 FROM anvil.harbor_packages ORDER BY created_at DESC,id LIMIT 100"
                    ).fetchall(),
                    "environments": c.execute(
                        "SELECT id,name,manifest_sha256 AS sha256 FROM anvil.environment_versions ORDER BY created_at DESC,id LIMIT 100"
                    ).fetchall(),
                    "policy_sets": c.execute(
                        "SELECT id,content_sha256 AS sha256 FROM anvil.benchmark_policy_sets WHERE task_group_id=%s ORDER BY created_at DESC,id LIMIT 100",
                        (task_group_id,),
                    ).fetchall(),
                    "actor_inputs": c.execute(
                        "SELECT id,sha256,mime_type,byte_size FROM anvil.artifacts WHERE classification='actor' AND scan_status='clean' ORDER BY created_at DESC,id LIMIT 100"
                    ).fetchall(),
                    "approved_revisions": c.execute(
                        "SELECT v.id,r.kind,v.content_hash AS sha256 FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE r.lifecycle='approved' ORDER BY v.created_at DESC,v.id LIMIT 300"
                    ).fetchall(),
                    "evaluators": evaluators,
                    "methods": method_options(imported, c),
                    "recommendations": recommendation_status(c, imported),
                    "execution_data_options": input_options(c, project, imported),
                    "workflow_step_options": step_options(c, project, imported),
                    "limits": {"minimum_safety_categories": 5, "minimum_prompts_per_category": 3},
                },
                request,
            )

    @router.get("/{task_group_id}/inputs/{artifact_id}/preview")
    def input_preview(project: UUID, task_group_id: UUID, artifact_id: UUID, request: Request):
        from anvil import artifacts
        from anvil.input_preview import MAX_BYTES, preview

        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            group(c, project, task_group_id)
            row = one(
                c,
                "SELECT sha256,mime_type,byte_size,classification,scan_status FROM anvil.artifacts WHERE project_id=%s AND id=%s",
                (project, artifact_id),
            )
            if not row:
                raise HTTPException(404, "Input file not found")
            if row["classification"] != "actor" or row["scan_status"] != "clean":
                raise HTTPException(403, "Only clean actor input files can be previewed")
            if row["byte_size"] > MAX_BYTES:
                raise HTTPException(422, "Input preview is limited to 256 KiB")
            try:
                result = preview(artifacts.read(c, artifact_id, actor_only=True), row["mime_type"])
            except (ValueError, UnicodeError, RecursionError):
                raise HTTPException(
                    422,
                    "Input must be bounded UTF-8 CSV or a JSON record array with consistent columns",
                ) from None
            audit(c, project, user, "project.input_previewed", artifact_id)
            return wrap(
                {**result, "artifact_id": str(artifact_id), "sha256": row["sha256"]}, request
            )

    @router.get("/{task_group_id}/readiness")
    def get_readiness(project: UUID, task_group_id: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, *READ_ROLES)
            return wrap(readiness(c, project, task_group_id), request)

    return router
