"""SME bundle v1 metadata. Parsing and signature checks never execute imported content."""

import base64
import binascii
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")]
Version = Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
Text = Annotated[str, Field(min_length=1, max_length=20000)]
Points = Annotated[int, Field(strict=True, ge=1, le=1000000)]
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_BYTES = 500 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024


def canonical_path(value: str) -> str:
    parts = value.split("/")
    if (
        len(value) > 240
        or len(parts) > 12
        or not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", p) for p in parts)
        or any(
            p.lower()
            in {
                "setup.py",
                "autorun.sh",
                "entrypoint.sh",
                "sitecustomize.py",
                "usercustomize.py",
                "install.sh",
            }
            or p.endswith(".pth")
            for p in parts
        )
    ):
        raise ValueError("Non-canonical or auto-run payload path")
    return value


def unique_paths(paths: list[str]) -> None:
    folded = {path.lower() for path in paths}
    if len(folded) != len(paths):
        raise ValueError("Duplicate or case-aliased path")
    for path in folded:
        parts = path.split("/")
        if any("/".join(parts[:i]) in folded for i in range(1, len(parts))):
            raise ValueError("File/directory path alias")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Exporter(Model):
    identity: Identifier
    version: Version


class Bank(Model):
    id: Identifier
    version: Version
    revision: Identifier
    title: Text


class Source(Model):
    owner: Text
    classification: Literal["original_synthetic_fixture", "partner_restricted", "public_licensed"]
    rights_references: list[Text] = Field(min_length=1, max_length=50)


class PayloadFile(Model):
    path: str
    byte_size: int = Field(ge=0, le=MAX_FILE_BYTES)
    sha256: Hash
    media_type: Literal[
        "text/markdown",
        "text/plain",
        "text/csv",
        "application/json",
        "application/pdf",
        "application/octet-stream",
    ]
    visibility: Literal["actor", "evaluation_private"]
    task_id: Identifier

    _path = field_validator("path")(canonical_path)


class Output(Model):
    path: str
    media_type: Literal["text/markdown", "application/json", "text/plain", "text/csv"]
    required: bool
    max_bytes: int = Field(ge=1, le=MAX_OUTPUT_BYTES)
    schema_ref: str | None = None

    @field_validator("path", "schema_ref")
    @classmethod
    def safe(cls, value):
        if value is not None:
            canonical_path(value)
        return value

    @model_validator(mode="after")
    def output_namespace(self):
        if self.path.split("/")[0].lower() in {
            "runtime_pack",
            "eval_pack",
            "manifest.json",
            "signature.json",
        }:
            raise ValueError("Output path collides with source namespace")
        return self


class Environment(Model):
    image_reference: str = Field(min_length=1, max_length=300)
    oci_manifest_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    cpus: int = Field(ge=1, le=4)
    memory_mb: int = Field(ge=128, le=4096)
    pids_limit: int = Field(ge=1, le=128)
    network: Literal["none"]

    @model_validator(mode="after")
    def pinned(self):
        name, separator, digest = self.image_reference.partition("@")
        if (
            not separator
            or digest != self.oci_manifest_digest
            or not re.fullmatch(r"[a-z0-9][a-z0-9._:/-]*", name)
            or "://" in name
            or ".." in name
        ):
            raise ValueError("Environment must bind a credential-free OCI digest reference")
        return self


class ToolServer(Model):
    id: Identifier
    version: Version
    transport: Literal["stdio"]
    schema_path: str
    schema_sha256: Hash
    command: list[str] = Field(min_length=1, max_length=10)
    tool_timeout_seconds: int = Field(ge=1, le=60)

    _path = field_validator("schema_path")(canonical_path)

    @field_validator("command")
    @classmethod
    def bounded_command(cls, value):
        if any(not v or len(v.encode()) > 1024 or any(ord(c) < 32 for c in v) for v in value):
            raise ValueError("Invalid stdio command declaration")
        return value


class Criterion(Model):
    id: Identifier
    category: Literal["criterion", "assignment", "justification"]
    possible_points: Points
    evaluator_type: Literal["deterministic", "semantic"]
    rule_ref: str
    evidence_requirement: Literal["sealed_output_span_or_absence"]
    applicability_rule: Literal["always"]

    _path = field_validator("rule_ref")(canonical_path)


class Constraint(Model):
    id: Identifier
    rule_ref: str
    hard_failure: bool

    _path = field_validator("rule_ref")(canonical_path)


class EvaluatorRequirement(Model):
    registry_id: Identifier
    version: Version
    implementation_sha256: Hash
    image_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    policy_sha256: Hash


class CompilerRequirement(Model):
    profile: Literal["sme-artifact-v1"]
    version: Version


class Task(Model):
    id: Identifier
    version: Version
    revision: Identifier
    domain: Identifier
    prompt_path: str
    actor_asset_paths: list[str] = Field(max_length=100)
    outputs: list[Output] = Field(min_length=1, max_length=10)
    timeout_seconds: int = Field(ge=1, le=1800)
    environment: Environment
    tools: list[ToolServer] = Field(min_length=1, max_length=10)
    criteria: list[Criterion] = Field(min_length=1, max_length=1000)
    constraints: list[Constraint] = Field(max_length=100)
    evaluator_requirement: EvaluatorRequirement
    calibration_paths: list[str] = Field(min_length=1, max_length=100)

    _path = field_validator("prompt_path")(canonical_path)

    @field_validator("actor_asset_paths", "calibration_paths")
    @classmethod
    def paths(cls, value):
        for path in value:
            canonical_path(path)
        if len(value) != len(set(value)):
            raise ValueError("Duplicate task asset path")
        return value

    @model_validator(mode="after")
    def unique_members(self):
        for items in [
            [c.id for c in [*self.criteria, *self.constraints]],
            [s.id for s in self.tools],
            [o.path.lower() for o in self.outputs],
        ]:
            if len(items) != len(set(items)):
                raise ValueError("Duplicate task member")
        unique_paths([o.path for o in self.outputs])
        if sum(o.max_bytes for o in self.outputs) > MAX_OUTPUT_BYTES:
            raise ValueError("Total output quota exceeds limit")
        return self


class Scoring(Model):
    profile: Literal["sme_points_v1", "bodhium_pilot_v1"]
    policy_version: Version
    task_maxima: dict[Identifier, Points] = Field(min_length=1, max_length=100)
    suite_maximum: Points
    hard_constraint_policy: Literal["zero_official_keep_diagnostics"]
    valid_trial_policy: Literal["model_failure_zero_operational_invalid"]
    display_rounding: Literal["half_up_2dp"]


class Manifest(Model):
    schema_version: Literal["praxis.anvil.benchmark_bundle.v1"]
    signature_profile: Literal["ed25519-jcs-v1"]
    exporter: Exporter
    bank: Bank
    exported_at: str
    source: Source
    files: list[PayloadFile] = Field(min_length=1, max_length=5000)
    tasks: list[Task] = Field(min_length=1, max_length=100)
    scoring: Scoring
    compiler_requirement: CompilerRequirement

    @field_validator("exported_at")
    @classmethod
    def utc(cls, value):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
            raise ValueError("Export timestamp must use UTC seconds")
        datetime.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def consistent(self):
        task_ids = {t.id for t in self.tasks}
        if len(task_ids) != len(self.tasks):
            raise ValueError("Duplicate task identity")
        members = {f.path: f for f in self.files}
        unique_paths([f.path for f in self.files])
        if sum(f.byte_size for f in self.files) > MAX_EXPANDED_BYTES:
            raise ValueError("Expanded payload exceeds limit")
        for file in self.files:
            prefix = "runtime_pack" if file.visibility == "actor" else "eval_pack"
            if file.task_id not in task_ids or not file.path.startswith(
                f"{prefix}/{file.task_id}/"
            ):
                raise ValueError("Payload ownership or visibility mismatch")
        maxima = {t.id: sum(c.possible_points for c in t.criteria) for t in self.tasks}
        if self.scoring.task_maxima != maxima or self.scoring.suite_maximum != sum(maxima.values()):
            raise ValueError("Criterion/task/suite point totals disagree")
        for task in self.tasks:

            def owned(path, visibility):
                file = members.get(path)
                if file is None or file.task_id != task.id or file.visibility != visibility:
                    raise ValueError("Missing, foreign or wrong-visibility dependency")
                return file

            actor_paths = [task.prompt_path, *task.actor_asset_paths]
            actor_paths += [t.schema_path for t in task.tools]
            actor_paths += [o.schema_ref for o in task.outputs if o.schema_ref is not None]
            for path in actor_paths:
                owned(path, "actor")
            if set(actor_paths) != {
                f.path for f in self.files if f.task_id == task.id and f.visibility == "actor"
            }:
                raise ValueError("Undeclared actor dependency")
            for tool in task.tools:
                file = owned(tool.schema_path, "actor")
                if file.sha256 != tool.schema_sha256 or file.media_type != "application/json":
                    raise ValueError("Tool schema binding mismatch")
                if tool.tool_timeout_seconds > task.timeout_seconds:
                    raise ValueError("Tool deadline exceeds task deadline")
            for path in [
                *(c.rule_ref for c in [*task.criteria, *task.constraints]),
                *task.calibration_paths,
            ]:
                owned(path, "evaluation_private")
        if self.scoring.profile == "bodhium_pilot_v1":
            if self.source.classification == "original_synthetic_fixture":
                raise ValueError("Fictional fixtures are not Bodhium source")
            if maxima != {"BL-001": 24, "BL-002": 6, "BL-003": 51}:
                raise ValueError("Bodhium requires exact task identities and 24/6/51 points")
            tasks = {t.id: t for t in self.tasks}
            if any(
                len(t.criteria) != maxima[t.id] or any(c.possible_points != 1 for c in t.criteria)
                for t in self.tasks
            ):
                raise ValueError("Bodhium requires all 81 explicit unit-point criteria")
            categories = [c.category for c in tasks["BL-003"].criteria]
            if categories.count("assignment") != 10 or categories.count("justification") != 41:
                raise ValueError("Bodhium requires 10 assignments and 41 justification checkpoints")
        return self


def _json(raw: bytes):
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Metadata exceeds byte limit")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("Non-finite JSON number")

    def check(value, depth=0):
        if depth > 32:
            raise ValueError("Metadata exceeds nesting limit")
        if isinstance(value, dict):
            for key, child in value.items():
                check(key, depth + 1)
                check(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                check(child, depth + 1)
        elif isinstance(value, str):
            value.encode("utf-8")
            if "\0" in value:
                raise ValueError("NUL metadata")
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite JSON number")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
        check(value)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("Malformed UTF-8 metadata") from exc
    return value


@dataclass(frozen=True)
class ParsedManifest:
    manifest: Manifest
    raw: bytes
    canonical: bytes
    raw_sha256: str
    canonical_sha256: str


def parse_manifest(raw: bytes) -> ParsedManifest:
    value = _json(raw)
    manifest = Manifest.model_validate(value)
    canonical = rfc8785.dumps(value)
    return ParsedManifest(
        manifest,
        raw,
        canonical,
        hashlib.sha256(raw).hexdigest(),
        hashlib.sha256(canonical).hexdigest(),
    )


class Signature(Model):
    profile: Literal["ed25519-jcs-v1"]
    key_id: Identifier
    algorithm: Literal["Ed25519"]
    signature_base64: str = Field(min_length=88, max_length=88)

    def decoded(self):
        try:
            result = base64.b64decode(self.signature_base64, validate=True)
        except binascii.Error as exc:
            raise ValueError("Malformed signature encoding") from exc
        if len(result) != 64 or base64.b64encode(result).decode() != self.signature_base64:
            raise ValueError("Non-canonical signature encoding")
        return result


@dataclass(frozen=True)
class TrustedSigner:
    key_id: str
    public_key: bytes
    not_before: datetime
    not_after: datetime
    revoked: bool = False

    def __post_init__(self):
        if (
            self.not_before.utcoffset() is None
            or self.not_after.utcoffset() is None
            or self.not_before >= self.not_after
            or len(self.public_key) != 32
        ):
            raise ValueError("Invalid installation signer policy")


@dataclass(frozen=True)
class SignatureDecision:
    status: str
    key_id: str | None
    raw_sha256: str
    canonical_sha256: str


def verify_signature(
    raw: bytes, signature_raw: bytes | None, *, signers: dict[str, TrustedSigner], now: datetime
) -> SignatureDecision:
    parsed = parse_manifest(raw)
    if now.utcoffset() is None:
        raise ValueError("Signature policy time must be timezone-aware")
    status, key_id = "quarantined_unsigned", None
    if signature_raw is not None:
        signature = Signature.model_validate(_json(signature_raw))
        signature_bytes = signature.decoded()
        key_id = signature.key_id
        signer = signers.get(key_id)
        if signer is None:
            status = "quarantined_unknown_signer"
        elif signer.key_id != key_id:
            raise ValueError("Invalid installation signer mapping")
        elif signer.revoked:
            status = "quarantined_revoked_signer"
        elif not signer.not_before <= now < signer.not_after:
            status = "quarantined_expired_signer"
        else:
            try:
                Ed25519PublicKey.from_public_bytes(signer.public_key).verify(
                    signature_bytes, parsed.canonical
                )
            except InvalidSignature as exc:
                raise ValueError("Signature verification failed") from exc
            status = "verified"
    return SignatureDecision(status, key_id, parsed.raw_sha256, parsed.canonical_sha256)


def actor_view(manifest: Manifest, task_id: str) -> dict:
    task = next((t for t in manifest.tasks if t.id == task_id), None)
    if task is None:
        raise ValueError("Unknown task")
    paths = {
        task.prompt_path,
        *task.actor_asset_paths,
        *(t.schema_path for t in task.tools),
        *(o.schema_ref for o in task.outputs if o.schema_ref is not None),
    }
    return {
        "profile": "sme-artifact-v1",
        "task_id": task.id,
        "task_version": task.version,
        "origin": manifest.source.classification,
        "prompt_path": task.prompt_path,
        "actor_asset_paths": task.actor_asset_paths,
        "files": [f.model_dump() for f in manifest.files if f.path in paths],
        "outputs": [o.model_dump() for o in task.outputs],
        "timeout_seconds": task.timeout_seconds,
        "environment": task.environment.model_dump(),
        "tools": [t.model_dump() for t in task.tools],
    }
