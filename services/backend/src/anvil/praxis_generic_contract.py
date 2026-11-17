"""Generic authored-task and joint-template wire contracts. No imported execution."""

import hashlib
import re
from decimal import Decimal
from typing import Literal
from uuid import UUID

import rfc8785
from pydantic import Field, model_validator

from anvil.dataset_export_contract import Identifier, Model, Sha, json_object
from anvil.praxis_case_dataset import CaseDatasetRef, CaseSelector, PolicyRef
from anvil.praxis_marketing_contract import CampaignSelector, MarketingExecution

SPEC = "praxis.anvil.template-spec.v1"
EXPORT = "praxis.authored-task-export.v1"
EXPORT_V2 = "praxis.authored-task-export.v2"
FIELD_TYPES = {
    "text",
    "long_text",
    "date",
    "number",
    "pick_list",
    "multi_select",
    "repeated_array",
    "criterion",
    "evidence_record",
    "policy_citation",
    "tool_call",
    "graph_binding",
}
PRIVATE_VISIBILITIES = {"private_reference", "private_rubric", "evaluation_private"}
SCHEMA_KEYS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "const",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "description",
    "title",
}


def canonical(value):
    return rfc8785.dumps(value)


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def load(raw):
    value = json_object(raw)
    canonical(value)  # Reject non-JCS-compatible integers/Unicode before hashing.
    return value


def path(value):
    if (
        not isinstance(value, str)
        or len(value) > 240
        or not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*(/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*", value)
    ):
        raise ValueError("Unsafe relative package path")
    return value


def schema_definition(value, depth=0):
    if depth > 16 or not isinstance(value, dict) or set(value) - SCHEMA_KEYS:
        raise ValueError("Unsupported bounded JSON-schema keyword or depth")
    if value.get("type") not in {
        "object",
        "array",
        "string",
        "number",
        "integer",
        "boolean",
        "null",
    }:
        raise ValueError("Explicit supported schema type required")
    props = value.get("properties", {})
    required = value.get("required", [])
    if (
        not isinstance(props, dict)
        or not isinstance(required, list)
        or any(type(x) is not str for x in required)
        or len(set(required)) != len(required)
        or not set(required) <= props.keys()
    ):
        raise ValueError("Schema required fields must resolve")
    for child in props.values():
        schema_definition(child, depth + 1)
    if "items" in value:
        schema_definition(value["items"], depth + 1)
    if value.get("type") == "array" and "items" not in value:
        raise ValueError("Array item schema required")
    extra = value.get("additionalProperties", False)
    if type(extra) is not bool:
        raise ValueError("Only boolean additionalProperties supported")
    for key in ("minItems", "maxItems", "minLength", "maxLength"):
        if key in value and (type(value[key]) is not int or value[key] < 0):
            raise ValueError("Invalid schema bound")
    for key in ("minimum", "maximum"):
        if key in value and type(value[key]) not in (int, float):
            raise ValueError("Numeric schema bound required")
    for low, high in (("minimum", "maximum"), ("minItems", "maxItems"), ("minLength", "maxLength")):
        if low in value and high in value and value[low] > value[high]:
            raise ValueError("Contradictory schema bounds")
    if "enum" in value and (
        not isinstance(value["enum"], list) or not 1 <= len(value["enum"]) <= 100
    ):
        raise ValueError("Bounded nonempty enum required")
    canonical(value)


def schema_errors(value, schema, pointer=""):
    """Safe subset checks; return paths only, never echo private input values."""
    kinds = {
        "object": type(value) is dict,
        "array": type(value) is list,
        "string": type(value) is str,
        "number": type(value) in (int, float),
        "integer": type(value) is int,
        "boolean": type(value) is bool,
        "null": value is None,
    }
    if not kinds.get(schema["type"], False):
        return [pointer]
    errors = []
    if "const" in schema and canonical(value) != canonical(schema["const"]):
        errors.append(pointer)
    if "enum" in schema and canonical(value) not in [canonical(v) for v in schema["enum"]]:
        errors.append(pointer)
    if isinstance(value, dict):
        errors += [pointer + "/" + key for key in schema.get("required", []) if key not in value]
        for key, child in value.items():
            part = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
            if key in schema.get("properties", {}):
                errors += schema_errors(child, schema["properties"][key], part)
            elif schema.get("additionalProperties", False) is False:
                errors.append(part)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 10000):
            errors.append(pointer)
        for index, item in enumerate(value):
            errors += schema_errors(item, schema["items"], pointer + "/" + str(index))
    if isinstance(value, str) and not schema.get("minLength", 0) <= len(value) <= schema.get(
        "maxLength", 1000000
    ):
        errors.append(pointer)
    if type(value) in (int, float) and not schema.get(
        "minimum", float("-inf")
    ) <= value <= schema.get("maximum", float("inf")):
        errors.append(pointer)
    return errors


class CapabilityRef(Model):
    id: Identifier
    version: Identifier


class SkillsRole(Model):
    mandatory: list[str] = Field(min_length=1, max_length=50)
    preferred: list[str] = Field(default_factory=list, max_length=50)
    specialties: list[str] = Field(default_factory=list, max_length=50)
    jurisdictions: list[str] = Field(default_factory=list, max_length=50)
    languages: list[str] = Field(default_factory=list, max_length=50)
    certifications: list[str] = Field(default_factory=list, max_length=50)


class Skills(Model):
    schema_version: Literal["anvil.template-skills.v1"]
    authoring: SkillsRole
    reviewing: SkillsRole


class Tool(Model):
    id: Identifier
    input_schema: dict
    output_schema: dict
    error_schema: dict
    response_mode: Literal["recorded", "environment"]
    pending: bool
    error_statuses: list[Literal[429, 503]]
    reset: Literal["new_episode"]
    isolation: Literal["per_episode"]


class Evaluator(Model):
    criterion_id: Identifier
    capability: CapabilityRef
    evidence_source: Literal["output", "run_evidence", "trace", "business_table", "human"]


class RuleRef(Model):
    id: Identifier
    version: Identifier
    content_sha256: Sha
    publication_ref: str = Field(min_length=1, max_length=200)


class Limits(Model):
    tool_calls: int = Field(ge=0, le=1000)
    wall_seconds: int = Field(ge=1, le=86400)
    output_bytes: int = Field(ge=1, le=1048576)
    transitions: int = Field(ge=1, le=10000)


class Execution(Model):
    schema_version: Literal["anvil.template-execution.v1"]
    catalogue_version: Literal["1.0.0", "1.1.0"]
    environment: CapabilityRef
    tools: list[Tool] = Field(max_length=50)
    evaluators: list[Evaluator] = Field(min_length=1, max_length=100)
    output_schema: dict
    conformance_output: dict
    limits: Limits
    graph_node_types: list[str] = Field(max_length=20)
    rules: list[RuleRef] = Field(max_length=100)
    network: Literal["none"]
    reset: Literal["new_episode"]
    isolation: Literal["per_episode"]
    paid_calls: Literal[False]


class ReusableExecution(Execution):
    """Explicit successor; frozen v1 objects gain no defaults or new fields."""

    schema_version: Literal["anvil.template-execution.v2"]
    catalogue_version: Literal["1.2.0"]
    federalPolicies: list[PolicyRef] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def reusable_environment(self):
        if self.environment.id != "golden-kyc-openenv-v2" or self.environment.version != "2":
            raise ValueError("Reusable KYC requires the explicit state-dataset capability version")
        ids = [p.id for p in self.federalPolicies]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate federal policy identity")
        return self


class TemplateProposal(Model):
    schemaVersion: Literal[SPEC]
    anvil_template_key: Identifier
    requirement: dict
    authoring: dict = Field(
        json_schema_extra={
            "required": ["profile"],
            "additionalProperties": False,
            "properties": {
                "profile": {"type": "object"},
                "template": {"type": "object"},
                "examples": {"type": "array"},
            },
            "description": "Praxis-owned authoring.schema.json governs profile/template/examples; exact supplied values are hashed.",
        }
    )
    execution: Execution | ReusableExecution | MarketingExecution = Field(
        discriminator="schema_version"
    )
    skills: Skills

    @model_validator(mode="after")
    def consistent(self):
        # Never normalize the published object before hashing it.
        if not self.requirement or len(canonical(self.requirement)) > 16384:
            raise ValueError("Bounded nonempty requirement reference required")
        if set(self.authoring) - {"profile", "template", "examples"}:
            raise ValueError("Authoring contains unsupported fields")
        form = self.authoring.get("profile")
        if not isinstance(form, dict):
            raise ValueError("Authoring profile required")
        if "template" in self.authoring and not isinstance(self.authoring["template"], dict):
            raise ValueError("Authoring template must be an object")
        if "examples" in self.authoring and not isinstance(self.authoring["examples"], list):
            raise ValueError("Authoring examples must be an array")
        if len(canonical(self.authoring)) > 524288:
            raise ValueError("Bounded authoring part required")
        if set(form) - {
            "schemaVersion",
            "profileId",
            "version",
            "catalogWorkflowName",
            "templateId",
            "handoverName",
            "agentMode",
            "storage",
            "domainPlugin",
            "exportCapabilities",
            "contractStatus",
            "titleField",
            "contract",
            "sections",
            "coverageDimensions",
            "edgeCases",
            "guidance",
            "workedExamples",
        }:
            raise ValueError(
                "Unsupported authoring metadata; personnel records do not belong in templates"
            )
        if form.get("schemaVersion") != "praxis.template_profile.v1" or not isinstance(
            form.get("profileId"), str
        ):
            raise ValueError("Exact Praxis form schema/profile identity required")
        sections = form.get("sections")
        if (
            not isinstance(sections, list)
            or any(not isinstance(s, dict) for s in sections)
            or [s.get("key") for s in sections] != ["S" + str(i) for i in range(1, 9)]
        ):
            raise ValueError("Exactly ordered S1–S8 sections required")

        def fields(items, depth=0):
            if depth > 8 or not isinstance(items, list) or len(items) > 100:
                raise ValueError("Bounded form fields required")
            ids = []
            for field in items:
                if (
                    not isinstance(field, dict)
                    or not isinstance(field.get("type"), str)
                    or field.get("type") not in FIELD_TYPES
                    or not isinstance(field.get("key"), str)
                ):
                    raise ValueError("Unsupported Praxis field definition")
                ids.append(field["key"])
                for bound in ("min", "max"):
                    if bound in field and type(field[bound]) not in (int, float):
                        raise ValueError("Numeric form bounds required")
                if "options" in field and not isinstance(field["options"], list):
                    raise ValueError("Form options must be an array")
                if field["type"] == "criterion" and field.get("visibility") != "private_rubric":
                    raise ValueError("Rubric criteria must be private_rubric")
                if (
                    field["key"] in {"expectedValue", "referenceValue"}
                    and field.get("visibility") not in PRIVATE_VISIBILITIES
                ):
                    raise ValueError("Reference fields must be private")
                condition = field.get("required", False)
                if type(condition) is not bool:
                    if (
                        not isinstance(condition, dict)
                        or set(condition) != {"anyOf"}
                        or not isinstance(condition["anyOf"], list)
                        or not 1 <= len(condition["anyOf"]) <= 20
                    ):
                        raise ValueError("Unsupported required-field condition")
                    for test in condition["anyOf"]:
                        if (
                            not isinstance(test, dict)
                            or set(test) != {"field", "equals"}
                            or not isinstance(test["field"], str)
                            or not re.fullmatch(r"S[1-8]\.[A-Za-z][A-Za-z0-9_.]*", test["field"])
                        ):
                            raise ValueError("Unsupported field condition reference")
                if "itemFields" in field:
                    fields(field["itemFields"], depth + 1)
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate form field key")

        for section in sections:
            fields(section.get("fields", []))
        if isinstance(self.execution, MarketingExecution):
            if (
                form.get("profileId") != "veyra-hush-one-launch-v1"
                or form.get("agentMode") != "MULTI"
            ):
                raise ValueError(
                    "Marketing v3 requires the exact reusable five-role authoring profile"
                )
            return self  # v3 validates its distinct tool/output/graph/rubric shape.
        schema_definition(self.execution.output_schema)
        if (
            any(e.evidence_source == "output" for e in self.execution.evaluators)
            and self.execution.output_schema.get("type") != "object"
        ):
            raise ValueError("Output-reference evaluators require a structured output object")
        if schema_errors(self.execution.conformance_output, self.execution.output_schema):
            raise ValueError("Conformance output must satisfy the declared schema")
        for tool in self.execution.tools:
            if tool.response_mode == "environment" and (
                self.execution.environment.id != "golden-kyc-openenv-v2"
                or self.execution.catalogue_version not in {"1.1.0", "1.2.0"}
            ):
                raise ValueError("Environment tools require the explicit native Golden catalogue")
            for value in (tool.input_schema, tool.output_schema, tool.error_schema):
                schema_definition(value)
        for group in (self.execution.tools, self.execution.evaluators, self.execution.rules):
            ids = [getattr(x, "criterion_id", None) or x.id for x in group]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate execution ID")
        return self


class TemplateSpec(TemplateProposal):
    """Only Praxis assigns the stable lineage and published integer version."""

    template_id: str
    version: int = Field(ge=1, le=9007199254740991)

    @model_validator(mode="after")
    def identity(self):
        UUID(self.template_id)
        return self


class FileRef(Model):
    path: str = Field(min_length=1, max_length=240)
    sha256: Sha


class PrivateRef(FileRef):
    purpose: Literal["grader_only_reference_and_rubric"]
    access: Literal["private_rubric"]


class TemplateRef(Model):
    id: Identifier
    version: int = Field(ge=1, le=9007199254740991)
    sha256: Sha


class TaskEntry(Model):
    task_id: Identifier
    revision_id: Identifier
    template: TemplateRef
    form: FileRef
    actor: FileRef
    private_assets: list[PrivateRef] = Field(min_length=1, max_length=1)
    agent_mode: Literal["SINGLE", "MULTI"]
    review: dict

    @model_validator(mode="after")
    def review_shape(self):
        if set(self.review) != {"status", "revision_id", "receipt_ref"} or any(
            type(v) is not str for v in self.review.values()
        ):
            raise ValueError("Only opaque status/revision/receipt review provenance is allowed")
        return self


class RevocationEvent(Model):
    schema_version: Literal["anvil.template-revocation.v1"]
    event_id: str
    environment: Literal["qa", "staging", "local"]
    project_id: str
    anvil_template_key: Identifier
    template_id: str
    version: int = Field(ge=1)
    template_sha256: Sha
    receipt_id: str
    receipt_hash: Sha
    status: Literal["revoked"]
    reason: str = Field(min_length=1, max_length=1000)
    sequence: int = Field(ge=1)

    @model_validator(mode="after")
    def identities(self):
        for value in (self.event_id, self.project_id, self.template_id, self.receipt_id):
            UUID(value)
        return self


class Batch(Model):
    id: Identifier
    part_index: int = Field(ge=1, le=10000)
    part_count: int = Field(ge=1, le=10000)

    @model_validator(mode="after")
    def ordered(self):
        if self.part_index > self.part_count:
            raise ValueError("Batch part exceeds count")
        return self


class Export(Model):
    schema_version: Literal[EXPORT]
    package_id: Identifier
    package_version: Identifier
    batch: Batch
    content_classification: Literal["synthetic"]
    tasks: list[TaskEntry] = Field(min_length=1, max_length=200)
    execution: dict


class ReusableTaskEntry(TaskEntry):
    case_selector: CaseSelector


class ReusableExport(Export):
    """Dataset selection belongs to the export, never the authored workflow."""

    schema_version: Literal[EXPORT_V2]
    case_dataset: CaseDatasetRef
    tasks: list[ReusableTaskEntry] = Field(min_length=5, max_length=5)


class CampaignTaskEntry(TaskEntry):
    case_selector: CampaignSelector
    agent_mode: Literal["MULTI"]


class CampaignExport(Export):
    schema_version: Literal[EXPORT_V2]
    case_dataset: CaseDatasetRef
    tasks: list[CampaignTaskEntry] = Field(min_length=1, max_length=1)


def weight_bps(value):
    if type(value) not in (int, float):
        raise ValueError("Numeric weight required")
    weight = Decimal(str(value)) * 100
    if weight != weight.to_integral_value() or not 0 < weight <= 10000:
        raise ValueError("Positive weight with at most two decimal places required")
    return int(weight)
