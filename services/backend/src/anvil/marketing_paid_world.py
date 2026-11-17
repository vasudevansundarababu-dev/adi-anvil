"""Trusted coordinator facade; private fixture/controller state stays on API.

Construction validates public binding bytes, not runtime admission. The fixed
Harbor boundary must establish native/source/asset authority before attach/use.
No provider client, private branch, controller credential or world factory can be
passed here. Server-side world custody must independently verify every request.
"""

import math
import os
import re
from time import monotonic
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from anvil.campaign_semantic_contract import Claim, bounded_json
from anvil.dataset_export_contract import Sha, json_object
from anvil.db import digest
from anvil.praxis_generic_contract import canonical
from anvil.praxis_generic_contract import digest as wire_digest
from anvil.praxis_marketing_contract import MarketingExecution
from anvil.schemas import Strict

Reference = Annotated[str, Field(min_length=1, max_length=2000)]


class CampaignContext(Strict):
    case_id: str = Field(min_length=1, max_length=200)
    locale: Literal["en-US"]
    campaign_ref: Reference
    task_id: str = Field(min_length=1, max_length=200)
    revision_id: str = Field(min_length=1, max_length=200)
    dataset_id: str = Field(min_length=1, max_length=200)
    dataset_version: str = Field(min_length=1, max_length=200)
    dataset_sha256: Sha
    public_source_refs: list[Reference] = Field(max_length=200)
    currency: Literal["USD"]
    business_budget_minor: int = Field(strict=True, ge=0, le=20000000)
    origin: Literal["fictional_campaign_environment"]


class Attachment(Strict):
    schema_version: Literal["anvil.marketing-world-attachment.v1"]
    project_id: UUID
    actor_id: UUID
    job_id: UUID
    plan_id: UUID
    world_binding_id: UUID
    world_binding_sha256: Sha
    episode_id: UUID
    generation: int = Field(strict=True, ge=0)
    case_id: str = Field(min_length=1, max_length=200)
    case_snapshot_sha256: Sha
    execution_sha256: Sha
    native_binding_sha256: Sha
    source_manifest_sha256: Sha
    dataset_qualification_sha256: Sha
    rights_receipt_sha256: Sha
    campaign_context: CampaignContext


class Release(Strict):
    schema_version: Literal["anvil.marketing-world-release.v1"]
    world_binding_id: UUID
    world_binding_sha256: Sha
    episode_id: UUID
    generation: int = Field(strict=True, ge=0)
    case_id: str = Field(min_length=1, max_length=200)
    case_snapshot_sha256: Sha
    week: int = Field(strict=True, ge=1, le=12)
    released_at: AwareDatetime
    window_ref: Reference
    evidence_refs: list[Reference] = Field(max_length=500)
    receipt_id: UUID
    receipt_sha256: Sha

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("Distinct actual released evidence references required")
        return self


class BaselineDescriptors(Strict):
    schema_version: Literal["anvil.marketing-baseline-descriptors.v1"]
    world_binding_id: UUID
    world_binding_sha256: Sha
    episode_id: UUID
    generation: int = Field(strict=True, ge=0)
    case_id: str = Field(min_length=1, max_length=200)
    week: int = Field(strict=True, ge=1, le=12)
    source_contract_sha256: Sha
    provenance: Literal["PREEXISTING_STANDALONE_DESCRIPTOR_FIXTURES"]
    deliveries: list[dict] = Field(min_length=1, max_length=6)
    issues: list[dict] = Field(max_length=100)
    new_task3_effect: Literal[False]
    actual_media_generated: Literal[False]
    actual_media_inspected: Literal[False]
    campaign_authority_issued: Literal[False]
    spend_authority_issued: Literal[False]

    @field_validator("new_task3_effect", "actual_media_generated", "actual_media_inspected",
                     "campaign_authority_issued", "spend_authority_issued", mode="before")
    @classmethod
    def no_authority(cls, value):
        if value is not False:
            raise ValueError("Baseline descriptors grant no new effect or authority")
        return value

    @model_validator(mode="after")
    def actual_fixture_scope(self):
        bounded_json(self.model_dump(mode="json"), 16384, max_nodes=4000)
        if len({r.get("creative_id") for r in self.deliveries}) != len(self.deliveries):
            raise ValueError("Distinct existing baseline creative versions required")
        for row in self.deliveries:
            if (row.get("locale") != "en-US" or row.get("market") != "US"
                    or row.get("asset_bytes_exist") is not False
                    or row.get("asset_content_sha256") is not None
                    or row.get("human_approval") is not False
                    or row.get("provenance") != "TASK3_STANDALONE_DESCRIPTOR_FIXTURE_NO_MEDIA"
                    or type(row.get("creative_version")) is not int
                    or row["creative_version"] < 1
                    or type(row.get("descriptor_sha256")) is not str
                    or not re.fullmatch(r"[0-9a-f]{64}", row["descriptor_sha256"])):
                raise ValueError("Baseline descriptors cannot represent new/actual media or authority")
        return self


class ServiceRelease(Release):
    schema_version: Literal["anvil.marketing-world-release.v2"]
    baseline_delivery_manifest: BaselineDescriptors | None

    @model_validator(mode="after")
    def same_baseline(self):
        if self.baseline_delivery_manifest is not None and any(
            getattr(self.baseline_delivery_manifest, key) != getattr(self, key)
            for key in ("world_binding_id", "world_binding_sha256", "episode_id", "generation", "case_id", "week")
        ):
            raise ValueError("Baseline descriptors belong to another actual released window")
        return self


class OpeningBaselineDescriptors(BaselineDescriptors):
    schema_version: Literal["anvil.marketing-opening-baseline-descriptors.v1"]
    week: int = Field(strict=True, ge=0, le=0)


class OpeningRelease(ServiceRelease):
    schema_version: Literal["anvil.marketing-world-opening-release.v1"]
    week: int = Field(strict=True, ge=0, le=0)
    phase: Literal["opening"]
    operator_program_id: Literal["marketing-opening0-and-twelve-reviews-v1"]
    baseline_delivery_manifest: OpeningBaselineDescriptors | None


def released(value):
    if type(value) is dict and value.get("schema_version") == "anvil.marketing-world-opening-release.v1":
        return OpeningRelease.model_validate(value)
    if type(value) is dict and value.get("schema_version") == "anvil.marketing-world-release.v2":
        return ServiceRelease.model_validate(value)
    return Release.model_validate(value)


class WorldCall(Claim):
    plan_id: UUID
    operation: Literal[
        "attach", "opening", "release", "effect", "role_attach", "role_tool", "fence", "drain", "quiescence"
    ]
    value: dict

    @model_validator(mode="after")
    def exact_operation(self):
        bounded_json(self.value, 65536)
        scope = {"world_binding_id", "world_binding_sha256", "episode_id", "generation"}
        fields = {
            "attach": set(),
            "opening": scope,
            "release": scope | {"week"},
            "effect": scope | {"week", "visit", "node_id", "inputs"},
            "role_attach": scope | {"role"},
            "role_tool": scope | {"role", "request_id", "operation", "arguments"},
            "fence": scope,
            "drain": scope,
            "quiescence": scope,
        }[self.operation]
        if set(self.value) != fields:
            raise ValueError("Exact fixed world operation fields required")
        if fields:
            UUID(self.value["world_binding_id"])
            UUID(self.value["episode_id"])
            if type(self.value["generation"]) is not int or self.value["generation"] < 0:
                raise ValueError("Exact world generation required")
            if self.operation in {"release", "effect"} and (
                type(self.value["week"]) is not int
                or not (0 if self.operation == "effect" else 1) <= self.value["week"] <= 12
            ):
                raise ValueError("Exact world window required")
            sha = self.value["world_binding_sha256"]
            if type(sha) is not str or not re.fullmatch(r"[a-f0-9]{64}", sha):
                raise ValueError("Exact world binding hash required")
            if self.operation == "effect" and (
                type(self.value["visit"]) is not int
                or not 1 <= self.value["visit"] <= 400
                or type(self.value["inputs"]) is not dict
            ):
                raise ValueError("Exact bounded world effect inputs required")
            if self.operation == "effect" and (
                type(self.value["node_id"]) is not str or not 1 <= len(self.value["node_id"]) <= 200
            ):
                raise ValueError("Exact bounded world node required")
            if self.operation in {"role_attach", "role_tool"}:
                from anvil.marketing_task2_contract import WIRE_ROLES

                if type(self.value["role"]) is not str or self.value["role"] not in WIRE_ROLES:
                    raise ValueError("Exact host-bound world role required")
            if self.operation == "role_tool" and (
                type(self.value["request_id"]) is not str
                or not re.fullmatch(r"[a-f0-9]{32}", self.value["request_id"])
                or type(self.value["operation"]) is not str
                or not 1 <= len(self.value["operation"]) <= 60
                or type(self.value["arguments"]) is not dict
            ):
                raise ValueError("Actual correlated role tool request required")
        return self


class EffectReceipt(Strict):
    input_sha256: Sha
    artifact_sha256: Sha
    post_state_sha256: Sha
    world_binding_sha256: Sha
    world_effect_id: UUID
    world_receipt_sha256: Sha
    episode_id: UUID
    generation: int = Field(strict=True, ge=0)
    node_id: str = Field(min_length=1, max_length=200)
    week: int = Field(strict=True, ge=1, le=12)
    visit: int = Field(strict=True, ge=1, le=400)
    origin: Literal["persisted_environment_effect"]
    simulated_environment: Literal[True]

    @field_validator("simulated_environment", mode="before")
    @classmethod
    def simulation_only(cls, value):
        if value is not True:
            raise ValueError("World fixtures never represent actual human approval")
        return value


class Effect(Strict):
    artifact: dict
    receipt: EffectReceipt
    port: Literal["responded", "timeout"] | None = None

    @model_validator(mode="after")
    def bounded(self):
        bounded_json(self.artifact, 49152)
        if wire_digest(self.artifact) != self.receipt.artifact_sha256:
            raise ValueError("Exact actual world artifact bytes required")
        return self


class OpeningEffectReceipt(EffectReceipt):
    week: int = Field(strict=True, ge=0, le=0)


class OpeningEffect(Effect):
    receipt: OpeningEffectReceipt


def effect_result(value):
    model = OpeningEffect if type(value) is dict and value.get("receipt", {}).get("week") == 0 else Effect
    return model.model_validate(value)


def _rpc(job, plan_id, operation, value, remaining, absolute_deadline):
    from anvil import pilot_environment
    from anvil.marketing_native_worker_flags import (
        trusted_worker_live_enabled as harbor_live_enabled,
    )

    stopping = operation in {"fence", "drain", "quiescence"}
    if (
        pilot_environment.current() != "qa"
        or os.environ.get("ANVIL_WORKER_BROKER_ROLE") != "worker"
        or os.environ.get("ANVIL_WORKER_BROKER_ENABLED") != "true"
        or (not stopping and not harbor_live_enabled())
        or os.environ.get(
            "ANVIL_MARKETING_WORLD_STOP_ENABLED" if stopping else "ANVIL_MARKETING_WORLD_ENABLED"
        )
        != "true"
        or os.environ.get("ANVIL_WORKER_BROKER_URL")
        != "http://api:8200/internal/v1/worker-dispatch"
    ):
        raise RuntimeError("marketing_private_world_transport_not_enabled")
    if (
        operation
        not in {
            "attach",
            "opening",
            "release",
            "effect",
            "role_attach",
            "role_tool",
            "fence",
            "drain",
            "quiescence",
        }
        or type(remaining) is not int
        or not 1 <= remaining <= 600
    ):
        raise ValueError("Exact bounded world operation required")
    rpc_deadline = min(absolute_deadline, monotonic() + remaining)
    payload = WorldCall(
        project_id=job["project_id"],
        actor_id=job["actor_id"],
        job_id=job["id"],
        lease_token=job["lease_token"],
        plan_id=plan_id,
        operation=operation,
        value=value,
    ).model_dump(mode="json")
    bounded_json(payload, 98304, max_nodes=10000)
    try:
        from anvil.marketing_paid_world_transport import execute

        raw = execute(canonical(payload), absolute_deadline=rpc_deadline, request_seconds=remaining)
        result = json_object(raw)
        bounded_json(result, 131072, max_nodes=10000)
        if monotonic() >= rpc_deadline:
            raise TimeoutError("marketing_world_response_processing_deadline")
        return result
    except Exception:
        raise RuntimeError("marketing_world_outcome_unknown_no_retry") from None


class QualifiedWorld:
    """Exact public facade, not an actor-supplied implementation of world rules."""

    @classmethod
    def attach(cls, job, prepared, *, absolute_deadline, phase_deadline=None):
        cls._remaining(absolute_deadline)
        rpc_deadline = absolute_deadline
        if phase_deadline is not None:
            if (type(phase_deadline) not in (int, float)
                    or not math.isfinite(phase_deadline)
                    or phase_deadline > absolute_deadline):
                raise ValueError("Attach phase must fit original world deadline")
            rpc_deadline = phase_deadline
        remaining = cls._remaining(rpc_deadline)
        value = _rpc(
            job,
            job["plan_id"],
            "attach",
            {},
            min(remaining, prepared["request_timeout_seconds"]),
            rpc_deadline,
        )
        return cls(job, prepared, value, absolute_deadline=absolute_deadline)

    def __init__(self, job, prepared, attachment, *, absolute_deadline):
        self._remaining(absolute_deadline)
        bounded_json(attachment, 32768)
        bound = Attachment.model_validate(attachment)
        if prepared.get("world_attachment_sha256") != wire_digest(attachment) or prepared.get(
            "world_attachment"
        ) != bound.model_dump(mode="json"):
            raise ValueError("Exact server-owned prepared world attachment required")
        native = prepared["native_binding"]
        assignment = native["case_assignment"]
        dataset = native["case_context"]["caseDataset"]
        if (
            prepared.get("mode") != "marketing-native"
            or any(
                str(getattr(bound, key)) != str(job[field])
                for key, field in (
                    ("project_id", "project_id"),
                    ("actor_id", "actor_id"),
                    ("job_id", "id"),
                    ("plan_id", "plan_id"),
                )
            )
            or bound.case_id != assignment["case_id"]
            or bound.case_snapshot_sha256 != assignment["snapshot_sha256"]
            or bound.execution_sha256 != native["execution_sha256"]
            or bound.execution_sha256 != wire_digest(prepared["execution"])
            or bound.native_binding_sha256 != wire_digest(native)
            or bound.source_manifest_sha256 != native["fixture_manifest_sha256"]
            or bound.dataset_qualification_sha256
            != native["dataset_qualification"]["receipt_sha256"]
            or bound.campaign_context.case_id != bound.case_id
            or bound.campaign_context.task_id != native["task_id"]
            or bound.campaign_context.revision_id != native["revision_id"]
            or any(
                getattr(bound.campaign_context, field) != dataset[key]
                for field, key in (
                    ("dataset_id", "id"),
                    ("dataset_version", "version"),
                    ("dataset_sha256", "sha256"),
                )
            )
        ):
            raise ValueError("Exact server-owned campaign world attachment required")
        self._job, self._deadline = dict(job), absolute_deadline
        self._bound = bound
        self._execution = MarketingExecution.model_validate(prepared["execution"]).model_dump()
        self._request_timeout = prepared["request_timeout_seconds"]
        self.case_id, self.episode_id, self.generation = (
            bound.case_id,
            str(bound.episode_id),
            bound.generation,
        )

    @staticmethod
    def _remaining(deadline):
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError("Trusted outer absolute deadline required")
        delta = deadline - monotonic()
        remaining = int(delta)
        if remaining < 1 or delta > 600:
            raise TimeoutError("marketing_world_aggregate_deadline_expired_or_extended")
        return remaining

    @property
    def campaign_context(self):
        return self._bound.campaign_context.model_dump(mode="json")

    @property
    def rights_ref(self):
        """Opaque receipt identity only; the server/operator must verify its body."""
        return "anvil-rights-receipt:sha256:" + self._bound.rights_receipt_sha256

    @property
    def binding_projection(self):
        """Immutable public metadata for independent outer-record comparison."""
        return canonical(
            self._bound.model_dump(mode="json", exclude={"campaign_context"})
            | {"rights_ref": self.rights_ref}
        )

    def _call(self, operation, value, *, request_seconds=None, phase_deadline=None):
        if request_seconds is not None and (
            type(request_seconds) is not int or not 1 <= request_seconds <= 60
        ):
            raise ValueError("Bounded fixed role-tool request deadline required")
        deadline = self._deadline
        if phase_deadline is not None:
            if (
                operation not in {"fence", "drain", "quiescence", "release", "effect", "role_attach", "role_tool"}
                or type(phase_deadline) not in (int, float)
                or not math.isfinite(phase_deadline)
                or phase_deadline > self._deadline
            ):
                raise ValueError("World phase deadline must fit original world deadline")
            deadline = phase_deadline
        scope = {
            "world_binding_id": str(self._bound.world_binding_id),
            "world_binding_sha256": self._bound.world_binding_sha256,
            "episode_id": self.episode_id,
            "generation": self.generation,
        }
        result = _rpc(
            self._job,
            self._job["plan_id"],
            operation,
            scope | value,
            min(self._remaining(deadline), self._request_timeout, request_seconds or 600),
            deadline,
        )
        self._remaining(deadline)
        return result

    def role_environment(self, role, *, phase_deadline=None):
        from anvil.marketing_world_role import WorldRoleEnvironment

        return WorldRoleEnvironment(self, role, phase_deadline=phase_deadline)

    def fence(self, *, phase_deadline=None):
        return self._stop_status("fence", phase_deadline=phase_deadline)

    def quiescence(self, *, phase_deadline=None):
        return self._stop_status("quiescence", phase_deadline=phase_deadline)

    def drain(self, *, phase_deadline=None):
        return self._stop_status("drain", phase_deadline=phase_deadline)

    def _stop_status(self, operation, *, phase_deadline=None):
        import hashlib

        from anvil.marketing_world_quiescence import Status

        options = {} if phase_deadline is None else {"phase_deadline": phase_deadline}
        value = Status.model_validate(self._call(operation, {}, **options))
        for name in (
            "project_id",
            "job_id",
            "plan_id",
            "world_binding_id",
            "world_binding_sha256",
            "episode_id",
            "generation",
            "execution_sha256",
        ):
            if getattr(value.fence, name) != getattr(self._bound, name):
                raise ValueError("Exact same actual world stop response scope required")
        if (
            value.fence.lease_sha256
            != hashlib.sha256(str(self._job["lease_token"]).encode()).hexdigest()
        ):
            raise ValueError("Exact original job lease stop receipt required")
        result = value.model_dump(mode="json")
        self._remaining(self._deadline if phase_deadline is None else phase_deadline)
        return result

    def opening(self, *, phase_deadline=None):
        from anvil.marketing_paid_reconstruction import release_artifact

        options = {} if phase_deadline is None else {"phase_deadline": phase_deadline}
        raw = self._call("opening", {}, **options)
        response = OpeningRelease.model_validate(raw)
        if any(getattr(response, key) != getattr(self._bound, key) for key in (
            "world_binding_id", "world_binding_sha256", "episode_id", "generation", "case_id", "case_snapshot_sha256"
        )) or wire_digest({key: value for key, value in raw.items() if key != "receipt_sha256"}) != response.receipt_sha256:
            raise ValueError("Exact original opening receipt scope and bytes required")
        self._remaining(self._deadline if phase_deadline is None else phase_deadline)
        return release_artifact(raw)

    def release(self, week, *, phase_deadline=None):
        if type(week) is not int or not 1 <= week <= 12:
            raise ValueError("Exact published campaign window required")
        options = {} if phase_deadline is None else {"phase_deadline": phase_deadline}
        response = released(self._call("release", {"week": week}, **options))
        if response.week != week or any(
            getattr(response, key) != getattr(self._bound, key)
            for key in (
                "world_binding_id",
                "world_binding_sha256",
                "episode_id",
                "generation",
                "case_id",
                "case_snapshot_sha256",
            )
        ):
            raise ValueError("World release belongs to another actual case/window/generation")
        result = {
            "week": week,
            "released_at": response.released_at.isoformat(),
            "window_ref": response.window_ref,
            "evidence_refs": response.evidence_refs,
            "world_receipt_ref": str(response.receipt_id) + ":" + response.receipt_sha256,
        }
        if isinstance(response, ServiceRelease):
            result["baseline_delivery_manifest"] = (
                response.baseline_delivery_manifest.model_dump(mode="json") if response.baseline_delivery_manifest is not None else None
            )
        self._remaining(self._deadline if phase_deadline is None else phase_deadline)
        return result

    def effect(self, node, inputs, week, visit, *, phase_deadline=None):
        expected = next(
            (
                item
                for item in self._execution["workflow_graph"]["nodes"]
                if item["id"] == node.get("id")
            ),
            None,
        )
        if (
            expected != node
            or node["type"] not in {"human_step", "external_system"}
            or type(week) is not int
            or not 0 <= week <= 12
            or type(visit) is not int
            or not 1 <= visit <= 400
        ):
            raise ValueError("Exact published non-agent world effect required")
        refs = node.get("sendsRefs", node.get("permittedEvidence", []))
        if type(inputs) is not dict or set(inputs) != set(refs):
            raise ValueError("Only exact current node inputs enter the world")
        bounded_json(inputs, 32768)
        options = {} if phase_deadline is None else {"phase_deadline": phase_deadline}
        raw = self._call(
            "effect", {"node_id": node["id"], "inputs": inputs, "week": week, "visit": visit},
            **options,
        )
        bounded_json(raw, 60000)
        response = effect_result(raw).model_dump(mode="json")
        receipt = response["receipt"]
        if (
            receipt.get("input_sha256") != digest(inputs)
            or receipt.get("world_binding_sha256") != self._bound.world_binding_sha256
            or receipt.get("episode_id") != self.episode_id
            or receipt.get("generation") != self.generation
            or receipt.get("node_id") != node["id"]
            or receipt.get("week") != week
            or receipt.get("visit") != visit
            or receipt.get("origin") != "persisted_environment_effect"
        ):
            raise ValueError("World effect receipt differs from the exact claimed graph effect")
        if (
            node["type"] == "human_step"
            and response.get("port") not in {"responded", "timeout"}
            or node["type"] == "external_system"
            and response.get("port") is not None
        ):
            raise ValueError("Only the actual simulated approval port is allowed")
        self._remaining(self._deadline if phase_deadline is None else phase_deadline)
        return response
