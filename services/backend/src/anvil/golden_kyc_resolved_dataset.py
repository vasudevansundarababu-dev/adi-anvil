"""Private immutable input-binding candidate; no export rewriting or admission.

Authoring supplies reusable tasks. Anvil supplies the exact selected original
dataset and authentic review/qualification projections. This module derives all
membership/counts; constructing these types never authenticates those sources.
"""

from dataclasses import dataclass, field
from uuid import UUID

from pydantic import TypeAdapter

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import Sha
from anvil.golden_kyc_type_index import derive
from anvil.golden_kyc_v7_candidate import DecodedCandidate, DecodedTask
from anvil.praxis_case_dataset import CaseDataset, CaseDatasetRef
from anvil.praxis_generic_contract import canonical, digest
from anvil.project_input_contract import MAX_BYTES


@dataclass(frozen=True, slots=True)
class BindingScope:
    project_id: UUID
    project_binding_id: UUID
    project_binding_sha256: str
    runtime_source_sha256: str
    runtime_image_sha256: str
    environment_binding_sha256: str
    evaluator_bindings_sha256: str


@dataclass(frozen=True, slots=True)
class ReviewedTask:
    # Actual immutable receipt digest, never a hash of an opaque URI. The typed
    # source-resolution kind is provenance only, never Anvil human approval.
    task: DecodedTask
    review_receipt_sha256: str
    provenance_kind: str | None = None


@dataclass(frozen=True, slots=True)
class BoundRow:
    application_id: str
    application_sha256: str
    governing_state: str
    product: str | None
    task_id: str | None
    revision_id: str | None
    status: str


@dataclass(frozen=True, slots=True)
class ResolvedInput:
    canonical_body: bytes = field(repr=False)
    sha256: str
    rows: tuple[BoundRow, ...]
    status: str = "candidate_input_binding_not_qualified"
    run_authority: str = "not_granted"


def _sha(value):
    TypeAdapter(Sha).validate_python(value, strict=True)
    return value


def resolve_candidate(scope, source, reviewed_tasks, dataset, reference, snapshots):
    """Freeze a new context for exact original membership, never silently sample.

    Every row is assigned by verified snapshot.product or explicitly blocked.
    Example state, requested_product, titles and coverage quotas have no role.
    Policy/domain/runtime and current-source/review qualification remain separate.
    No operational persistence or API registration occurs in this pure function.
    """
    if (type(scope) is not BindingScope or type(scope.project_id) is not UUID
            or type(scope.project_binding_id) is not UUID or type(source) is not DecodedCandidate
            or type(reviewed_tasks) is not tuple or not 0 < len(reviewed_tasks) <= 200
            or source.status != "unregistered_candidate_not_admitted" or source.run_authority != "not_granted"):
        raise ValueError("Exact original source, review and Anvil binding projections required")
    scope_value = {"project_id": str(scope.project_id), "project_binding_id": str(scope.project_binding_id)}
    for name in ("project_binding_sha256", "runtime_source_sha256", "runtime_image_sha256",
                 "environment_binding_sha256", "evaluator_bindings_sha256"):
        scope_value[name] = _sha(getattr(scope, name))
    _sha(source.package_sha256)
    _sha(source.manifest_sha256)
    if (type(source.anvil_requirements) is not tuple or len(source.anvil_requirements) > 1000
            or any(type(item) is not tuple or len(item) != 2
                   or any(type(value) is not str or not 0 < len(value) <= 200 for value in item)
                   for item in source.anvil_requirements)):
        raise ValueError("Bounded separate Anvil provisioning requirements required")
    if (type(source.tasks) is not tuple or not 0 < len(source.tasks) <= 200
            or any(type(task) is not DecodedTask for task in source.tasks)):
        raise ValueError("Exact complete source task membership required")
    original = {(task.task_id, task.revision_id): task for task in source.tasks}
    if (len(original) != len(source.tasks) or len({task.task_id for task in source.tasks}) != len(source.tasks)
            or any(task.product not in {"individual", "adult_joint", "teen_joint", "custodial"} for task in source.tasks)):
        raise ValueError("Duplicate source task revision")
    tasks, routes, seen = [], {}, set()
    for reviewed in reviewed_tasks:
        if type(reviewed) is not ReviewedTask or type(reviewed.task) is not DecodedTask:
            raise ValueError("Original source and genuine review-registry projection required")
        task = reviewed.task
        key = (task.task_id, task.revision_id)
        if key in seen or key not in original or original[key] != task:
            raise ValueError("Review projection must bind an exact source task revision")
        seen.add(key)
        for value in (task.template_sha256, task.template_qualification_receipt_sha256,
                      task.authored_sha256, task.actor_sha256, task.private_reference_sha256,
                      reviewed.review_receipt_sha256):
            _sha(value)
        if reviewed.provenance_kind not in (None, "source_resolution_receipt"):
            raise ValueError("Exact typed source review provenance required")
        routes.setdefault(task.product, []).append(task)
        tasks.append({"task_id": task.task_id, "revision_id": task.revision_id,
                      "template": {"id": task.template_id, "version": task.template_version,
                                   "sha256": task.template_sha256},
                      "template_qualification_receipt_sha256": task.template_qualification_receipt_sha256,
                      "authored_sha256": task.authored_sha256, "actor_sha256": task.actor_sha256,
                      "private_reference_sha256": task.private_reference_sha256,
                      "source_review_receipt_ref": task.review_receipt_ref,
                      "review_receipt_sha256": reviewed.review_receipt_sha256,
                      **({"review_provenance_kind": "source_resolution_receipt",
                          "anvil_human_review_approved": False}
                         if reviewed.provenance_kind == "source_resolution_receipt" else {}),
                      "case_selector": {"field": "product", "value": task.product}})
    if seen != set(original):
        # Missing Anvil-authenticated review records cannot become approved or
        # disappear from an input context. They are provisioning/review blockers.
        raise ValueError("Complete genuine source-review binding required")
    if type(dataset) is not CaseDataset or type(reference) is not CaseDatasetRef:
        raise ValueError("Exact Anvil input dataset and reference required")
    # Freeze original membership/reference before advancing the source iterator.
    # Generator-side mutation must not change the context after hash checks.
    dataset_value = dataset.model_dump(mode="json")
    bounded_json(dataset_value, MAX_BYTES, max_nodes=100000, max_depth=8)
    dataset = CaseDataset.model_validate_json(canonical(dataset_value))
    reference = CaseDatasetRef.model_validate_json(canonical(reference.model_dump(mode="json")))
    index = derive(dataset, reference, snapshots)
    rows, counts, blocked = [], {task.task_id: 0 for task in source.tasks}, {}
    for row in index.rows:
        candidates = routes.get(row.product, ())
        status = row.blocked_reason
        task = None
        if status is None:
            if len(candidates) == 1:
                task, status = candidates[0], "assigned_pending_policy_and_runtime_qualification"
                counts[task.task_id] += 1
            else:
                status = "missing_workflow" if not candidates else "ambiguous_workflow"
        if task is None:
            blocked[status] = blocked.get(status, 0) + 1
        rows.append(BoundRow(row.application_id, row.application_sha256, row.governing_state, row.product,
                             task.task_id if task else None, task.revision_id if task else None, status))
    if len(rows) != dataset.case_count or sum(counts.values()) + sum(blocked.values()) != dataset.case_count:
        raise ValueError("Complete original dataset denominator conservation required")
    body = {"schema_version": "anvil.private-kyc-resolved-input.v1", "scope": scope_value,
            "source_package_sha256": source.package_sha256, "source_manifest_sha256": source.manifest_sha256,
            "source_anvil_requirements": [{"code": code, "task_id": task, "owner": "anvil"}
                                          for code, task in source.anvil_requirements],
            "case_dataset": reference.model_dump(mode="json"), "derived_type_index_sha256": index.sha256,
            "tasks": sorted(tasks, key=lambda task: (task["task_id"], task["revision_id"])),
            "input_count": dataset.case_count, "task_application_counts": counts, "blocked_counts": blocked,
            "rows": [{"application_id": row.application_id, "application_sha256": row.application_sha256,
                      "governing_state": row.governing_state, "product": row.product,
                      "task_id": row.task_id, "revision_id": row.revision_id, "status": row.status} for row in rows],
            "runtime_qualified": False, "policy_qualified": False, "run_authority": "not_granted"}
    bounded_json(body, MAX_BYTES, max_nodes=150512, max_depth=12)
    return ResolvedInput(canonical(body), digest(body), tuple(rows))
