"""Unregistered application-type decoder for the proposed unchanged v1 export.

NOT called by the public validator or advertised contracts. Written agreement,
exact published template qualification and actual source review are prerequisites
to registration. Legacy Export/ReusableExport meanings remain unchanged.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Literal

from pydantic import Field

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import Model, Sha, pointer
from anvil.praxis_case_dataset import State
from anvil.praxis_generic_contract import (
    Export,
    TaskEntry,
    TemplateRef,
    TemplateSpec,
    digest,
    load,
    path,
)
from anvil.praxis_generic_export import actor_projection, read_archive, self_check


class ProductSelector(Model):
    field: Literal["product"]
    value: Literal["individual", "adult_joint", "teen_joint", "custodial"]


class ExampleCoverage(Model):
    example_governing_state: State


class CandidateTaskEntry(TaskEntry):
    case_selector: ProductSelector
    coverage: ExampleCoverage | None = None


class CandidateExport(Export):
    # Deliberately inherits praxis.authored-task-export.v1. This is not an alias
    # for v2, and nothing selects this decoder just from a user-supplied selector.
    tasks: list[CandidateTaskEntry] = Field(min_length=1, max_length=200)


@dataclass(frozen=True, slots=True)
class PublishedVariant:
    """Projection from a genuine registry, not proof by constructing this type.

    Exact template bytes must already have a current qualification explicitly
    accepting product applicability. Version number alone cannot confer it.
    """

    template: TemplateRef
    qualification_receipt_sha256: str
    template_canonical: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class DecodedTask:
    task_id: str
    revision_id: str
    template_id: str
    template_version: int
    template_sha256: str
    template_qualification_receipt_sha256: str
    product: str
    authored_sha256: str
    actor_sha256: str
    private_reference_sha256: str
    review_receipt_ref: str
    # Metadata only. Never used by the resolved dataset/policy planner.
    example_governing_state: str | None


@dataclass(frozen=True, slots=True)
class DecodedCandidate:
    package_sha256: str
    manifest_sha256: str
    tasks: tuple[DecodedTask, ...]
    status: str = "unregistered_candidate_not_admitted"
    run_authority: str = "not_granted"
    anvil_requirements: tuple[tuple[str, str], ...] = ()


class CandidateConformanceError(ValueError):
    """Safe aggregate authoring diagnostics; no input values in exception text."""

    def __init__(self, errors):
        super().__init__("Source fields violate the exact published template")
        self.errors = tuple(errors)


def _document(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 10 * 1048576:
        raise ValueError("Bounded original JSON document required")
    value = load(raw)
    bounded_json(value, 10 * 1048576, max_nodes=100000, max_depth=24)
    return value


def decode_candidate(raw, variants):
    """Pure bounded source consistency, not API acceptance or task approval.

    variants must be supplied from authenticated current qualification records;
    no variant/template/qualification is read from the ZIP as authority. Source
    review receipts remain opaque provenance and need separate authentication.
    """
    if type(raw) is not bytes or type(variants) is not tuple or not 0 < len(variants) <= 200:
        raise ValueError("Bounded original archive and exact registry projections required")
    registry = {}
    for variant in variants:
        if type(variant) is not PublishedVariant or type(variant.template_canonical) is not bytes:
            raise ValueError("Original published application-type template projection required")
        from pydantic import TypeAdapter

        TypeAdapter(Sha).validate_python(variant.qualification_receipt_sha256, strict=True)
        spec = _document(variant.template_canonical)
        ref = TemplateRef.model_validate(variant.template.model_dump())
        key = (ref.id, ref.version, ref.sha256)
        if (key in registry or ref.version < 7 or digest(spec) != ref.sha256
                or spec.get("template_id") != ref.id or spec.get("version") != ref.version):
            raise ValueError("Exact unique published template version/hash required")
        authoring = spec.get("authoring")
        profile = authoring.get("profile") if type(authoring) is dict else None
        if type(profile) is not dict:
            raise ValueError("Original published form required")
        template = authoring.get("template")
        selector = template.get("caseSelector") if type(template) is dict else None
        products = ["individual", "adult_joint", "teen_joint", "custodial"]
        if (type(selector) is not dict or selector.get("field") != "product"
                or selector.get("source") != "S1.applicationType" or type(selector.get("values")) is not list
                or any(type(value) is not str for value in selector["values"])
                or len(selector["values"]) != 4 or set(selector["values"]) != set(products)):
            raise ValueError("Exact published application-type selector required")
        try:
            spec_model = TemplateSpec.model_validate(spec)
        except (ValueError, TypeError):
            raise ValueError("Anvil exact published template conformance required") from None
        registry[key] = (variant.qualification_receipt_sha256, digest(profile), spec_model)
    files = read_archive(raw)
    if "praxis-export.json" not in files:
        raise ValueError("Existing praxis-export.json manifest required")
    document = _document(files["praxis-export.json"])
    manifest = CandidateExport.model_validate(document)
    if manifest.execution != {"location": "anvil_only", "paid_calls": False} or manifest.execution["paid_calls"] is not False:
        raise ValueError("Existing Anvil-only source export execution declaration required")
    declared = {"praxis-export.json"}
    used_assets, task_ids, revisions, decoded = set(), set(), set(), []
    errors, needs = [], set()

    def issue(code, filename, parts, message, fix):
        item = {"code": code, "owner": "praxis", "file": filename,
                "pointer": pointer(parts), "message": message, "fix": fix, "retryable": False}
        if item not in errors:
            errors.append(item)

    for index, entry in enumerate(manifest.tasks):
        key = (entry.template.id, entry.template.version, entry.template.sha256)
        if key not in registry:
            raise ValueError("Current exact application-type template qualification required")
        if entry.task_id in task_ids or (entry.task_id, entry.revision_id) in revisions:
            raise ValueError("Unique task identity and revision required")
        task_ids.add(entry.task_id)
        revisions.add((entry.task_id, entry.revision_id))
        values = {}
        for kind, ref in (("form", entry.form), ("actor", entry.actor), ("private", entry.private_assets[0])):
            path(ref.path)
            if (kind == "form" and not ref.path.startswith("forms/")
                    or kind == "actor" and ref.path != f"tasks/{entry.task_id}/actor.json"
                    or kind == "private" and ref.path != f"private/{entry.task_id}/reference.json"
                    or kind != "form" and ref.path in used_assets or ref.path not in files):
                raise ValueError("Existing distinct visibility-scoped source asset layout required")
            value = _document(files[ref.path])
            if digest(value) != ref.sha256:
                raise ValueError("Exact canonical source asset hash required")
            declared.add(ref.path)
            if kind != "form":
                used_assets.add(ref.path)
            values[kind] = value
        qualification_sha, published_form_sha, spec_model = registry[key]
        if digest(values["form"]) != published_form_sha:
            raise ValueError("Source form differs from exact published template")
        private = values["private"]
        if (private.get("access") != "private_rubric"
                or private.get("purpose") != "grader_only_reference_and_rubric"
                or type(private.get("authored")) is not dict):
            raise ValueError("Existing private authored reference classification required")
        authored = private["authored"]
        sections = authored.get("sections")
        identity = sections.get("S1") if type(sections) is dict else None
        if type(identity) is not dict or identity.get("applicationType") != entry.case_selector.value:
            raise ValueError("Product selector must derive from required S1.applicationType")
        example = identity.get("exampleGoverningState")
        # Optional pick lists permit an empty string. Project absence without
        # changing any original authored, actor or private-reference bytes.
        if type(example) is str and example == "":
            example = None
        if example is None:
            if "coverage" in document["tasks"][index]:
                raise ValueError("Omit optional example coverage when absent")
        elif entry.coverage is None or entry.coverage.example_governing_state != example:
            raise ValueError("Example metadata must match optional authored example state")
        if digest(actor_projection(values["form"], authored)) != digest(values["actor"]):
            raise ValueError("Exact published public actor projection required")
        if (entry.review.get("status") != "approved" or entry.review.get("revision_id") != entry.revision_id
                or not entry.review.get("receipt_ref")):
            raise ValueError("Exact approved revision provenance required")
        # Reuse the established full S1-S8 field/tool/output/rubric/evaluator
        # checks. No old single-state applicability restriction is imported.
        try:
            self_check(spec_model, entry, authored, values["actor"], issue,
                       lambda code, task=None: needs.add((code, task or entry.task_id)))
        except (TypeError, ValueError, AttributeError):
            issue("PX_FIELD_TYPE", entry.private_assets[0].path, ("authored",),
                  "Authored values violate the exact published field contract.",
                  "Use the published field types and immutable policy references without coercion.")
        decoded.append(DecodedTask(entry.task_id, entry.revision_id, *key, qualification_sha,
                                   entry.case_selector.value, digest(authored), digest(values["actor"]),
                                   entry.private_assets[0].sha256, entry.review["receipt_ref"], example))
    if declared != set(files):
        raise ValueError("Undeclared source assets are forbidden")
    if errors:
        raise CandidateConformanceError(errors)
    return DecodedCandidate(hashlib.sha256(raw).hexdigest(), digest(document), tuple(decoded),
                            anvil_requirements=tuple(sorted(needs)))
