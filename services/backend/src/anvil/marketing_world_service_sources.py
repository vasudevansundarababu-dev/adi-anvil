"""Deterministic private US-pair service normalization; no qualification grant.

Only bytes matching an independently bound source inventory are accepted.
No reviewer solutions, alternative outcomes or media bytes enter public output.
"""

import hashlib
from copy import deepcopy

from anvil.dataset_export_contract import json_object
from anvil.praxis_generic_contract import canonical, digest
from anvil.praxis_marketing_contract import MarketingExecution

SCHEMA = "anvil.marketing-us-pair-services.v1"
CASE_FILES = (
    "case.json", "approved_creative_catalogue.json", "task3_delivery_fixtures.json",
    "approval_fixtures.json", "claim_evidence.json", "production_options.json",
    "experiment_proposal_contract.json", "delivery_acceptance_contract.json",
    "accounting_contract.json",
)
SHARED_FILES = ("campaign_contract.json", "policies.json", "rubric.json", "offers.json")


def normalize(case_id, files, expected_hashes, execution):
    """Compile pinned source bytes, not an operator's approval or execution seal."""
    if case_id not in {"GT2-R01", "GT2-R02"} or type(files) is not dict or type(expected_hashes) is not dict:
        raise ValueError("Exact US-pair source population required")
    contract = MarketingExecution.model_validate(execution)
    nodes = contract.workflow_graph["nodes"]
    if (not any(n["id"] == "task3" and n["type"] == "external_system" and n.get("sendsRefs") == ["production_request"] for n in nodes)
            or not any(n["id"] == "approver" and n["type"] == "human_step" and n.get("simulated") is True
                       and n.get("permittedEvidence") == ["approval_request"] for n in nodes)):
        raise ValueError("Exact published Task3 and simulated approval interfaces required")
    paths = ["shared/" + name for name in SHARED_FILES]
    paths += ["cases/" + case_id + "/" + name for name in CASE_FILES]
    paths += [f"reviewer_only/us-pair/{case_id}/reuse-test-{branch}/conditional_campaign_approval.json"
              for branch in ("positive", "null", "negative")]
    values, provenance = {}, {}
    for path in paths:
        raw = files.get(path)
        if (type(raw) is not bytes or not 0 < len(raw) <= 1048576
                or hashlib.sha256(raw).hexdigest() != expected_hashes.get(path)):
            raise ValueError("Missing or changed independently pinned service source")
        # Reuse strict duplicate/nonfinite/depth checking for arrays as well.
        value = json_object(b'{"value":' + raw + b'}')["value"]
        canonical(value)
        values[path] = value
        provenance[path] = {"sha256": expected_hashes[path], "bytes": len(raw)}
    shared = {name[:-5]: values["shared/" + name] for name in SHARED_FILES}
    case = {name[:-5]: values[f"cases/{case_id}/{name}"] for name in CASE_FILES}
    policies, rubric = shared["policies"], shared["rubric"]
    if (type(policies) is not list or len(policies) != 23
            or {p["id"] for p in policies} != {f"POL-{i:02d}" for i in range(1, 24)}
            or any(p["version"] != 1 or p["provenance"] != "AUTHORISED_FICTIONAL_COMPANY_POLICY" for p in policies)
            or {key: value["weight"] for key, value in rubric["domains"].items()} != dict(zip("ABCDEFG", (10, 20, 15, 10, 15, 15, 15)))
            or sum(len(value["criteria"]) for value in rubric["domains"].values()) != 23
            or any(sum(value["criteria"].values()) != value["weight"] for value in rubric["domains"].values())
            or case["case"]["case_id"] != case_id or case["case"]["focus_locale"] != "en-US"
            or shared["campaign_contract"]["approval_mode"] != "ENVIRONMENT_SIMULATED_FIXTURES"
            or case["delivery_acceptance_contract"]["mode"] != "TASK2_STANDALONE_DESCRIPTOR_FIXTURES"):
        raise ValueError("Service sources differ from approved policy/rubric/US fixture scope")
    approvals = {}
    for branch in ("positive", "null", "negative"):
        path = f"reviewer_only/us-pair/{case_id}/reuse-test-{branch}/conditional_campaign_approval.json"
        value = values[path]
        if (value["decision"] != "APPROVED_IF_VALID_REQUEST_SELECTS_THIS_BRANCH"
                or value["real_human_decision"] is not False
                or value["status"] != "CONDITIONAL_ENVIRONMENT_FIXTURE_NOT_A_REAL_OR_ALREADY_ISSUED_DECISION"
                or value["provenance"] != "EXPLICIT_SIMULATED_CONDITIONAL_CAMPAIGN_AUTHORITY"
                or value["experiment_id"] != case["experiment_proposal_contract"]["id"]
                or value["experiment_contract_sha256"] != expected_hashes[f"cases/{case_id}/experiment_proposal_contract.json"]):
            raise ValueError("Exact conditional source authority/provenance required")
        approvals[branch] = deepcopy(value)
    body = {
        "schema_version": SCHEMA, "case_id": case_id, "execution_sha256": digest(execution),
        "execution": deepcopy(execution),
        "source_documents": {path: files[path].decode("utf-8") for path in paths},
        "source_provenance": provenance, "shared": shared, "case": case,
        "conditional_campaign_approval_sources": approvals,
        "mode": "STANDALONE_DESCRIPTOR_SIMULATION_ONLY",
        "readiness_rule": {
            "schema_version": "anvil.marketing-campaign-readiness.v1",
            "owner_decision_ref": "codex-owner-answer:call_88610dbfb6d049f98b86b31864b5de7a",
            "conditions": ["saved Policy Reviewer assessment for exact submitted versions",
                           "all mandatory findings resolved", "passing claims, rights, offer and campaign scope checks"],
            "candidate_flags_are_not_proof": True,
            "authority": "Separate conditional environment controller decision; not the readiness recommendation",
        },
        "campaign_authority_issued": False, "real_human_approval": False,
        "actual_media_generated": False, "qualification_granted": False,
    }
    if len(canonical(body)) > 16777216:
        raise ValueError("Bounded normalized service source required")
    return body


def with_services(world_body, files, execution):
    """Explicit operator source successor; no seed, persistence or qualification."""
    if type(world_body) is not dict or world_body.get("schema_version") != "anvil.marketing-private-world-definition.v1":
        raise ValueError("Explicit original world v1 source body required")
    value = deepcopy(world_body)
    services = normalize(value["case_id"], files, value["source_hashes"], execution)
    value.update(schema_version="anvil.marketing-private-world-definition.v2",
                 service_contract=services, service_contract_sha256=digest(services))
    for collection, path, public in public_sources(services):
        entries = value["records"][collection]
        matches = [r for r in entries if r["public"].get("id") == public["id"]]
        if any(r.get("outcome_binding") is not None for r in matches):
            raise ValueError("Baseline service source collides with a private conditional record")
        entries[:] = [r for r in entries if r["public"].get("id") != public["id"]]
        entries.append({"source_path": path, "source_sha256": value["source_hashes"][path],
                        "released_at": public.get("released_at", value["start"]),
                        "outcome_binding": None, "public": deepcopy(public)})
        value["public_columns"][collection] = sorted(set(value["public_columns"][collection]) | set(public))
    return value


def public_sources(services):
    """Only approved baseline case documents; no conditional decisions/outcomes."""
    case = services["case_id"]
    groups = [
        ("documents", f"cases/{case}/experiment_proposal_contract.json", [services["case"]["experiment_proposal_contract"]]),
        ("documents", f"cases/{case}/production_options.json", services["case"]["production_options"]),
        ("content", f"cases/{case}/approved_creative_catalogue.json", services["case"]["approved_creative_catalogue"]),
        ("claim-evidence", f"cases/{case}/claim_evidence.json", services["case"]["claim_evidence"]),
        ("task3-deliveries", f"cases/{case}/task3_delivery_fixtures.json",
         [r for r in services["case"]["task3_delivery_fixtures"] if r.get("locale") == "en-US"]),
        ("offers", "shared/offers.json", [r for r in services["shared"]["offers"] if r.get("market") == "US"]),
        ("policies", "shared/policies.json", services["shared"]["policies"]),
    ]
    creatives = {r["id"] for r in services["case"]["approved_creative_catalogue"]}
    groups.append(("operations", f"cases/{case}/approval_fixtures.json",
                   [r for r in services["case"]["approval_fixtures"] if r.get("target_id") in creatives
                    or r.get("authorisation_type") == "SPENDING_CEILING_NOT_OBLIGATION"]))
    for collection, path, rows in groups:
        for row in rows:
            yield collection, path, row
