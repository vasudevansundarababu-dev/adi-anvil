"""Anvil-private deterministic service proposals, never persisted effect proof.

Observed versioned requests and approved source fixtures remain distinct. These
helpers neither issue campaign authority nor produce a persisted Effect receipt.
"""

from copy import deepcopy
from datetime import timezone
from typing import Literal

from pydantic import Field, ValidationError

from anvil.dataset_export_contract import Sha
from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_world_requests import resolve_request
from anvil.marketing_world_service_sources import SCHEMA
from anvil.praxis_generic_contract import digest
from anvil.schemas import Strict


class CreativeRef(Strict):
    id: str = Field(min_length=1, max_length=200)
    version: int = Field(strict=True, ge=1, le=1000)
    descriptor_sha256: Sha


class DescriptorRequest(Strict):
    service_contract: Literal["anvil.marketing-us-pair-services.v1"]
    mode: Literal["reuse_exact_descriptor"]
    creative_refs: list[CreativeRef] = Field(min_length=1, max_length=6)


def runtime_guidance():
    """Public tool-content protocol, not new Praxis authoring/output fields."""
    return {
        "service_contract": SCHEMA,
        "production_request_content": {
            "service_contract": SCHEMA, "mode": "reuse_exact_descriptor",
            "creative_refs": [{"id": "copy a released US creative id", "version": 1,
                               "descriptor_sha256": "copy its exact released descriptor hash"}],
        },
        "scope": "Standalone existing US descriptors only. No media generation, measured inspection, real human approval, campaign or spending authority.",
        "missing_or_unsupported": "Hold with explicit issues; a quote is not a produced asset or commitment.",
        "campaign_action": "Read the released experiment proposal with source_documents.read. Copy its id/version/source_record_sha256 into source_contract_ref and save it with the exact parameters using experiments.propose. The orchestrator saves readiness.request content with service_contract, mode conditional_reuse_campaign, actual experiment_ref, experiment_contract_ref (the same source contract reference), scope, creative_refs and planned_cap_usd_minor. Copy server-issued hashes; never compute or invent them.",
        "policy_assessment": "Policy Reviewer saves review_assessments.write content with service_contract, action_ref (the actual readiness-request reference), recommendation ready/hold/revise and finding_refs. Save campaign_findings.write records for that same action_ref with findings carrying id, mandatory boolean, check claims/rights/offer/campaign_scope, status and evidence_refs of source id/version/source_record_sha256 (use key sha256). A resolved/ready flag alone supplies no proof. Return the actual saved assessment reference with campaign_findings so the orchestrator can submit it.",
        "approval_request": "Content is the saved readiness-request action plus readiness_ref to the actual saved Policy Reviewer assessment. Mode conditional_reuse_campaign; this requests the separate conditional controller decision and never self-approves. No extra Praxis authoring or final-output fields.",
        "versioned_handoff": "Include the actual readiness-request reference in the plan and assign it to policy using handoffs.assign. handoffs.assigned.read returns exact currently assigned records and server hashes; stale handoffs are unavailable. Policy returns its saved assessment reference in campaign_findings. All references use id/version/sha256 copied from server results.",
    }


def _proposal(observed, sources, failures, returned):
    return {
        "schema_version": "anvil.marketing-descriptor-service-proposal.v1",
        "observed_request_sha256": observed["request_sha256"],
        "request_ref": {"id": observed["request"]["id"], "version": observed["request"]["version"],
                        "sha256": observed["request_sha256"]},
        "source_contract_sha256": digest(sources),
        "status": "hold" if failures else "simulated_descriptor_return",
        "issues": failures, "deliveries": [] if failures else returned,
        "campaign_authority_issued": False, "real_human_approval": False,
        "actual_media_generated": False, "physical_capture_verified": False,
        "persisted_effect_verified": False,
    }


def descriptor_proposal(controller, execution, node, inputs, sources):
    """Return only actually requested, released, source-matching US descriptors.

    The caller must use a qualified private world source and atomically persist
    its effect/receipt separately. No controller approval or finance mutation.
    """
    observed = resolve_request(controller, execution, node, inputs)
    if (node["type"] != "external_system" or node["id"] != "task3"
            or sources.get("schema_version") != SCHEMA
            or sources.get("case_id") != controller.case_id
            or sources.get("execution_sha256") != digest(execution)):
        raise ValueError("Exact actual Task3 request and private source scope required")
    try:
        request = DescriptorRequest.model_validate(observed["request"]["content"])
    except ValidationError:
        return _proposal(observed, sources, [{"code": "unsupported_or_missing_descriptor_request",
                          "fix": "Use the published runtime service guidance and exact released descriptor references; new production needs its own authorized returned fixture."}], [])
    refs = [r.model_dump() for r in request.creative_refs]
    if len({r["id"] for r in refs}) != len(refs):
        return _proposal(observed, sources, [{"code": "duplicate_creative_reference",
                          "fix": "Request each exact released creative version once."}], [])
    failures, returned = check_descriptors(refs, sources, controller._clock)
    return _proposal(observed, sources, failures, returned)


def check_descriptors(refs, sources, instant):
    """Independent fixture checks; a reviewer's flags never supply their truth."""
    case = sources["case"]
    now = timestamp(instant).astimezone(timezone.utc)
    failures, returned = [], []

    def fail(code, identifier):
        failures.append({"code": code, "creative_id": identifier})

    for ref in refs:
        identifier = ref["id"]
        matches = [r for r in case["approved_creative_catalogue"] if r.get("id") == identifier]
        if len(matches) != 1:
            fail("descriptor_missing_or_ambiguous", identifier)
            continue
        creative = matches[0]
        if (creative.get("version") != ref["version"]
                or creative.get("descriptor_sha256") != ref["descriptor_sha256"]
                or creative.get("locale") != "en-US"
                or creative.get("content_bytes_present") is not False
                or creative.get("content_sha256") is not None
                or creative.get("provenance") != "TASK3_APPROVED_DESCRIPTOR_FIXTURE_NOT_GENERATED_CONTENT"):
            fail("descriptor_version_scope_mismatch", identifier)
            continue
        if timestamp(creative["released_at"]) > now:
            fail("descriptor_not_released", identifier)
            continue
        approvals = [r for r in case["approval_fixtures"] if r.get("target_id") == identifier
                     and r.get("target_version") == ref["version"]
                     and r.get("descriptor_sha256") == ref["descriptor_sha256"]
                     and r.get("decision") == "APPROVED_FOR_STANDALONE_SIMULATION_ONLY"
                     and r.get("real_human_decision") is False
                     and r.get("issuer") == "environment_fixture"
                     and r.get("provenance") == "EXPLICIT_SIMULATED_APPROVAL"]
        deliveries = [r for r in case["task3_delivery_fixtures"] if r.get("creative_id") == identifier
                      and r.get("creative_version") == ref["version"]
                      and r.get("descriptor_sha256") == ref["descriptor_sha256"]]
        if len(approvals) != 1 or len(deliveries) != 1:
            fail("matching_simulated_approval_or_delivery_missing", identifier)
            continue
        approval, delivery = approvals[0], deliveries[0]
        negatives = [r for r in case["approval_fixtures"] if r.get("target_id") == identifier
                     and r.get("target_version") in (None, ref["version"])
                     and r.get("decision") in {"REJECTED", "REVISION_REQUIRED", "SUPERSEDED"}
                     and timestamp(r["released_at"]) <= now
                     and timestamp(r["released_at"]) >= timestamp(approval["released_at"])]
        if negatives:
            fail("current_rejection_revision_or_supersession", identifier)
            continue
        if (timestamp(approval["released_at"]) > now or timestamp(delivery["released_at"]) > now
                or delivery.get("approval_ref") != approval["id"]
                or delivery.get("asset_bytes_exist") is not False
                or delivery.get("asset_content_sha256") is not None
                or delivery.get("human_approval") is not False
                or delivery.get("provenance") != "TASK3_STANDALONE_DESCRIPTOR_FIXTURE_NO_MEDIA"
                or delivery.get("technical_inspection") != "FIXTURE_ASSERTION_ONLY_NOT_MEASURED"):
            fail("delivery_release_or_fixture_provenance_mismatch", identifier)
            continue
        rights = creative["rights_fixture"]
        if (delivery["rights_fixture"] != rights or rights.get("allowed_market") != "US"
                or rights.get("allowed_channel") != creative["channel"]
                or not rights["effective_from"] <= now.date().isoformat() <= rights["effective_to"]):
            fail("rights_scope_or_validity_mismatch", identifier)
            continue
        offers = [r for r in sources["shared"]["offers"] if r.get("id") == creative["offer_id"]
                  and r.get("market") == "US" and r.get("sku") == "VEYRA-HUSH-ONE"
                  and r["effective_from"] <= now.date().isoformat() <= r["effective_to"]]
        evidence = {(r["id"], r["version"]) for r in case["claim_evidence"]
                    if r.get("sku") == "VEYRA-HUSH-ONE" and r.get("real_test_performed") is False}
        if (len(offers) != 1 or delivery["claim_evidence_refs"] != creative["claim_evidence_refs"]
                or any((r["id"], r["version"]) not in evidence for r in creative["claim_evidence_refs"])):
            fail("current_offer_or_exact_claim_evidence_missing", identifier)
            continue
        returned.append(deepcopy(delivery))
    return failures, returned


def baseline_manifest(controller, sources, attachment, week):
    """Materialize only released preexisting descriptors, never a new Task3 run."""
    from anvil.marketing_paid_world import BaselineDescriptors, OpeningBaselineDescriptors
    from anvil.marketing_task2_contract import WIRE_ROLES
    from anvil.marketing_world_readiness import CampaignAction, Findings, _evidence, _object

    refs = [{key: row[key] for key in ("id", "version", "descriptor_sha256")}
            for row in sources["case"]["approved_creative_catalogue"]]
    failures, deliveries = check_descriptors(refs, sources, controller._clock)
    available = {r["public"].get("id"): r["public"] for r in controller._initial["task3-deliveries"]
                 if r.get("actor_visible") is True and r.get("outcome_binding") is None
                 and timestamp(r["released_at"]) <= timestamp(controller._clock)}
    selected = []
    for delivery in deliveries:
        if available.get(delivery["id"]) != delivery:
            failures.append({"code": "baseline_delivery_not_actually_released", "creative_id": delivery["creative_id"]})
        else:
            selected.append(delivery)
    blocked = set()
    for record in controller._objects.values():
        if record.get("kind") != "campaign-findings" or record.get("created_by_role") != WIRE_ROLES["policy"]:
            continue
        try:
            findings = Findings.model_validate(record["content"])
            saved_action = _object(controller, findings.action_ref, "readiness-requests", "orchestrator")
            action = CampaignAction.model_validate(saved_action["content"])
            action_refs = [r.model_dump() for r in action.creative_refs]
            checks, _ = check_descriptors(action_refs, sources, controller._clock)
            current = {f.id: f for f in findings.findings}
            for _, previous in controller._keys.values():
                if type(previous) is not dict or previous.get("id") != record["id"] or previous.get("kind") != "campaign-findings":
                    continue
                earlier = Findings.model_validate(previous["content"])
                if earlier.action_ref == findings.action_ref and any(
                    f.mandatory and (f.id not in current or not current[f.id].mandatory) for f in earlier.findings
                ):
                    blocked.update(r["id"] for r in action_refs)
            for finding in findings.findings:
                if not finding.mandatory:
                    continue
                expected = _evidence(sources, action_refs, finding.check) if not checks else set()
                actual = {(e.id, e.version, e.sha256) for e in finding.evidence_refs}
                if finding.status != "resolved" or not expected or not expected <= actual:
                    blocked.update(r["id"] for r in action_refs)
        except (ValidationError, ValueError, TypeError, KeyError, AttributeError, StopIteration):
            blocked.update(r["id"] for r in refs)
    selected = [r for r in selected if r["creative_id"] not in blocked]
    failures.extend({"code": "baseline_has_unresolved_mandatory_findings", "creative_id": key} for key in sorted(blocked))
    if not selected:
        return None
    value = {
        "schema_version": "anvil.marketing-baseline-descriptors.v1",
        **{key: attachment[key] for key in ("world_binding_id", "world_binding_sha256", "episode_id", "generation", "case_id")},
        "week": week, "source_contract_sha256": digest(sources),
        "provenance": "PREEXISTING_STANDALONE_DESCRIPTOR_FIXTURES", "deliveries": selected, "issues": failures,
        "new_task3_effect": False, "actual_media_generated": False, "actual_media_inspected": False,
        "campaign_authority_issued": False, "spend_authority_issued": False,
    }
    if week == 0:
        value["schema_version"] = "anvil.marketing-opening-baseline-descriptors.v1"
    return (OpeningBaselineDescriptors if week == 0 else BaselineDescriptors).model_validate(value).model_dump(mode="json")
