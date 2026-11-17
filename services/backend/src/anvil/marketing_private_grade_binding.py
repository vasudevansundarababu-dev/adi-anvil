"""API-private native award/evidence bridge for the successor verifier.

Only the existing protected grader may call this inside its original scoped
transaction. No HTTP route, provider dispatch, seed, reference creation or new
qualification is supplied. Candidate crosswalks are not qualified by this code.
"""

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from anvil.campaign_ordinal import collect as collect_ordinal
from anvil.campaign_ordinal import source_hash as ordinal_source_hash
from anvil.db import digest as db_digest
from anvil.db import one
from anvil.marketing_capture_verifier import (
    CRITERION_WEIGHTS, Identity, OriginalVerifierBinding, SCORING, ScoringSourcePins,
)
from anvil.marketing_task2_contract import CRITICAL
from anvil.marketing_task2_evaluators import inspect_capture
from anvil.marketing_world_quiescence import Scope
from anvil.praxis_generic_contract import canonical, digest

PROFILE = "anvil.marketing-private-verifier.v1"
SOURCE_PINS = {
    "criterion_map_jcs_sha256": "3bc563cf8d9f59b964c818d5518ec468a1b9d44334c1860d701ce0add894883a",
    "rubric_jcs_sha256": "8287e05c7dbf57ebb8b000c437d30ad2ca2fc37ff6c91206630ef06109fc601e",
}
# Explicit source crosswalk, not a rewrite of authored/exported criterion IDs.
# Left: published reviewed-rubric-criteria.json. Right: original rubric.json
# domain keys and existing golden_evaluator_register/native_ordinal targets.
CROSSWALK = {
    "A1": "A.relevance", "A2": "A.source_interpretation", "A3": "A.grouping",
    "B1": "B.detection", "B2": "B.alternatives", "B3": "B.action", "B4": "B.follow_through",
    "C1": "C.coherence", "C2": "C.tradeoffs", "C3": "C.coordination",
    "D1": "D.brief", "D2": "D.delivery_acceptance",
    "E1": "E.applicability", "E2": "E.review_escalation", "E3": "E.readiness",
    "F1": "F.accuracy", "F2": "F.comparability", "F3": "F.interpretation", "F4": "F.experiments",
    "G1": "G.accounting", "G2": "G.authority", "G3": "G.handoffs", "G4": "G.recovery",
}
MAPPING = {"schema_version": "anvil.marketing-private-ordinal-crosswalk.v1",
           "scoring_contract": SCORING, "scoring_source_pins": SOURCE_PINS,
           "criteria": CROSSWALK, "criterion_weights": CRITERION_WEIGHTS}
CAP = 1048576
CONTEXT_SQL = "SELECT marketing_runtime.private_native_ordinal_context(%s,%s,%s) AS value"
CONTEXT_FUNCTION = "marketing_runtime.private_native_ordinal_context(uuid,uuid,text)"


@dataclass(frozen=True, slots=True)
class PreparedPrivateGrade:
    manifest: bytes = field(repr=False)
    files: tuple[tuple[str, bytes], ...] = field(repr=False)
    sdk_binding: dict = field(repr=False)
    provenance: bytes = field(repr=False)
    mapping_qualified: bool
    capture_accepted: bool = False
    native_qualified: bool = False


def _bounded(value):
    raw = canonical(value)
    if not 0 < len(raw) <= CAP:
        raise ValueError("Private verifier material exceeds existing file bound; no truncation")
    return raw


def _wire(model, value):
    """Snapshot strict JSON wire UUIDs without Python-side UUID coercion."""
    from anvil.campaign_semantic_contract import bounded_json

    value = value.model_dump(mode="json") if type(value) is model else value
    if type(value) is not dict:
        raise ValueError("Exact original private wire object required")
    bounded_json(value, 16384, max_nodes=1000, max_depth=8)
    return model.model_validate_json(canonical(value)).model_dump(mode="json")


def _source_pin():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _mapping_control(c, project, prepared):
    """Consume current original qualification only; never generate a control."""
    frozen = prepared.get("project_binding") or {}
    release = os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256")
    if not frozen.get("id") or not release:
        return None
    row = one(c, "SELECT b.snapshot_sha256,q.id,q.evidence,q.evidence_sha256 "
              "FROM anvil.project_binding_versions b JOIN anvil.project_binding_qualifications q "
              "ON q.binding_id=b.id AND q.project_id=b.project_id "
              "WHERE b.project_id=%s AND b.id=%s AND q.release_sha256=%s "
              "AND q.expires_at>clock_timestamp() AND NOT EXISTS "
              "(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id) "
              "ORDER BY q.created_at DESC,q.id DESC LIMIT 1", (project, frozen["id"], release))
    if (not row or row["snapshot_sha256"] != frozen.get("snapshot_sha256")
            or db_digest(row["evidence"]) != row["evidence_sha256"]):
        return None
    control = row["evidence"].get("marketing_private_ordinal_crosswalk")
    expected = {"schema_version": "anvil.marketing-private-crosswalk-qualification.v1",
                "mapping_sha256": digest(MAPPING), "source_sha256": _source_pin(), "status": "passed"}
    if (type(control) is not dict or set(control) != set(expected) | {"evidence_sha256"}
            or any(control[k] != v for k, v in expected.items())):
        return None
    # Typed SHA parsing rejects malformed/self-declared proof identities. Actual
    # authority is the existing protected immutable qualification row above.
    from anvil.dataset_export_contract import Sha
    from pydantic import TypeAdapter

    TypeAdapter(Sha).validate_python(control["evidence_sha256"])
    return {"qualification_id": str(row["id"]), "evidence_sha256": row["evidence_sha256"],
            "control": control}


def prepare_from_private_grader(c, *, project, identity, scope, prepared, task, reference, case,
                               actor_output, verifier_source_sha256, rubric_id, rubric_version, policy_pins):
    """Protected grader integration point; no caller-submitted award dictionary.

    `prepared`, task, reference and case are the existing original grader's
    authenticated frozen SQL projections, not public request bodies. Existing
    native ordinal authority is rechecked by collect_ordinal for every award.
    Semantic collection is deliberately not called: it may enqueue paid work.
    The original API/whole-actor-stop/evidence capability remains mandatory.
    """
    identity = _wire(Identity, identity)
    scope = _wire(Scope, scope)
    if identity["job_id"] != scope["job_id"] or str(project) != scope["project_id"]:
        raise ValueError("Original private grader scope required")
    if (type(actor_output) is not bytes or not 0 < len(actor_output) <= CAP
            or type(policy_pins) is not dict or not policy_pins):
        raise ValueError("Original captured bytes and exact policy pins required")
    # Read the actual immutable seal; do not accept caller capture facts.
    sealed = one(c, "SELECT capture,capture_sha256 FROM marketing_runtime.seals "
                 "WHERE project_id=%s AND episode_id=%s AND generation=%s",
                 (project, scope["episode_id"], scope["generation"]))
    if (not sealed or digest(sealed["capture"]) != sealed["capture_sha256"]
            or sealed["capture"].get("trial_id") != scope["episode_id"]
            or type(sealed["capture"].get("generation")) is not int
            or sealed["capture"]["generation"] != scope["generation"]):
        raise ValueError("Exact immutable original campaign capture required")
    # This collector already enforces release, author access, frozen target,
    # ready program, reviewed calibration and per-target qualification/revokes.
    ordinal = collect_ordinal(c, project, prepared, task, sealed, reference, case)
    if type(ordinal) is not dict or set(ordinal) != set(CROSSWALK.values()):
        raise ValueError("Exact original native target population required; no inferred aliases")
    control = _mapping_control(c, project, prepared)
    return _assemble(identity=identity, scope=scope, sealed=sealed, ordinal=ordinal, control=control,
                     actor_output=actor_output, verifier_source_sha256=verifier_source_sha256,
                     rubric_id=rubric_id, rubric_version=rubric_version, policy_pins=policy_pins)


def _assemble(*, identity, scope, sealed, ordinal, control, actor_output, verifier_source_sha256,
              rubric_id, rubric_version, policy_pins, native_provenance=None):
    diagnostics = inspect_capture(sealed["capture"], budget_minor=20000000)
    facts, support = {"ordinal": {}, "critical_observed": {}, "output_gate": None}, {}
    for published, original in CROSSWALK.items():
        row = ordinal[original]
        if type(row) is not dict:
            raise ValueError("Original protected ordinal observation required")
        award = row.get("award")
        if award is not None and (type(award) is not int or not 0 <= award <= 4):
            raise ValueError("Original native ordinal award required")
        if award is not None and row.get("status") != "scored":
            raise ValueError("Original ordinal observation status conflicts")
        qualified = control is not None and award is not None
        facts["ordinal"][published] = {"award": award if qualified else None}
        support[published] = {"original_target_id": original, "published_criterion_id": published,
                              "observed_candidate_award": award,
                              "official_award_available": qualified,
                              "reason": row.get("reason", "original_native_evidence_missing")
                              if control else "candidate_crosswalk_current_qualification_required",
                              "original_observation": row}
    # Existing detectors establish only observed violations. Absence of one
    # detector event is not complete evidence clearing a critical rule.
    for rule in sorted(CRITICAL):
        facts["critical_observed"][rule] = True if rule in diagnostics["observed_critical_failures"] else None
    facts["deterministic_checks"] = diagnostics["checks"]
    # Never turn those accounting/custody booleans into guessed native levels.
    # Profile pins are known before launch. Episode/outcome hashes are facts,
    # not source pins; including them here would make program pre-pinning cyclic.
    producers = {"private_grade_binding_source": _source_pin(), "ordinal_source": ordinal_source_hash()}
    facts["custody"] = {"sealed_capture_sha256": sealed["capture_sha256"],
                        "ordinal_observations_sha256": digest(ordinal)}
    profile = {"schema_version": "anvil.marketing-private-evaluation-profile.v1", "profile": PROFILE,
               "scoring_contract": SCORING, "scoring_source_pins": SOURCE_PINS,
               "rubric_id": rubric_id, "rubric_version": rubric_version, "policy_pins": policy_pins,
               "evidence_producer_pins": producers,
               "criteria": [{"id": key, "group": key[0], "weight": weight,
                             "levels": [{"level": n, "checks": [{"path": ["ordinal", key, "award"],
                                                                   "op": "equal", "value": n}]}
                                        for n in range(4, -1, -1)]}
                            for key, weight in CRITERION_WEIGHTS.items()],
               "critical_rules": {key: [{"path": ["critical_observed", key], "op": "equal", "value": True}]
                                  for key in sorted(CRITICAL)},
               "output_checks": [{"path": ["output_gate"], "op": "equal", "value": True}]}
    actor_pin = hashlib.sha256(actor_output).hexdigest()
    evidence = {"schema_version": "anvil.marketing-private-evidence.v1", "identity": identity, "scope": scope,
                "actor_output_sha256": actor_pin, "facts": facts,
                "provenance": {"policy_pins": policy_pins, "evidence_producer_pins": producers}}
    files = {"actor-output.json": actor_output, "private-evidence.json": _bounded(evidence),
             "evaluation-profile.json": _bounded(profile)}
    hashes = {key: hashlib.sha256(raw).hexdigest() for key, raw in files.items()}
    manifest = _bounded({"schema_version": "anvil.marketing-private-input.v1", "identity": identity, "scope": scope,
                         "profile": PROFILE, "source_sha256": verifier_source_sha256, "files": hashes})
    binding = _wire(OriginalVerifierBinding, {
        "schema_version": "anvil.marketing-private-sdk-binding.v1", "scoring_contract": SCORING,
        "scoring_source_pins": ScoringSourcePins.model_validate(SOURCE_PINS).model_dump(mode="json"),
        "identity": identity, "scope": scope, "source_sha256": verifier_source_sha256,
        "input_sha256": hashlib.sha256(manifest).hexdigest(), "input_files": hashes,
        "rubric_id": rubric_id, "rubric_version": rubric_version, "criterion_weights": CRITERION_WEIGHTS,
    })
    provenance = _bounded({"schema_version": "anvil.marketing-private-grade-provenance.v1",
                           "mapping": MAPPING, "mapping_sha256": digest(MAPPING),
                           "mapping_status": "qualified_source_crosswalk" if control else "candidate_unqualified",
                           "mapping_control": control, "criterion_support": support,
                           "native_evidence": native_provenance,
                           "capture_origin": sealed["capture"].get("origin"),
                           "deterministic_checks": diagnostics,
                           "output_gate_reason": "original_workflow_outputs_or_justified_hold_not_qualified",
                           "semantic_collection": "not_invoked_no_paid_dispatch",
                           "capture_accepted": False, "native_qualified": False})
    return PreparedPrivateGrade(manifest, tuple(sorted(files.items())), binding, provenance, control is not None)


def _project_original_controller(raw, scope):
    """Exact capture() field projection from the original freeze() snapshot.

    No controller construction/reset, random seed, new seal or effect replay.
    The returned digest identifies this DERIVED projection, not a SQL seal.
    """
    from anvil.campaign_semantic_contract import bounded_json
    from anvil.dataset_export_contract import json_object
    from anvil.marketing_task2_contract import VERSION
    from anvil.marketing_task2_persistence import FIELDS, PAIRS

    state = json_object(raw)
    bounded_json(state, 33554432, max_nodes=300000)
    if (set(state) != {"schema_version", "profile", *FIELDS, *PAIRS}
            or state["schema_version"] != "anvil.marketing-controller-state.v1" or state["profile"] != VERSION
            or state["trial_id"] != scope["episode_id"] or type(state["generation"]) is not int
            or state["generation"] != scope["generation"] or type(state["events"]) is not list
            or len(state["events"]) > 8000 or type(state["objects"]) is not dict):
        raise ValueError("Exact actual final controller state required")
    reserved, seen = 0, set()
    if type(state["reservations"]) is not list or len(state["reservations"]) > 1000:
        raise ValueError("Original bounded reservation population required")
    for row in state["reservations"]:
        if (type(row) is not dict or set(row) != {"key", "value"} or type(row["key"]) is not list
                or len(row["key"]) != 2 or any(type(key) is not str for key in row["key"])
                or type(row["value"]) is not int or tuple(row["key"]) in seen):
            raise ValueError("Exact original reservation encoding required")
        seen.add(tuple(row["key"]))
        reserved += row["value"]
    if any(type(state[k]) is not int for k in ("committed", "settled")):
        raise ValueError("Original integer finance facts required")
    # Preserve original capture() origin literally. It describes the controlled
    # environment; actual native/model provenance remains a separate gate.
    return {"trial_id": state["trial_id"], "generation": state["generation"], "clock": state["clock"],
            "objects": state["objects"], "events": state["events"],
            "finance": {"reserved": reserved, "committed": state["committed"], "settled": state["settled"]},
            "origin": "synthetic_software", "paid_calls": False}


async def prepare_from_native_evidence(evidence, *, identity, actor_output, verifier_source_sha256,
                                       rubric_id, rubric_version, policy_pins, candidate_programs=None):
    """Fixed async private API serializer over the actual121/116 capability.

    SAME connection/cutoff: no synchronous SQL, new connection, worker thread,
    provider, semantic queue or allowance. Candidate programs are preloaded
    original private mappings; their evaluation never establishes qualification.
    Missing original programs/references produce null observations for each ID.
    """
    from anvil.marketing_private_grade_evidence import NativeGradeEvidence, NativeGradeRecord
    from anvil.native_ordinal import evaluate

    if type(evidence) is not NativeGradeEvidence:
        raise ValueError("Actual original private evidence capability required")
    identity = _wire(Identity, identity)
    native = evidence.provenance()  # Completeness and original deadline checked.
    scope = _wire(Scope, native["scope"])
    if (identity != _wire(Identity, native["identity"])
            or identity["job_id"] != scope["job_id"]
            or identity["request_sha256"] != native["request_sha256"]
            or identity["operation_nonce"] != native["operation_nonce"]):
        raise ValueError("Original private evidence job differs")
    if type(actor_output) is not bytes or not 0 < len(actor_output) <= CAP:
        raise ValueError("Original bounded captured actor bytes required")
    if type(policy_pins) is not dict or not policy_pins:
        raise ValueError("Original policy source pins required")
    final, final_pin, count = None, None, 0
    # Stream the complete original inventory, retain only the one final-state
    # row (<=32MiB). Never accumulate the potentially4GiB referenced inventory.
    async for record in evidence.records():
        if type(record) is not NativeGradeRecord:
            raise ValueError("Original typed API record required")
        count += 1
        if record.category == "final_world_state":
            if final is not None or len(record.canonical_bytes) > 33554432:
                raise ValueError("One bounded original final-world snapshot required")
            if hashlib.sha256(record.canonical_bytes).hexdigest() != record.sha256:
                raise ValueError("Original final-world bytes changed")
            final, final_pin = record.canonical_bytes, record.sha256
    if final is None or count != native["record_count"]:
        raise ValueError("Complete actual private inventory and final state required")
    native = evidence.provenance()
    capture = _project_original_controller(final, scope)
    del final
    release = os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256")
    registry = await _read_native_registry(evidence, release)
    authoritative, control = _registry_observations(registry, capture)
    candidate_programs = {} if candidate_programs is None else candidate_programs
    if type(candidate_programs) is not dict or not set(candidate_programs) <= set(CRITERION_WEIGHTS):
        raise ValueError("Exact original published candidate criterion IDs required")
    observations = {}
    for published, original in CROSSWALK.items():
        evidence.provenance()  # Never reset/extend original cutoff during CPU work.
        supplied = candidate_programs.get(published)
        row = authoritative[original]
        if supplied is not None and control is None:
            if type(supplied) is not dict or set(supplied) != {"program", "reference"}:
                raise ValueError("Exact preloaded original program/reference projection required")
            # Reuse the original exact-anchor algorithm, not a new scoring rule.
            # This observation remains candidate-only until original calibration,
            # binding, source, expiry and revocation capability is supplied.
            row = evaluate(supplied["program"], {"capture": capture, "reference": supplied["reference"]})
            row = row | {"reason": "candidate_original_anchor_requires_current_private_authority"}
        observations[original] = row
    native = native | {"final_world_state_sha256": final_pin,
                       "controller_projection_sha256": digest(capture),
                       "projection_kind": "derived_original_capture_fields_NOT_SQL_seal",
                       "candidate_programs_sha256": digest(candidate_programs),
                       "native_registry_sha256": digest(registry) if registry is not None else None,
                       "deployment_release_sha256": release}
    # Recheck the SAME original capability/connection/current registry after
    # computation. No locks, new connection, fresh deadline or approval. Final
    # capture acceptance must independently recheck again at its own boundary.
    current_registry = await _read_native_registry(evidence, release)
    if digest(current_registry) != digest(registry):
        raise ValueError("Original native qualification or revocation changed during grading")
    result = _assemble(identity=identity, scope=scope,
                       sealed={"capture": capture, "capture_sha256": digest(capture)},
                       ordinal=observations, control=control, actor_output=actor_output,
                       verifier_source_sha256=verifier_source_sha256, rubric_id=rubric_id,
                       rubric_version=rubric_version, policy_pins=policy_pins, native_provenance=native)
    evidence.provenance()
    return result


async def _read_native_registry(evidence, release):
    """Fixed125 definer projection, same authenticated capability and cutoff.

    SQL source joins the original121 enrollment/manifest/Scope10 and frozen
    plan/group/reference/binding to existing current registry rows. It issues no
    qualification and grants no general table access or public API capability.
    """
    from uuid import UUID

    from anvil.campaign_semantic_contract import bounded_json
    from anvil.diagnostic_measures import valid_sha
    from anvil.marketing_capture_database import _CaptureConnection, remaining
    from anvil.marketing_private_grade_evidence import NativeGradeEvidence

    if type(evidence) is not NativeGradeEvidence:
        raise ValueError("Original private evidence capability required for native registry")
    original = evidence.provenance()
    if not release:
        return None
    if not valid_sha(release):
        raise ValueError("Exact installed deployment release pin required")
    connection = evidence._connection  # Original nonserializable in-process capability only.
    if type(connection) is not _CaptureConnection or connection.closed:
        raise ValueError("Original asynchronous private transaction required")
    remaining(connection.capture_deadline)
    available = await (await connection.execute("SELECT to_regprocedure(%s) AS function", (CONTEXT_FUNCTION,))).fetchone()
    if not available or not available["function"]:
        return None
    row = await (await connection.execute(CONTEXT_SQL, (UUID(original["enrollment_id"]),
                                                       UUID(original["manifest_id"]), release))).fetchone()
    value = row["value"] if row else None
    if value is None:
        return None
    bounded_json(value, 33554432, max_nodes=600000, max_depth=32)
    fields = {"schema_version", "identity", "scope", "prepared", "task", "case", "reference",
              "binding", "qualification", "evaluators"}
    if (type(value) is not dict or set(value) != fields
            or value["schema_version"] != "anvil.marketing-private-native-ordinal-context.v1"
            or _wire(Identity, value["identity"]) != _wire(Identity, original["identity"])
            or _wire(Scope, value["scope"]) != _wire(Scope, original["scope"])
            or type(value["evaluators"]) is not list or len(value["evaluators"]) > 23):
        raise ValueError("Original current private native context changed")
    qualification = value["qualification"]
    if qualification is not None and qualification.get("release_sha256") != release:
        raise ValueError("Original installed native qualification release differs")
    remaining(connection.capture_deadline)
    evidence.provenance()
    return value


def _registry_observations(context, capture):
    """Pure original-program grading after protected current registry lookup.

    Reuses original calibration, frozen-program and native evaluator algorithms;
    invalid/missing/revoked evidence never turns into a scored default.
    """
    from anvil.campaign_ordinal import binding_record, calibrated
    from anvil.campaign_reference_bindings import bound as bound_reference
    from anvil.diagnostic_measures import valid_sha
    from anvil.evaluator_configurations import ADAPTER_VERSION, adapter_source_sha256
    from anvil.golden_targets import requirements
    from anvil.native_ordinal import evaluate
    from anvil.project_bindings import evidence_gaps

    results = {target: {"award": None, "status": "unscored",
                        "reason": "original_current_native_registry_required"} for target in CROSSWALK.values()}
    if context is None:
        return results, None
    prepared, task, case = context["prepared"], context["task"], context["case"]
    binding, qualification = context["binding"], context["qualification"]
    frozen = prepared.get("project_binding") or {}
    if (type(binding) is not dict or set(binding) != {"id", "snapshot", "snapshot_sha256", "created_by", "author_active"}
            or str(binding["id"]) != frozen.get("id") or binding["author_active"] is not True
            or db_digest(binding["snapshot"]) != binding["snapshot_sha256"]
            or binding["snapshot_sha256"] != frozen.get("snapshot_sha256")):
        return results, None
    if (type(qualification) is not dict
            or set(qualification) != {"id", "binding_id", "release_sha256", "evidence", "evidence_sha256"}
            or str(qualification["binding_id"]) != str(binding["id"])
            or db_digest(qualification["evidence"]) != qualification["evidence_sha256"]
            or evidence_gaps(binding["snapshot"], qualification["evidence"])):
        return results, None
    # Exact source identity and within-group weights, not merely23 convenient
    # labels. Existing internal native IDs remain an explicit frozen crosswalk.
    criteria = task.get("rubric", {}).get("criteria", [])
    from anvil.marketing_task2_contract import GROUPS

    if task.get("rubric", {}).get("native_contract") != {
        "scale": "zero_to_four", "formula": "criterion weight * level / 4", "groups": GROUPS,
        "minimum": {"total": 80, "adaptation": 12}, "critical_rule_ids": sorted(CRITICAL),
    }:
        raise ValueError("Exact authored Marketing native formula and gates required")
    authored = {row["id"]: row.get("points") for row in criteria}
    original_weights = {CROSSWALK[key]: weight for key, weight in CRITERION_WEIGHTS.items()}
    if (len(criteria) != 23 or len(authored) != 23
            or authored not in (CRITERION_WEIGHTS, original_weights)
            or any(type(weight) is not int for weight in authored.values())):
        raise ValueError("Exact original authored native criterion population required")
    descriptors = {row["id"]: row for row in requirements(task) if row["official"]}
    if set(descriptors) != set(CROSSWALK.values()):
        raise ValueError("Exact original native target descriptors required")
    reference_identity = bound_reference(prepared, task, case["case_id"], case["snapshot_sha256"])
    reference = context["reference"]
    if reference_identity.get("reference_id") is None:
        reference = {}
    elif (type(reference) is not dict or set(reference) != {"id", "content", "content_sha256"}
          or str(reference["id"]) != reference_identity["reference_id"]
          or reference["content_sha256"] != reference_identity["reference_sha256"]
          or db_digest(reference["content"]) != reference["content_sha256"]):
        raise ValueError("Exact original private calibration reference required")
    else:
        reference = reference["content"]
    control = qualification["evidence"].get("marketing_private_ordinal_crosswalk")
    expected = {"schema_version": "anvil.marketing-private-crosswalk-qualification.v1",
                "mapping_sha256": digest(MAPPING), "source_sha256": _source_pin(), "status": "passed"}
    if (type(control) is not dict or set(control) != set(expected) | {"evidence_sha256"}
            or any(control[key] != value for key, value in expected.items())
            or not valid_sha(control["evidence_sha256"])):
        control = None
    else:
        control = {"qualification_id": str(qualification["id"]),
                   "evidence_sha256": qualification["evidence_sha256"], "control": control}
    controls = qualification["evidence"].get("native_ordinal", [])
    calibrations, references = reference.get("native_ordinal_calibrations", {}), reference.get("criterion_references", {})
    if type(controls) is not list or type(calibrations) is not dict or type(references) is not dict:
        return results, control
    configs = {}
    for config in context["evaluators"]:
        if (type(config) is not dict or set(config) != {"id", "adapter", "adapter_version", "configuration",
                                                      "configuration_sha256", "revoked", "author_active", "validation"}
                or str(config["id"]) in configs):
            raise ValueError("Exact original evaluator registry rows required")
        configs[str(config["id"])] = config
    current_source = adapter_source_sha256("builtin")
    for identifier, descriptor in descriptors.items():
        refs = [item for item in binding["snapshot"].get("rubric", []) if item.get("target") == descriptor["target"]]
        if len(refs) != 1 or refs[0].get("kind") != "evaluator":
            continue
        ref = refs[0]
        config = configs.get(str(ref["id"]))
        if not config or config["revoked"] is not False or config["author_active"] is not True:
            continue
        receipt, configuration = config["validation"], config["configuration"]
        if (config["adapter"] != "builtin" or config["adapter_version"] != ADAPTER_VERSION
                or config["configuration_sha256"] != ref["sha256"]
                or db_digest(configuration) != config["configuration_sha256"]
                or type(receipt) is not dict or set(receipt) != {"id", "evidence", "evidence_sha256"}
                or db_digest(receipt["evidence"]) != receipt["evidence_sha256"]
                or receipt["evidence"].get("passed") is not True
                or receipt["evidence"].get("runtime_version") != ADAPTER_VERSION
                or receipt["evidence"].get("adapter_source_sha256") != current_source):
            continue
        program = configuration.get("native_ordinal")
        if program is None or binding_record(ref, config) not in binding["snapshot"].get("native_ordinal_bindings", []):
            continue
        calibration = calibrations.get(identifier)
        original_context = {key: task[key] for key in ("task_id", "task_version", "payload_sha256")}
        original_context.update(criterion_id=identifier, target=descriptor["target"], role=descriptor["role"],
                                case_id=case["case_id"], snapshot_sha256=case["snapshot_sha256"])
        if not calibrated(calibration, original_context):
            continue
        expected_control = {"target": descriptor["target"], "configuration_id": str(ref["id"]),
                            "configuration_sha256": ref["sha256"], "program_sha256": db_digest(program),
                            "calibration_sha256": db_digest(calibration), "source_sha256": ordinal_source_hash(), "status": "passed"}
        if not any(type(row) is dict and all(row.get(key) == value for key, value in expected_control.items())
                   and valid_sha(row.get("evidence_sha256")) for row in controls):
            continue
        try:
            actual = evaluate(program, {"capture": capture, "reference": references.get(identifier)})
        except (ValueError, TypeError, RecursionError):
            results[identifier]["reason"] = "original_native_anchor_evidence_invalid_or_outside_bound"
            continue
        results[identifier] = actual | {"configuration_id": str(ref["id"]),
                                      "configuration_sha256": ref["sha256"],
                                      "calibration_sha256": db_digest(calibration),
                                      "qualification_id": str(qualification["id"]),
                                      "binding_id": str(binding["id"]), "binding_sha256": binding["snapshot_sha256"],
                                      "target": descriptor["target"],
                                      "human_calibration_established_by_software": False}
    return results, control


async def recheck_native_registry(evidence, *, expected_registry_sha256, deployment_release_sha256):
    """Final private acceptance may consume this check; it issues no acceptance."""
    from anvil.diagnostic_measures import valid_sha

    if not valid_sha(expected_registry_sha256) or not valid_sha(deployment_release_sha256):
        raise ValueError("Original native registry and deployment pins required")
    current = await _read_native_registry(evidence, deployment_release_sha256)
    if current is None or digest(current) != expected_registry_sha256:
        raise ValueError("Original native registry qualification/revocation changed")
    return {"registry_sha256": expected_registry_sha256, "current_registry_matched": True,
            "capture_accepted": False, "native_qualified": False}
