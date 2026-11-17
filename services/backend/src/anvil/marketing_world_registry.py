"""Operator candidates and API-only current private world source selection.

No qualification is created here. Real independent receipts must already exist;
neither source import, a paid job lease nor a JSON status grants qualification.
"""

import os
import secrets
from typing import Literal

from pydantic import Field, model_validator

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import Sha
from anvil.db import Jsonb, project_fence, uid
from anvil.marketing_world_definition import definition
from anvil.praxis_generic_contract import digest
from anvil.schemas import Strict

CONTROLS = frozenset(
    {
        "membership_and_revocation",
        "role_isolation",
        "future_evidence_isolation",
        "paired_branch_selection",
        "conditional_approval_activation",
        "request_version_scope",
        "financial_conservation",
        "simulated_task3",
        "source_rights_projection",
        "actual_native_runtime",
        "no_model_requests",
    }
)


class Control(Strict):
    status: Literal["passed"]
    evidence_sha256: Sha


class Qualification(Strict):
    schema_version: Literal["anvil.marketing-private-world-qualification.v1"]
    origin: Literal["independent_qa"]
    scope: Literal["fictional_controlled_sources_and_simulated_world_only"]
    definition_sha256: Sha
    source_sha256: Sha
    runtime_sha256: Sha
    runtime_image_sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    dataset_qualification_sha256: Sha
    rights_receipt_sha256: Sha
    controls: dict[str, Control]

    def expected_controls(self):
        return CONTROLS

    @model_validator(mode="after")
    def all_controls(self):
        if set(self.controls) != self.expected_controls():
            raise ValueError("Exact independently exercised world qualification controls required")
        return self


class OpeningQualification(Qualification):
    schema_version: Literal["anvil.marketing-private-world-qualification.v2"]
    operator_program_id: Literal["marketing-opening0-and-twelve-reviews-v1"]
    operator_program_sha256: Sha

    def expected_controls(self):
        return CONTROLS | {"opening_plan_before_feedback", "opening_twelve_review_reconstruction"}


class PopulationQualification(OpeningQualification):
    schema_version: Literal["anvil.marketing-private-world-qualification.v3"]

    def expected_controls(self):
        return super().expected_controls() | {"complete_original_source_population"}


def decode_qualification(value):
    model = {"anvil.marketing-private-world-qualification.v3": PopulationQualification,
             "anvil.marketing-private-world-qualification.v2": OpeningQualification}.get(value.get("schema_version"), Qualification)
    return model.model_validate(value)


def new_candidate(value, dataset):
    """New private operator source: generate blinding once, never from a model.

    This grants no persistence/qualification/run authority. Restore/verification
    uses candidate() on the frozen body; it must never regenerate the seed.
    """
    bounded_json(value, 16777216, max_nodes=200000)
    if type(value) is not dict or "branch_seed" in value:
        raise ValueError("New source requires host-generated private blinding, not caller seed")
    return candidate(value | {"branch_seed": secrets.token_hex(32)}, dataset)


def candidate(value, dataset):
    """Prepare normalized operator bytes; never import arbitrary actor paths."""
    from anvil.praxis_template_registry import source_hash

    world = definition(value)
    member = next(
        (item for item in dataset["manifest"]["cases"] if item["id"] == world.case_id), None
    )
    if (
        member is None
        or member["snapshot_sha256"] != world.case_snapshot_sha256
        or world.fixture_manifest_sha256 != dataset["fixture_manifest_sha256"]
        or world.source_manifest_sha256 != dataset["fixture_manifest_sha256"]
        or world.source_hashes != dataset["fixture_manifest"]["source_hashes"]
    ):
        raise ValueError("Actual immutable dataset case and complete source inventory required")
    body = world.model_dump(mode="json")
    return {
        "definition": body,
        "definition_sha256": digest(body),
        "source_sha256": source_hash(),
        "dataset_id": str(dataset["id"]),
    }


def persist(connection, project, prepared):
    """Existing privileged operator only; no app/worker/table writes granted."""
    if not connection.execute(
        "SELECT has_table_privilege(current_user,'campaign_private.world_sources','INSERT') AS allowed"
    ).fetchone()["allowed"]:
        raise PermissionError("Existing privileged world source operator required")
    from anvil.praxis_template_registry import source_hash

    world = definition(prepared["definition"])
    if (
        digest(prepared["definition"]) != prepared["definition_sha256"]
        or prepared["source_sha256"] != source_hash()
    ):
        raise ValueError("Current immutable world candidate required")
    project_fence(connection, project)
    dataset = connection.execute(
        "SELECT * FROM anvil.campaign_dataset_versions WHERE project_id=%s AND id=%s",
        (project, prepared["dataset_id"]),
    ).fetchone()
    if dataset is None or candidate(prepared["definition"], dataset) != prepared:
        raise ValueError("Immutable project dataset/source candidate required")
    old = connection.execute(
        "SELECT id FROM campaign_private.world_sources WHERE project_id=%s AND dataset_id=%s AND definition_sha256=%s AND source_sha256=%s",
        (project, prepared["dataset_id"], prepared["definition_sha256"], prepared["source_sha256"]),
    ).fetchone()
    if old:
        return {"source_id": str(old["id"]), "qualification": "not_granted"}
    used = connection.execute(
        "SELECT coalesce(sum(octet_length(definition::text)),0) AS bytes FROM campaign_private.world_sources WHERE project_id=%s",
        (project,),
    ).fetchone()["bytes"]
    size = connection.execute(
        "SELECT octet_length(%s::jsonb::text) AS bytes", (Jsonb(prepared["definition"]),)
    ).fetchone()["bytes"]
    if size > 16777216 or used + size > 536870912:
        raise ValueError("Private world source project quota exhausted")
    identifier = uid()
    connection.execute(
        "INSERT INTO campaign_private.world_sources(id,project_id,dataset_id,case_id,case_snapshot_sha256,execution_sha256,source_sha256,definition,definition_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            prepared["dataset_id"],
            world.case_id,
            world.case_snapshot_sha256,
            world.execution_sha256,
            prepared["source_sha256"],
            Jsonb(prepared["definition"]),
            prepared["definition_sha256"],
        ),
    )
    return {"source_id": str(identifier), "qualification": "not_granted"}


def load(connection, claim, plan):
    """Called by private API only, after full marketing_paid_execution.admitted.

    SQL rejects unleased access and hides sources from scheduler/worker roles.
    Actual time expiry/revocation is checked on every read, not cached at attach.
    """
    from anvil.golden_kyc_anvil import source_hash as runtime_hash
    from anvil.praxis_template_registry import source_hash

    rows = connection.execute(
        "SELECT marketing_runtime.private_world_candidates(%s,%s,%s) AS value",
        (claim.job_id, claim.lease_token, claim.plan_id),
    ).fetchall()
    if len(rows) > 100:
        raise RuntimeError("marketing_world_source_population_ambiguous")
    native = plan["config"]["marketing_native_binding"]
    accepted = {}
    for row in rows:
        source, qualification = row["value"]["source"], row["value"]["qualification"]
        body, receipt = source["definition"], qualification["receipt"]
        world = definition(body)
        evidence = decode_qualification(receipt)
        expected = {"anvil.marketing-private-world-definition.v6": PopulationQualification,
                    "anvil.marketing-private-world-definition.v5": OpeningQualification}.get(world.schema_version, Qualification)
        if (
            type(evidence) is not expected
            or (isinstance(evidence, OpeningQualification) and evidence.operator_program_sha256 != world.operator_program_sha256)
            or digest(body) != source["definition_sha256"]
            or digest(receipt) != qualification["receipt_sha256"]
            or evidence.definition_sha256 != source["definition_sha256"]
            or source["source_sha256"] != source_hash()
            or evidence.source_sha256 != source_hash()
            or evidence.runtime_sha256 != runtime_hash()
            or evidence.runtime_sha256 != native["runtime_sha256"]
            or evidence.runtime_image_sha256 != os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST")
            or evidence.dataset_qualification_sha256
            != native["dataset_qualification"]["receipt_sha256"]
            or evidence.rights_receipt_sha256 != world.rights_receipt_sha256
            or world.case_id != native["case_assignment"]["case_id"]
            or world.case_snapshot_sha256 != native["case_assignment"]["snapshot_sha256"]
            or world.execution_sha256 != native["execution_sha256"]
            or world.fixture_manifest_sha256 != native["fixture_manifest_sha256"]
            or world.campaign_context.task_id != native["task_id"]
            or world.campaign_context.revision_id != native["revision_id"]
        ):
            continue
        accepted[str(source["id"])] = (world, source, qualification)
    if len(accepted) != 1:
        raise RuntimeError("marketing_current_independently_qualified_world_required")
    return next(iter(accepted.values()))


def require_sdk(connection, claim, plan):
    """Current serving-image/source check before the final SQL SDK claim.

    This metadata projection never loads fixtures into the candidate prompt.
    SQL also holds the source revocation fence in the final once-only claim.
    """
    from anvil.golden_kyc_anvil import source_hash as runtime_hash
    from anvil.praxis_template_registry import source_hash

    if (
        claim is None
        or str(claim.plan_id) != str(plan["id"])
        or str(claim.actor_id) != str(plan["created_by"])
    ):
        raise RuntimeError("marketing_exact_current_worker_broker_claim_required")
    from anvil.marketing_capture_store import require_sdk_capture_budget

    require_sdk_capture_budget(connection, claim)
    from anvil.marketing_capture_evidence_store import require_reserved_manifest

    capture_budget = require_reserved_manifest(connection, claim)
    row = connection.execute(
        "SELECT marketing_runtime.private_world_runtime_receipt(%s,%s,%s) AS value",
        (claim.job_id, claim.lease_token, claim.plan_id),
    ).fetchone()["value"]
    if not row:
        raise RuntimeError("marketing_current_world_sdk_qualification_required")
    source, qualification = row["source"], row["qualification"]
    receipt = qualification["receipt"]
    evidence = decode_qualification(receipt)
    native = plan["config"]["marketing_native_binding"]
    if (
        type(evidence) is not PopulationQualification
        or source.get("definition_schema") != "anvil.marketing-private-world-definition.v6"
        or source.get("operator_program_sha256") != evidence.operator_program_sha256
        or source.get("operator_program_id") != evidence.operator_program_id
        or digest(receipt) != qualification["receipt_sha256"]
        or evidence.definition_sha256 != source["definition_sha256"]
        or evidence.source_sha256 != source["source_sha256"]
        or evidence.source_sha256 != source_hash()
        or evidence.runtime_sha256 != runtime_hash()
        or evidence.runtime_sha256 != native["runtime_sha256"]
        or evidence.runtime_image_sha256 != os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST")
        or evidence.rights_receipt_sha256 != source["rights_receipt_sha256"]
        or evidence.dataset_qualification_sha256
        != native["dataset_qualification"]["receipt_sha256"]
        or source["case_id"] != native["case_assignment"]["case_id"]
        or source["case_snapshot_sha256"] != native["case_assignment"]["snapshot_sha256"]
        or source["execution_sha256"] != native["execution_sha256"]
    ):
        raise RuntimeError("marketing_world_sdk_source_or_serving_image_changed")
    return capture_budget
