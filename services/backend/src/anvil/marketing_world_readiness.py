"""Owner-confirmed readiness conditions, separate from controller authority.

No dates or candidate ready/resolved flags alone issue campaign approval.
This supports only the approved exact US-pair reuse experiment fixtures.
"""

from copy import deepcopy
from datetime import timezone
from typing import Literal

from pydantic import Field, StrictInt, ValidationError

from anvil.dataset_export_contract import Sha
from anvil.marketing_task2_contract import WIRE_ROLES
from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_world_requests import RequestReference, resolve_request
from anvil.marketing_world_service_sources import SCHEMA
from anvil.marketing_world_services import CreativeRef, check_descriptors
from anvil.praxis_generic_contract import canonical, digest
from anvil.schemas import Strict

RULE = "anvil.marketing-campaign-readiness.v1"
OWNER_DECISION = "codex-owner-answer:call_88610dbfb6d049f98b86b31864b5de7a"


class Scope(Strict):
    market: Literal["US"]
    locale: Literal["en-US"]
    channel: Literal["search"]
    weeks: list[StrictInt] = Field(min_length=2, max_length=2)
    keywords: list[str] = Field(min_length=2, max_length=2)


class CampaignAction(Strict):
    service_contract: Literal["anvil.marketing-us-pair-services.v1"]
    mode: Literal["conditional_reuse_campaign"]
    experiment_ref: RequestReference
    experiment_contract_ref: RequestReference
    scope: Scope
    creative_refs: list[CreativeRef] = Field(min_length=2, max_length=2)
    planned_cap_usd_minor: int = Field(strict=True, ge=1, le=200000)


class CampaignRequest(CampaignAction):
    readiness_ref: RequestReference


class Assessment(Strict):
    service_contract: Literal["anvil.marketing-us-pair-services.v1"]
    action_ref: RequestReference
    recommendation: Literal["ready", "hold", "revise"]
    finding_refs: list[RequestReference] = Field(max_length=100)


class EvidenceRef(Strict):
    id: str = Field(min_length=1, max_length=200)
    sha256: Sha
    version: int = Field(strict=True, ge=1, le=1000)


class Finding(Strict):
    id: str = Field(min_length=1, max_length=100)
    mandatory: bool = Field(strict=True)
    check: Literal["claims", "rights", "offer", "campaign_scope"]
    status: Literal["open", "resolved", "unknown"]
    evidence_refs: list[EvidenceRef] = Field(max_length=50)


class Findings(Strict):
    service_contract: Literal["anvil.marketing-us-pair-services.v1"]
    action_ref: RequestReference
    findings: list[Finding] = Field(max_length=100)


def _object(controller, ref, kind, role):
    value = controller._objects.get(ref.id)
    if (type(value) is not dict or value.get("version") != ref.version
            or digest(value) != ref.sha256 or value.get("kind") != kind
            or value.get("created_by_role") != WIRE_ROLES[role]
            or value.get("simulation_only") is not True):
        raise ValueError("Current exact assigned-role assessment/experiment/finding required")
    return value


def action_identity(request):
    scope = request.scope.model_dump()
    scope["keywords"] = sorted(scope["keywords"])
    return {
        "mode": request.mode, "experiment_contract_ref": request.experiment_contract_ref.model_dump(),
        "scope": scope, "creative_refs": sorted([r.model_dump() for r in request.creative_refs], key=lambda r: r["id"]),
        "planned_cap_usd_minor": request.planned_cap_usd_minor,
    }


def _evidence(sources, refs, check):
    """Expected evidence comes from actual sources, not candidate resolution flags."""
    catalog = {r["id"]: r for r in sources["case"]["approved_creative_catalogue"]}
    wanted = set()
    for ref in refs:
        creative = catalog[ref["id"]]
        if check == "claims":
            records = {(r["id"], r["version"]): r for r in sources["case"]["claim_evidence"]}
            wanted.update((r["id"], r["version"], digest(records[(r["id"], r["version"])]))
                          for r in creative["claim_evidence_refs"])
        elif check == "rights":
            wanted.add((creative["id"], creative["version"], digest(creative)))
        elif check == "offer":
            offer = next(r for r in sources["shared"]["offers"] if r["id"] == creative["offer_id"])
            wanted.add((offer["id"], offer["version"], digest(offer)))
        else:
            contract = sources["case"]["experiment_proposal_contract"]
            wanted.add((contract["id"], contract["version"], digest(contract)))
    return wanted


def assess(controller, execution, node, inputs, sources):
    observed = resolve_request(controller, execution, node, inputs)
    if (node["type"] != "human_step" or node["id"] != "approver"
            or sources.get("schema_version") != SCHEMA or sources.get("case_id") != controller.case_id
            or sources.get("execution_sha256") != digest(execution)):
        raise ValueError("Exact observed campaign request and private source scope required")
    report = {"schema_version": RULE, "owner_decision_ref": OWNER_DECISION,
              "request_ref": {"id": observed["request"]["id"], "version": observed["request"]["version"], "sha256": observed["request_sha256"]},
              "source_contract_sha256": digest(sources), "ready": False, "issues": [],
              "campaign_authority_issued": False, "real_human_approval": False}
    issues = report["issues"]
    try:
        request = CampaignRequest.model_validate(observed["request"]["content"])
        action = action_identity(request)
        report["reviewed_action_sha256"] = digest(action)
        refs = action["creative_refs"]
        if len({r["id"] for r in refs}) != 2 or any(type(w) is not int for w in request.scope.weeks):
            raise ValueError("Exact distinct creative versions and integer windows required")
        conditional = sources["conditional_campaign_approval_sources"][controller._outcome]
        expected_scope = deepcopy(conditional["scope"])
        expected_scope["keywords"] = sorted(expected_scope["keywords"])
        expected_refs = sorted(conditional["creative_refs"], key=lambda r: r["id"])
        contract = sources["case"]["experiment_proposal_contract"]
        public_contract_ref = {"id": contract["id"], "version": contract["version"], "sha256": digest(contract)}
        if (canonical(action["scope"]) != canonical(expected_scope)
                or canonical(refs) != canonical(expected_refs)
                or request.experiment_contract_ref.model_dump() != public_contract_ref
                or request.planned_cap_usd_minor != conditional["approved_cap_usd_minor"]
                or request.planned_cap_usd_minor != contract["planned_cap_usd_minor"]):
            issues.append({"code": "conditional_controller_scope_version_or_cap_mismatch"})
        experiment = _object(controller, request.experiment_ref, "experiments", "performance")
        if (set(experiment["content"]) != {"source_contract_ref", "parameters"}
                or experiment["content"]["source_contract_ref"] != public_contract_ref
                or canonical(experiment["content"]["parameters"]) != canonical(contract)):
            issues.append({"code": "actual_proposed_experiment_differs_from_authorized_fixture"})
        failures, _ = check_descriptors(refs, sources, controller._clock)
        issues.extend(failures)
        now = timestamp(controller._clock).astimezone(timezone.utc)
        if (now < timestamp(conditional["issued_at_if_selected"])
                or now >= timestamp(contract["start"] + "T00:00:00Z")):
            issues.append({"code": "campaign_authority_not_yet_available_or_would_be_retroactive"})
        saved = _object(controller, request.readiness_ref, "readiness-assessments", "policy")
        assessment = Assessment.model_validate(saved["content"])
        saved_action = _object(controller, assessment.action_ref, "readiness-requests", "orchestrator")
        saved_action_body = CampaignAction.model_validate(saved_action["content"])
        if (canonical(action_identity(saved_action_body)) != canonical(action)
                or saved_action_body.experiment_ref != request.experiment_ref
                or assessment.recommendation != "ready"):
            issues.append({"code": "saved_policy_assessment_not_ready_for_exact_submitted_versions"})
        current = {r["id"]: r for r in controller._objects.values()
                   if r.get("kind") == "campaign-findings" and r.get("created_by_role") == WIRE_ROLES["policy"]
                   and r.get("content", {}).get("action_ref") == assessment.action_ref.model_dump()}
        if len({r.id for r in assessment.finding_refs}) != len(assessment.finding_refs) or {r.id for r in assessment.finding_refs} != set(current):
            issues.append({"code": "mandatory_finding_set_missing_or_contradictory"})
        for ref in assessment.finding_refs:
            saved_finding = _object(controller, ref, "campaign-findings", "policy")
            findings = Findings.model_validate(saved_finding["content"])
            if findings.action_ref != assessment.action_ref:
                issues.append({"code": "finding_belongs_to_other_submitted_versions"})
            by_id = {finding.id: finding for finding in findings.findings}
            if len(by_id) != len(findings.findings):
                issues.append({"code": "ambiguous_duplicate_finding"})
            # Existing immutable idempotency returns retain earlier versions.
            # Removing a formerly mandatory finding is not a resolution.
            for _, prior in controller._keys.values():
                if (type(prior) is dict and prior.get("id") == saved_finding["id"]
                        and prior.get("kind") == "campaign-findings"):
                    earlier = Findings.model_validate(prior["content"])
                    if earlier.action_ref != assessment.action_ref:
                        continue
                    for old in earlier.findings:
                        if old.mandatory and (old.id not in by_id or not by_id[old.id].mandatory):
                            issues.append({"code": "mandatory_finding_removed_or_downgraded"})
            for finding in findings.findings:
                if not finding.mandatory:
                    continue
                actual = {(e.id, e.version, e.sha256) for e in finding.evidence_refs}
                expected = _evidence(sources, refs, finding.check) if not failures else set()
                if finding.status != "resolved" or not expected or not expected <= actual:
                    issues.append({"code": "mandatory_finding_has_no_passing_underlying_resolution", "finding_id": finding.id})
        report["assessment_ref"] = request.readiness_ref.model_dump()
        report["experiment_ref"] = request.experiment_ref.model_dump()
        report["readiness_checks"] = {name: "passed" if not issues else "not_established"
                                      for name in ("claims", "rights", "offer", "campaign_scope", "mandatory_findings")}
        report["ready"] = not issues
    except (ValidationError, ValueError, KeyError, TypeError, AttributeError, StopIteration):
        issues.append({"code": "readiness_evidence_missing_unknown_or_invalid"})
    return report
