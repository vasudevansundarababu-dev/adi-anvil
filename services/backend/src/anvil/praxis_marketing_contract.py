"""Explicit Marketing v3/v2-family contracts; no reinterpretation of KYC/v1.

Acceptance of bytes is structural interoperability, never runtime qualification,
human publication, a calibrated semantic award or permission to spend.
"""

import hashlib
from typing import Literal

import rfc8785
from pydantic import Field, model_validator

from anvil.dataset_export_contract import Identifier, Model, Sha
from anvil.marketing_task2_contract import CRITICAL, GROUPS, WIRE_ROLES
from anvil.praxis_case_dataset import CaseDatasetRef


def fingerprint(value):
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def bounded_schema(schema, depth=0):
    allowed = {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "oneOf",
        "description",
        "title",
    }
    if not isinstance(schema, dict) or set(schema) - allowed or depth > 16:
        raise ValueError("Unsupported bounded Marketing JSON schema")
    if "type" in schema and schema["type"] not in {
        "object",
        "array",
        "string",
        "integer",
        "number",
        "boolean",
        "null",
    }:
        raise ValueError("Unsupported schema type")
    if not any(
        key in schema for key in ("type", "const", "enum", "properties", "required", "oneOf")
    ):
        raise ValueError("Schema must declare a constraint")
    for key in ("minLength", "maxLength", "minItems", "maxItems"):
        if key in schema and (type(schema[key]) is not int or not 0 <= schema[key] <= 1048576):
            raise ValueError("Bounded nonnegative schema limits required")
    for key in ("minimum", "maximum"):
        if key in schema and type(schema[key]) not in (int, float):
            raise ValueError("Numeric schema limit required")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or len(properties) > 200:
        raise ValueError("Bounded schema property map required")
    for child in properties.values():
        bounded_schema(child, depth + 1)
    if "items" in schema:
        bounded_schema(schema["items"], depth + 1)
    if "oneOf" in schema:
        if not isinstance(schema["oneOf"], list) or not 1 <= len(schema["oneOf"]) <= 10:
            raise ValueError("Bounded oneOf alternatives required")
        for child in schema["oneOf"]:
            bounded_schema(child, depth + 1)
    if "required" in schema and (
        not isinstance(schema["required"], list)
        or any(type(x) is not str for x in schema["required"])
        or len(schema["required"]) != len(set(schema["required"]))
    ):
        raise ValueError("Unique required property names required")
    if "additionalProperties" in schema and type(schema["additionalProperties"]) is not bool:
        raise ValueError("Only boolean additionalProperties is supported")
    rfc8785.dumps(schema)


def graph_check(graph):
    if (
        not isinstance(graph, dict)
        or graph.get("schemaVersion") != "praxis.workflow_graph.v1-proposed"
        or graph.get("agentMode") != "MULTI"
    ):
        raise ValueError("Exact proposed Marketing MULTI graph contract required")
    if set(graph) != {
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
        raise ValueError("Unexpected graph metadata")
    indexes = {}
    for kind, maximum in (
        ("roles", 5),
        ("nodes", 100),
        ("edges", 300),
        ("artifacts", 100),
        ("loops", 20),
    ):
        values = graph[kind]
        if (
            not isinstance(values, list)
            or not 1 <= len(values) <= maximum
            or any(not isinstance(v, dict) or not isinstance(v.get("id"), str) for v in values)
        ):
            raise ValueError("Bounded identified graph collections required")
        indexes[kind] = {v["id"]: v for v in values}
        if len(indexes[kind]) != len(values):
            raise ValueError("Duplicate graph identity")
    if set(indexes["roles"]) != set(WIRE_ROLES):
        raise ValueError("Exactly the five canonical role identities are required")
    allowed_types = {
        "input",
        "agent_step",
        "decision",
        "join",
        "human_step",
        "external_system",
        "output",
        "escalation",
    }
    nodes, artifacts = indexes["nodes"], indexes["artifacts"]
    for node in nodes.values():
        if node.get("type") not in allowed_types:
            raise ValueError("Unknown Marketing graph node type")
        if node["type"] == "agent_step" and node.get("roleId") not in WIRE_ROLES:
            raise ValueError("Agent step must bind one canonical role")
        if node["type"] == "human_step" and node.get("simulated") is not True:
            raise ValueError("Task2 environment approval must explicitly remain simulated")
        if node["type"] == "external_system" and (
            node.get("roleId")
            or node.get("system") != "Task3 media production and DAM (environment fixture)"
        ):
            raise ValueError("Task3 is the external production boundary, never a sixth agent")
        for name in (
            "inputRefs",
            "requiredInputs",
            "optionalInputs",
            "sendsRefs",
            "permittedEvidence",
        ):
            values = node.get(name, [])
            valid = (
                all(
                    value in nodes and nodes[value].get("outputArtifact") in artifacts
                    for value in values
                )
                if node["type"] == "join" and name in {"requiredInputs", "optionalInputs"}
                else all(value in artifacts for value in values)
            )
            if not valid:
                raise ValueError("Unresolved graph input artifact")
        for name in ("outputArtifact", "returnsArtifact", "deliverable"):
            if node.get(name) and node[name] not in artifacts:
                raise ValueError("Unresolved graph output artifact")
    for edge in indexes["edges"].values():
        if edge.get("from") not in nodes or edge.get("to") not in nodes:
            raise ValueError("Graph edge must resolve both endpoints")
    bounds = {loop["id"]: loop.get("maxIterations") for loop in indexes["loops"].values()}
    if bounds != {
        "creative_revision": 2,
        "plan_revision": 2,
        "approval_revision": 2,
        "weekly_cycle": 12,
    } or graph["limits"] != {"maxTransitions": 400}:
        raise ValueError("Exact two-revision/twelve-week/400-transition protocol required")
    for loop in indexes["loops"].values():
        if (
            loop.get("returnEdgeId") not in indexes["edges"]
            or nodes.get(loop.get("exhaustedTarget"), {}).get("type") != "escalation"
        ):
            raise ValueError("Every bounded loop requires an explicit exhaustion escalation")
    return graph


class Capability(Model):
    id: Identifier
    version: Identifier


class MarketingTool(Model):
    id: Identifier
    role_ids: list[Literal["orchestrator", "intent", "performance", "brief", "policy"]] = Field(
        min_length=1, max_length=5
    )
    input_schema: dict
    output_schema: dict
    error_schema: dict

    @model_validator(mode="after")
    def schemas(self):
        if len(self.role_ids) != len(set(self.role_ids)):
            raise ValueError("Duplicate authorized tool role")
        for schema in (self.input_schema, self.output_schema, self.error_schema):
            bounded_schema(schema)
        return self


class MarketingEvaluator(Model):
    criterion_id: Identifier
    native_criterion_id: Identifier
    group: Literal["A", "B", "C", "D", "E", "F", "G"]
    weight: int = Field(ge=1, le=100, strict=True)
    capability: Capability
    evidence_source: Literal["run_evidence"]


class MarketingExecution(Model):
    schema_version: Literal["anvil.template-execution.v3"]
    catalogue_version: Literal["1.3.0"]
    environment: Capability
    evaluators: list[MarketingEvaluator] = Field(min_length=23, max_length=23)
    tools: list[MarketingTool] = Field(min_length=1, max_length=50)
    isolation: Literal["per_campaign_episode"]
    output_schema: dict
    paid_calls: Literal[False]
    rubric: dict
    rubric_source: dict
    workflow_graph: dict
    workflow_graph_sha256: Sha
    dataset_binding: dict

    @model_validator(mode="after")
    def exact_contract(self):
        if self.environment.model_dump() != {"id": "marketing-task2-us-v1", "version": "1"}:
            raise ValueError("Exact Marketing environment capability required")
        if self.rubric != {
            "scale": "zero_to_four",
            "formula": "criterion weight * level / 4",
            "groups": GROUPS,
            "minimum": {"total": 80, "adaptation": 12},
            "critical_rule_ids": sorted(CRITICAL),
        }:
            raise ValueError("Exact native Marketing rubric and gates required")
        if (
            set(self.rubric_source) != {"version", "sha256"}
            or not self.rubric_source["version"]
            or len(self.rubric_source["sha256"]) != 64
        ):
            raise ValueError("Version/hash of reviewed native anchors required")
        if self.dataset_binding != {
            "schema_version": "anvil.campaign-case-dataset.v1",
            "count_source": "qualified_dataset_membership",
            "selector": {"field": "dataset", "value": "all"},
        }:
            raise ValueError("One reusable campaign selects the whole qualified case dataset")
        graph_check(self.workflow_graph)
        if fingerprint(self.workflow_graph) != self.workflow_graph_sha256:
            raise ValueError("Exact graph hash mismatch")
        bounded_schema(self.output_schema)
        tools = {t.id: t for t in self.tools}
        if len(tools) != len(self.tools):
            raise ValueError("Duplicate tool identity")
        for role in self.workflow_graph["roles"]:
            actual = {tool.id for tool in self.tools if role["id"] in tool.role_ids}
            if actual != set(role["tools"]):
                raise ValueError("Role tool contracts must exactly match the bound graph")
        if (
            len({e.criterion_id for e in self.evaluators}) != 23
            or len({e.native_criterion_id for e in self.evaluators}) != 23
        ):
            raise ValueError("Exactly23 unique source/native criterion mappings required")
        from anvil.golden_targets import definitions

        source_indexes = {}
        exact = {}
        for row in definitions("marketing"):
            if not row["official"]:
                continue
            group = row["id"].split(".", 1)[0]
            source_indexes[group] = source_indexes.get(group, 0) + 1
            exact[group + str(source_indexes[group])] = (
                row["id"],
                group,
                row["maximum_contribution"],
            )
        if {
            e.criterion_id: (e.native_criterion_id, e.group, e.weight) for e in self.evaluators
        } != exact:
            raise ValueError(
                "Exact approved source/native criterion identities and weights required"
            )
        for group, total in GROUPS.items():
            entries = [e for e in self.evaluators if e.group == group]
            if sum(e.weight for e in entries) != total or any(
                not e.native_criterion_id.startswith(group + ".")
                or e.capability.model_dump()
                != {"id": "marketing-task2-evidence-v1", "version": "1"}
                for e in entries
            ):
                raise ValueError(
                    "Exact native group/criterion weights and evaluator capability required"
                )
        return self


class CampaignSelector(Model):
    field: Literal["dataset"]
    value: Literal["all"]
    case_count: int = Field(ge=1, le=10000)


class CampaignMember(Model):
    id: Identifier
    snapshot_sha256: Sha
    locale: Literal["en-US", "en-IN", "hi-IN", "fr-FR", "en-SG"]


class CampaignDataset(Model):
    schema_version: Literal["anvil.campaign-case-dataset.v1"]
    id: Identifier
    version: Identifier
    case_count: int = Field(ge=1, le=10000)
    cases: list[CampaignMember] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def membership(self):
        identifiers = [c.id for c in self.cases]
        if len(identifiers) != self.case_count or identifiers != sorted(set(identifiers)):
            raise ValueError("Exact count and sorted unique campaign membership required")
        return self

    def reference(self):
        return CaseDatasetRef(
            id=self.id,
            version=self.version,
            sha256=fingerprint(self.model_dump()),
            case_count=self.case_count,
        )

    def select(self, reference, selector):
        if reference != self.reference() or selector.case_count != self.case_count:
            raise ValueError("Campaign dataset identity/version/hash/count mismatch")
        return self.cases
