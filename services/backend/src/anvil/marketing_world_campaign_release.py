"""Advance already activated finance only; never activate by passage of time."""

from anvil.marketing_world_activation_definition import ActivationWorldDefinition
from anvil.marketing_world_authority import PREFIX
from anvil.marketing_world_finance_transition import prepare as prepare_finance
from anvil.marketing_world_financial_records import current_observation
from anvil.marketing_world_opening_definition import OpeningWorldDefinition
from anvil.marketing_world_population_definition import PopulationWorldDefinition
from anvil.praxis_generic_contract import canonical, digest


def prepare(controller, world, instant):
    guards = [key for key in controller._controller_keys if key.startswith(PREFIX) and ":" not in key[len(PREFIX):]]
    if not guards:
        return None
    if type(world) not in (ActivationWorldDefinition, OpeningWorldDefinition, PopulationWorldDefinition) or len(guards) != 1:
        raise ValueError("Exact original independently activated private world required")
    slot = guards[0]
    sha, proof = controller._controller_keys[slot]
    if (digest(proof) != sha or not proof.get("report_transition_sha256")
            or proof.get("activation_world_sha256") != digest(world.model_dump(mode="json"))):
        raise ValueError("Complete prior decision/data/finance activation required")
    selected, _ = world.selected_programs(controller._outcome)
    old = current_observation(controller, selected, proof)
    entries = controller._initial.get("budget-snapshots", [])
    matches = [r for r in entries if r["public"]["id"] == old["id"]]
    if (len(matches) != 1 or matches[0].get("actor_visible") is not True or matches[0].get("outcome_binding") is not None
            or canonical(matches[0]["public"]) != canonical(old)):
        raise ValueError("Actual prior current balance must match reconciled controller finance")
    successor = prepare_finance(controller, world.finance_book, selected, instant)
    updated_proof = successor._controller_keys[slot][1]
    new = current_observation(successor, selected, updated_proof)
    for row in successor._initial["budget-snapshots"]:
        if row["public"]["id"] == old["id"]:
            row.update(released_at=successor._clock, public=new)
    updated_proof["current_finance_observation_sha256"] = digest(new)
    successor._controller_keys[slot] = (digest(updated_proof), updated_proof)
    return successor
