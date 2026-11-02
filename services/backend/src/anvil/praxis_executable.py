"""Description-first executable import contract. Validation never executes source code."""

import hashlib
from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, model_validator

from anvil.praxis_contract import Identifier, Model, Text
from anvil.task_parser import json_value


class Asset(Model):
    id: Identifier
    path: str = Field(min_length=1, max_length=200)
    media_type: Literal["application/json", "text/plain", "text/csv"]
    visibility: Literal["actor", "evaluation_private"]
    content: str = Field(max_length=262144)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def integrity(self):
        safe_relative(self.path)
        if len(self.content.encode()) > 262144:
            raise ValueError("Input asset exceeds byte limit")
        if self.media_type == "application/json":
            json_value(self.content.encode())
        if hashlib.sha256(self.content.encode()).hexdigest() != self.sha256:
            raise ValueError("Input asset hash mismatch: " + self.id)
        return self


def safe_relative(path):
    if (
        PurePosixPath(path).is_absolute()
        or "\\" in path
        or ":" in path
        or any(p in ("", ".", "..") or p.startswith(".") for p in path.split("/"))
        or any(ord(c) < 32 for c in path)
    ):
        raise ValueError("Unsafe relative asset/output path")


class Environment(Model):
    image_reference: str = Field(min_length=1, max_length=250)
    digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    digest_kind: Literal["oci_manifest", "docker_image_id"]
    network: Literal["none"]
    seed: int = Field(ge=0, le=2147483647, strict=True)
    cpus: int = Field(ge=1, le=4, strict=True)
    memory_mb: int = Field(ge=128, le=4096, strict=True)
    reset_description: Text

    @model_validator(mode="after")
    def image_not_a_secret_url(self):
        if "://" in self.image_reference or any(c.isspace() for c in self.image_reference):
            raise ValueError("Use a Docker image reference, not a URL")
        if "@" in self.image_reference and not self.image_reference.rsplit("@", 1)[1].startswith(
            "sha256:"
        ):
            raise ValueError("Image references cannot contain embedded credentials")
        return self


class ProbeSetup(Model):
    tool: Identifier
    arguments: dict


class Probe(Model):
    arguments: dict
    expected_description: Text
    safe_in_disposable_environment: Literal[True]
    setup_calls: list[ProbeSetup] = Field(default_factory=list, max_length=10)


class Tool(Model):
    id: Identifier
    description: Text
    input_schema: dict
    output_schema: dict
    effect: Literal["read_only", "workspace_write", "prohibited"]
    probe: Probe | None


class Server(Model):
    id: Identifier
    transport: Literal["stdio"]
    protocol_version: Literal["2025-06-18"]
    command: list[str] = Field(min_length=1, max_length=10)
    tools: list[Tool] = Field(min_length=1, max_length=30)


class Criterion(Model):
    id: Identifier
    description: Text
    weight_bps: int = Field(ge=1, le=10000, strict=True)
    phase: Literal["dense", "terminal"]


class Constraint(Model):
    id: Identifier
    description: Text
    phase: Literal["runtime", "final", "both"]
    hard_fail: bool
    penalty_bps: int = Field(ge=0, le=10000, strict=True)
    prohibited_tools: list[Identifier] = Field(max_length=20)


class Call(Model):
    tool: Identifier
    arguments: dict


class Fixture(Model):
    id: Identifier
    kind: Literal["good", "bad", "empty", "guardrail", "boundary"]
    output: dict | None
    observed_calls: list[Call] = Field(max_length=100)
    expected_reward_bps: int = Field(ge=0, le=10000, strict=True)
    expected_checks: dict[str, bool]
    covers: list[Identifier] = Field(min_length=1)


class PrivateEvaluation(Model):
    classification: Literal["synthetic_test_oracle"]
    canary: str = Field(min_length=10, max_length=100)
    fixtures: list[Fixture] = Field(min_length=4, max_length=30)


class TaskV3(Model):
    schema_version: Literal["praxis.anvil.task.v3"]
    task_id: Identifier
    task_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    revision_id: Identifier
    title: Text
    domain: Literal["marketing", "kyc_aml", "fraud"]
    objective: Text
    instructions: Text
    inputs: list[Asset] = Field(min_length=1, max_length=100)
    output_path: Literal["output.json"]
    output_schema: dict
    environment: Environment
    mcp_servers: list[Server] = Field(min_length=1, max_length=5)
    criteria: list[Criterion] = Field(min_length=1, max_length=30)
    constraints: list[Constraint] = Field(min_length=1, max_length=30)
    pass_threshold_bps: int = Field(ge=1, le=10000, strict=True)
    max_steps: int = Field(ge=1, le=100, strict=True)
    timeout_seconds: int = Field(ge=1, le=1800, strict=True)
    evaluation_private: PrivateEvaluation | None = None
    provenance: dict

    @model_validator(mode="after")
    def consistent(self):
        ids = [self.task_id]
        fixtures = self.evaluation_private.fixtures if self.evaluation_private else []
        ids.extend(
            item.id
            for group in (
                self.inputs,
                self.mcp_servers,
                self.criteria,
                self.constraints,
                fixtures,
            )
            for item in group
        )
        tools = [tool for server in self.mcp_servers for tool in server.tools]
        ids.extend(tool.id for tool in tools)
        if len(ids) != len(set(ids)):
            raise ValueError("IDs must be globally unique in an executable task")
        if len({asset.path for asset in self.inputs}) != len(self.inputs):
            raise ValueError("Input paths must be unique")
        if sum(c.weight_bps for c in self.criteria) != 10000:
            raise ValueError("Positive rubric weights must sum to 10000 basis points")
        if self.provenance.get("classification") != "synthetic":
            raise ValueError(
                "This executable-import increment accepts explicit synthetic sources only"
            )
        tool_ids = {tool.id for tool in tools}
        rule_ids = {r.id for r in [*self.criteria, *self.constraints]}
        kinds = {f.kind for f in fixtures}
        if fixtures and not {"good", "bad", "empty", "guardrail"} <= kinds:
            raise ValueError("Golden coverage requires good, bad, empty and guardrail cases")
        if fixtures and not any(
            f.kind == "good" and f.expected_reward_bps == 10000 for f in fixtures
        ):
            raise ValueError("A full-reward positive fixture is required")
        covered = set()
        for fixture in fixtures:
            if not set(fixture.covers) <= rule_ids or not set(fixture.expected_checks) <= rule_ids:
                raise ValueError("Unknown fixture rule reference")
            if any(call.tool not in tool_ids for call in fixture.observed_calls):
                raise ValueError("Unknown fixture tool reference")
            covered.update(fixture.covers)
        if fixtures and covered != rule_ids:
            raise ValueError("Every criterion/constraint needs fixture coverage")
        for constraint in self.constraints:
            if not set(constraint.prohibited_tools) <= tool_ids:
                raise ValueError("Unknown prohibited tool")
        for tool in tools:
            if tool.effect == "prohibited" and not any(
                c.phase in ("runtime", "both") and tool.id in c.prohibited_tools
                for c in self.constraints
            ):
                raise ValueError("Prohibited tools require a runtime constraint mapping")
            if tool.probe and any(
                call.tool not in tool_ids
                or next(t for t in tools if t.id == call.tool).effect == "prohibited"
                for call in tool.probe.setup_calls
            ):
                raise ValueError("Probe setup must reference a declared non-prohibited tool")
            if (
                tool.input_schema.get("type") != "object"
                or tool.output_schema.get("type") != "object"
            ):
                raise ValueError("Tool schemas must be objects")
            if tool.effect != "prohibited" and tool.probe is None:
                raise ValueError("Executable tools require a safe disposable probe")
        return self


def parse(raw):
    if len(raw) > 1048576:
        raise ValueError("Executable source exceeds 1 MiB")
    return TaskV3.model_validate(json_value(raw))


def actor_view(task):
    """Explicit allowlist: no private cases, reward expectations, probes or code."""
    return {
        "schema_version": task.schema_version,
        "task_id": task.task_id,
        "task_version": task.task_version,
        "title": task.title,
        "objective": task.objective,
        "instructions": task.instructions,
        "evidence": [
            asset.model_dump(exclude={"sha256"})
            for asset in task.inputs
            if asset.visibility == "actor"
        ],
        "output_path": task.output_path,
        "output_schema": task.output_schema,
        "actions": [
            {
                "id": tool.id,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
            }
            for server in task.mcp_servers
            for tool in server.tools
            if tool.effect != "prohibited"
        ],
        "constraints": [{"id": c.id, "description": c.description} for c in task.constraints],
        "rubric": [
            {"id": c.id, "description": c.description, "weight_bps": c.weight_bps}
            for c in task.criteria
        ],
        "environment": {
            "binding": "tool-agent-v1",
            "image_digest": task.environment.digest,
            "image_reference": task.environment.image_reference,
            "digest_kind": task.environment.digest_kind,
        },
        "max_steps": task.max_steps,
        "timeout_seconds": task.timeout_seconds,
    }
