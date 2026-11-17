"""Source-derived ledger/budget projection, separate from spending authority."""

from copy import deepcopy

from anvil.dataset_export_contract import json_object
from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_world_finance import position
from anvil.praxis_generic_contract import canonical, digest

COLLECTIONS = {"ledger.jsonl": "ledger", "budget_snapshots.json": "budget-snapshots", "budget_envelopes.json": "budget-envelopes"}


def records(documents, prefix):
    for name, collection in COLLECTIONS.items():
        path = prefix + "/" + name
        raw = documents[path]
        if type(raw) is str:
            raw = raw.encode("utf-8")
        rows = ([json_object(line) for line in raw.splitlines()] if name.endswith("jsonl")
                else json_object(b'{"value":' + raw + b'}')["value"])
        for row in rows:
            yield collection, path, row


def prepare_projection(controller, baseline_documents, selected_documents, selected_book, proof):
    """Private producer only, after exact source normalization and decision.

    Preserve historical snapshots already released; add a distinct calculated
    current controller observation rather than rewriting their original IDs.
    """
    case = controller.case_id
    original = {collection: {} for collection in COLLECTIONS.values()}
    replacement = {collection: {} for collection in COLLECTIONS.values()}
    for collection, _, row in records(baseline_documents, f"cases/{case}"):
        original[collection][row["id"]] = row
    prefix = f"reviewer_only/us-pair/{case}/reuse-test-{controller._outcome}"
    for collection, _, row in records(selected_documents, prefix):
        replacement[collection][row["id"]] = row
    now = timestamp(controller._clock)
    result = {}
    for collection, baseline in original.items():
        if set(baseline) != set(replacement[collection]):
            raise ValueError("Complete original financial public identities required")
        actual = controller._initial.get(collection, [])
        by_id = {r["public"]["id"]: r for r in actual}
        if len(by_id) != len(actual) or set(by_id) != set(baseline):
            raise ValueError("Actual complete baseline financial projection required")
        rows = []
        for key, row in baseline.items():
            existing = by_id[key]
            if (canonical(existing["public"]) != canonical(row) or existing.get("actor_visible") is not True
                    or existing.get("outcome_binding") is not None
                    or timestamp(existing["released_at"]) != timestamp(row["released_at"])):
                raise ValueError("Actual baseline financial source differs")
            new = replacement[collection][key]
            if row == new or timestamp(existing["released_at"]) <= now:
                if collection != "budget-snapshots" and row != new and timestamp(existing["released_at"]) <= now:
                    raise ValueError("Conditional funding cannot rewrite released financial evidence")
                rows.append(deepcopy(existing))
            else:
                if new["released_at"] != row["released_at"]:
                    raise ValueError("Conditional funding cannot change financial publication time")
                rows.append({"actor_visible": True, "outcome_binding": controller._outcome,
                             "released_at": new["released_at"], "public": deepcopy(new)})
        result[collection] = rows
    current = current_observation(controller, selected_book, proof)
    result["budget-snapshots"].append({"actor_visible": True, "outcome_binding": None,
                                       "released_at": controller._clock, "public": current})
    return result


def current_observation(controller, selected_book, proof):
    """A mutable current balance is distinct from historical source snapshots."""
    value = position(selected_book, controller._clock)
    if (controller._settled != value["settled"] or controller._committed != value["committed"]
            or sum(controller._reservations.values()) != value["reserved"]):
        raise ValueError("Current controller and selected financial projection disagree")
    current = {"id": "anvil-current-campaign-balance:" + digest({"episode_id": controller.trial_id,
                                                                 "generation": controller.generation}),
               "as_of": controller._clock, "released_at": controller._clock,
               "actual_settled_usd_minor": value["settled"], "binding_outstanding_usd_minor": value["committed"],
               "active_reservations_usd_minor": value["reserved"], "campaign_authority_usd_minor": selected_book["ceiling"],
               "contingency_locked_usd_minor": value["locked_contingency"],
               "media_remaining_authorisable_usd_minor": value["spendable_before_reservations"],
               "approval_request_ref": deepcopy(proof["request_ref"]), "simulation_only": True,
               "provenance": "CURRENT_SOURCE_RECONCILED_SIMULATED_CONTROLLER_ACCOUNTING"}
    return current
