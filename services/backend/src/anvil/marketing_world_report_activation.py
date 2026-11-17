"""Pure report-state successor after an exact private controller decision.

The selected program must come from pinned private API normalization. Returning
this successor is not a persisted environment effect or runtime admission.
"""

from copy import deepcopy

from anvil.marketing_task2_persistence import freeze, restore
from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_world_authority import PREFIX
from anvil.praxis_generic_contract import canonical, digest


def prepare(controller, program):
    guards = [(key, value) for key, value in controller._controller_keys.items()
              if key.startswith(PREFIX) and ":" not in key[len(PREFIX):]]
    if len(guards) != 1:
        raise ValueError("One exact independent conditional controller decision required")
    slot, (fingerprint, proof) = guards[0]
    if (digest(proof) != fingerprint or proof.get("readiness", {}).get("ready") is not True
            or proof.get("episode_id") != controller.trial_id or proof.get("generation") != controller.generation
            or proof.get("branch") != controller._outcome or program.get("branch") != controller._outcome
            or program.get("case_id") != controller.case_id
            or program.get("schema_version") != "anvil.marketing-private-report-transition.v1"
            or not proof.get("selected_finance_book_sha256")):
        raise ValueError("Selected private report program and reconciled conditional finance required")
    request_ref = proof["request_ref"]
    request = controller._objects.get(request_ref["id"])
    if (request is None or digest(request) != request_ref["sha256"] or request.get("version") != request_ref["version"]
            or controller._approvals.get((request_ref["id"], request_ref["version"])) is not True):
        raise ValueError("Current exact independently approved request required")
    if "report_transition_sha256" in proof:
        raise ValueError("Selected report activation is one-use; no replay")
    baseline = {r["id"]: r for r in program["baseline"]}
    selected = {r["id"]: r for r in program["selected"]}
    if len(baseline) != len(program["baseline"]) or len(selected) != len(program["selected"]):
        raise ValueError("Distinct semantic report identities required")
    actual = controller._initial.get("reports", [])
    found = {}
    for entry in actual:
        key = entry["public"]["id"]
        if key in baseline:
            if (key in found or canonical(entry["public"]) != canonical(baseline[key])
                    or entry.get("outcome_binding") is not None or entry.get("actor_visible") is not True
                    or timestamp(entry["released_at"]) != timestamp(baseline[key]["released_at"])):
                raise ValueError("Actual original baseline reports must match exact pinned projection")
            found[key] = entry
        elif key in selected:
            raise ValueError("Selected report identity collides with another existing record")
    if set(found) != set(baseline):
        raise ValueError("Complete original baseline report projection required")
    now = timestamp(controller._clock)
    for key, entry in found.items():
        if timestamp(entry["released_at"]) <= now and selected.get(key) != baseline[key]:
            raise ValueError("Conditional activation cannot rewrite already released observations")
    before, fingerprint = freeze(controller)
    successor = restore(before, fingerprint)
    untouched = [deepcopy(entry) for entry in actual if entry["public"]["id"] not in baseline]
    for key, row in selected.items():
        if key in baseline and row == baseline[key]:
            untouched.append(deepcopy(found[key]))
        else:
            untouched.append({"actor_visible": True, "released_at": row["released_at"],
                              "outcome_binding": controller._outcome, "public": deepcopy(row)})
    successor._initial["reports"] = untouched
    updated = deepcopy(proof)
    updated.update(report_transition_sha256=digest(program), reports_activated_at=controller._clock)
    successor._controller_keys[slot] = (digest(updated), updated)
    return successor
