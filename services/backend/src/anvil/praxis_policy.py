"""Optional Project policy sidecar. This validates data, never installs an evaluator."""

import hashlib
import re
from typing import Annotated, Literal

from pydantic import Field, model_validator

from anvil.praxis_contract import Identifier, Model, Text
from anvil.task_parser import json_value

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_SOURCE_BYTES = 10 * 1024 * 1024


class Project(Model):
    id: Identifier
    version: Identifier
    name: Text


class PolicyRef(Model):
    policy_id: Identifier
    version: Identifier


class PolicySource(Model):
    id: Identifier
    path: Annotated[str, Field(min_length=1, max_length=240)]
    media_type: Literal[
        "text/plain",
        "text/markdown",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    size_bytes: int = Field(ge=0, le=MAX_SOURCE_BYTES)
    sha256: Hash

    @model_validator(mode="after")
    def safe_path(self):
        # Canonical portable paths only: no traversal, URL, escape, drive or aliases.
        if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", self.path):
            raise ValueError("Source path must be a portable relative package path")
        if any(p in (".", "..") or p.startswith(".") for p in self.path.split("/")):
            raise ValueError("Hidden, alias and traversal paths are unsupported")
        return self


class PolicyRule(Model):
    rule_id: Identifier
    requirement: Text
    source_location: Text
    severity: Literal["critical", "high", "medium", "low"]
    visibility: Literal["agent_instruction", "evaluator_only"]
    rubric_criterion_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    failure_mode_ids: list[Identifier] = Field(default_factory=list, max_length=100)


class Policy(Model):
    policy_id: Identifier
    version: Identifier
    title: Text
    source_id: Identifier
    rules: list[PolicyRule] = Field(max_length=500)


class TaskPolicyBinding(Model):
    task_id: Identifier
    task_version: Identifier
    payload_sha256: Hash
    # Effective scope is explicit, including Project inheritance/exclusions.
    policy_refs: list[PolicyRef] = Field(max_length=100)
    excluded_project_policy_refs: list[PolicyRef] = Field(default_factory=list, max_length=100)


def unique(values, label):
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label}")


class ProjectPolicyManifest(Model):
    schema_version: Literal["praxis.anvil.project_policy.v1"]
    source_project: Project
    project_default_policy_refs: list[PolicyRef] = Field(max_length=100)
    sources: list[PolicySource] = Field(max_length=100)
    policies: list[Policy] = Field(max_length=100)
    task_bindings: list[TaskPolicyBinding] = Field(max_length=10000)

    @model_validator(mode="after")
    def references(self):
        source_ids = [s.id for s in self.sources]
        unique(source_ids, "source ID")
        unique([s.path.casefold() for s in self.sources], "source path")
        keys = [(p.policy_id, p.version) for p in self.policies]
        unique(keys, "policy identity/version")
        unique([(b.task_id, b.task_version) for b in self.task_bindings], "Task binding")
        defaults = {(r.policy_id, r.version) for r in self.project_default_policy_refs}
        unique([(r.policy_id, r.version) for r in self.project_default_policy_refs], "default")
        if not defaults <= set(keys):
            raise ValueError("Unresolved Project default policy")
        for policy in self.policies:
            if policy.source_id not in source_ids:
                raise ValueError("Unresolved policy source")
            unique([r.rule_id for r in policy.rules], "rule ID within policy")
        for binding in self.task_bindings:
            active = [(r.policy_id, r.version) for r in binding.policy_refs]
            excluded = [(r.policy_id, r.version) for r in binding.excluded_project_policy_refs]
            unique(active, "Task policy reference")
            unique(excluded, "Task exclusion")
            if not set(active) <= set(keys) or not set(excluded) <= defaults:
                raise ValueError("Unresolved Task policy reference or exclusion")
            if set(active) & set(excluded) or defaults - set(excluded) - set(active):
                raise ValueError("Effective scope must include every non-excluded Project default")
        return self


def validate_package(raw: bytes, files: dict[str, bytes], project: tuple[str, str], tasks: dict):
    """Caller supplies captured bytes and exact imported identities; no filesystem/network reads.

    tasks maps (Task ID, version) to its exact legacy payload SHA256 in this Project.
    This function confers no source authenticity, membership, readiness or execution authority.
    """
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Policy manifest exceeds 2 MiB")
    manifest = ProjectPolicyManifest.model_validate(json_value(raw))
    if (manifest.source_project.id, manifest.source_project.version) != project:
        raise ValueError("Source Project/version does not match import")
    expected = {s.path for s in manifest.sources}
    if set(files) != expected:
        raise ValueError("Policy package files must exactly match declared sources")
    if sum(len(v) for v in files.values()) > 25 * 1024 * 1024:
        raise ValueError("Policy sources exceed aggregate 25 MiB")
    for source in manifest.sources:
        data = files[source.path]
        if len(data) != source.size_bytes or hashlib.sha256(data).hexdigest() != source.sha256:
            raise ValueError(f"Source size/hash mismatch: {source.id}")
    for binding in manifest.task_bindings:
        if tasks.get((binding.task_id, binding.task_version)) != binding.payload_sha256:
            raise ValueError(f"Task/version/payload mismatch: {binding.task_id}")
    return manifest


def agent_instructions(manifest: ProjectPolicyManifest, task_id: str, task_version: str):
    """Explicit safe projection; never includes full source files or evaluator-only rules."""
    binding = next(
        (
            b
            for b in manifest.task_bindings
            if (b.task_id, b.task_version) == (task_id, task_version)
        ),
        None,
    )
    if binding is None:
        return []
    keys = {(r.policy_id, r.version) for r in binding.policy_refs}
    return [
        {
            "policy_id": p.policy_id,
            "policy_version": p.version,
            "rule_id": r.rule_id,
            "instruction": r.requirement,
        }
        for p in manifest.policies
        if (p.policy_id, p.version) in keys
        for r in p.rules
        if r.visibility == "agent_instruction"
    ]
