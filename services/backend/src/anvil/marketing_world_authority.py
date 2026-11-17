"""Prepare a private conditional-controller successor, never persist on its own.

Only the API may commit this successor with its already admitted workflow
intent and original state compare-and-swap. Calling this function or obtaining
its public proposal is not durable campaign authority or runtime qualification.
"""

from copy import deepcopy

from anvil.marketing_task2_persistence import freeze, restore
from anvil.marketing_world_finance import SCHEMA as FINANCE_SCHEMA
from anvil.marketing_world_finance import reservation_capacity
from anvil.marketing_world_readiness import CampaignRequest, assess
from anvil.praxis_generic_contract import digest

PREFIX = "anvil-private:marketing-conditional-authority:"


def prepare(controller, execution, node, inputs, sources, finance_book):
    """Inputs are private API-normalized sources; never accept a worker book.

    Returns an isolated successor plus public response and private proof.
    The original controller is untouched, including on every denial.
    """
    report = assess(controller, execution, node, inputs, sources)
    public = {"schema_version": "anvil.marketing-conditional-controller-response.v1",
              "request_ref": deepcopy(report["request_ref"]), "decision": "pending",
              "source_contract_sha256": digest(sources),
              "campaign_authority_issued": False, "simulation_only": True,
              "real_human_approval": False, "additional_media_budget": 0}
    private = {"readiness": deepcopy(report), "persisted": False}
    if not report["ready"]:
        return None, public, private
    request_ref = report["request_ref"]
    request = CampaignRequest.model_validate(controller._objects[request_ref["id"]]["content"])
    contract = sources["case"]["experiment_proposal_contract"]
    slot = PREFIX + digest({"case_id": controller.case_id, "experiment": request.experiment_contract_ref.model_dump()})
    if slot in controller._controller_keys:
        raise ValueError("This experiment already has a conditional decision; no alias, revision or replay")
    if (finance_book.get("schema_version") != FINANCE_SCHEMA or finance_book.get("case_id") != controller.case_id
            or finance_book.get("ceiling") != controller._budget):
        raise ValueError("Exact private source-normalized campaign finance required")
    if (controller._approvals or controller._approval_bounds or controller._reservations
            or controller._committed != 0 or controller._settled != 0):
        raise ValueError("Unreconciled controller finance or prior authority; qualification required")
    capacity = reservation_capacity(finance_book, controller._clock, request.planned_cap_usd_minor)
    conditional = sources["conditional_campaign_approval_sources"][controller._outcome]
    if (conditional.get("issuer") != "environment_fixture" or conditional.get("real_human_decision") is not False
            or conditional.get("experiment_id") != contract["id"]
            or conditional.get("decision") != "APPROVED_IF_VALID_REQUEST_SELECTS_THIS_BRANCH"):
        raise ValueError("Independent conditional simulated-controller source required")
    source_path = f"reviewer_only/us-pair/{controller.case_id}/reuse-test-{controller._outcome}/conditional_campaign_approval.json"
    provenance = sources["source_provenance"][source_path]
    before, fingerprint = freeze(controller)
    successor = restore(before, fingerprint)
    # Existing parent obligations are hydrated once. Locked contingency is
    # checked by reservation_capacity, separately from the campaign ceiling.
    successor._committed = capacity["committed"]
    successor._settled = capacity["settled"]
    credential = successor.controller_credential()
    body = {"request_id": request_ref["id"], "version": request_ref["version"],
            "approved": True, "amount_bound": request.planned_cap_usd_minor}
    successor.control(credential, successor.generation, "decide", body, idempotency_key=slot + ":decision")
    successor.control(credential, successor.generation, "reserve",
                      {"request_id": request_ref["id"], "version": request_ref["version"],
                       "amount": request.planned_cap_usd_minor}, idempotency_key=slot + ":reserve")
    private.update({"branch": controller._outcome, "conditional_source_sha256": provenance["sha256"],
                    "source_contract_sha256": digest(sources), "finance": capacity,
                    "request_ref": deepcopy(request_ref), "experiment_ref": request.experiment_ref.model_dump(),
                    "episode_id": controller.trial_id, "generation": controller.generation,
                    "before_state_sha256": fingerprint, "issued_at": controller._clock})
    successor._controller_keys[slot] = (digest(private), deepcopy(private))
    public.update(decision="approved", campaign_authority_issued=True,
                  amount_bound_minor=request.planned_cap_usd_minor,
                  decision_ref="simulated-campaign-decision:" + digest({"episode_id": controller.trial_id,
                                                                           "generation": controller.generation,
                                                                           "request_ref": request_ref}),
                  scope=request.scope.model_dump())
    return successor, public, private
