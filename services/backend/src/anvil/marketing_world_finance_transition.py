"""Private selected-branch accounting successor, without extra component costs.

These pure proposals are not API commits or branch-report activation. The API
must persist the complete selected data/finance transition atomically before
returning its actual environment receipt. Original objects stay untouched.
"""

from copy import deepcopy

from anvil.marketing_task2_persistence import freeze, restore
from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_world_authority import PREFIX
from anvil.marketing_world_finance import position
from anvil.praxis_generic_contract import canonical, digest


def validate_transition(baseline, selected):
    if (baseline["case_id"] != selected["case_id"] or baseline["ceiling"] != selected["ceiling"]
            or baseline["locked_contingency"] != selected["locked_contingency"]
            or canonical(baseline["envelopes"]) != canonical(selected["envelopes"])
            or "reservation_events" in baseline or "reservation_events" not in selected):
        raise ValueError("Exact original envelope and conditional component schedule required")
    original = {r["id"]: r for r in baseline["commitments"]}
    changed = {r["id"]: r for r in selected["commitments"]}
    if original.keys() != changed.keys():
        raise ValueError("A conditional experiment cannot add another parent order")
    permitted = set()
    for key, row in original.items():
        other = changed[key]
        if row.get("locale") == "en-US" and row.get("channel") == "search" and row.get("week") in (7, 8):
            if ({k: v for k, v in other.items() if k not in {"committed_minor", "additional_campaign_approval_ref"}}
                    != {k: v for k, v in row.items() if k != "committed_minor"}):
                raise ValueError("Conditional funding changed parent order scope, date or terms")
            permitted.add(key)
        elif other != row:
            raise ValueError("Conditional funding changed another market, week or global cost")
    previous = {r["id"]: r for r in baseline["ledger"]}
    following = {r["id"]: r for r in selected["ledger"]}
    if previous.keys() != following.keys():
        raise ValueError("A conditional experiment cannot add a second parent settlement")
    for key, row in previous.items():
        other = following[key]
        if row["commitment_id"] in permitted:
            if ({k: v for k, v in other.items() if k != "amount_minor"}
                    != {k: v for k, v in row.items() if k != "amount_minor"}):
                raise ValueError("Conditional funding changed parent settlement identity or date")
        elif other != row:
            raise ValueError("Conditional funding changed another cost's settlement")


def prepare(controller, baseline, selected, instant):
    """Select only the private controller's pre-bound branch, never actor input."""
    validate_transition(baseline, selected)
    if timestamp(instant) < timestamp(controller._clock):
        raise ValueError("Selected accounting cannot rewrite an earlier observation window")
    guards = [(key, value) for key, value in controller._controller_keys.items() if key.startswith(PREFIX) and ":" not in key[len(PREFIX):]]
    if len(guards) != 1:
        raise ValueError("Exactly one independent conditional-controller decision required")
    slot, (proof_hash, proof) = guards[0]
    if (digest(proof) != proof_hash or proof.get("branch") != controller._outcome
            or proof.get("episode_id") != controller.trial_id or proof.get("generation") != controller.generation
            or proof.get("readiness", {}).get("ready") is not True
            or proof.get("finance", {}).get("finance_book_sha256") != digest(baseline)):
        raise ValueError("Actual private decision and original parent book required")
    prefix = f"reviewer_only/us-pair/{controller.case_id}/reuse-test-{controller._outcome}/"
    if any(not path.startswith(prefix) for path in selected["source_provenance"]):
        raise ValueError("Another private outcome cannot supply accounting")
    request = proof["request_ref"]
    current = controller._objects.get(request["id"])
    if (current is None or current["version"] != request["version"] or digest(current) != request["sha256"]
            or controller._approvals.get((request["id"], request["version"])) is not True):
        raise ValueError("Current exact approved request required before accounting advances")
    prior = proof.get("selected_finance_position", proof["finance"])
    if (controller._settled != prior["settled"] or controller._committed != prior["committed"]
            or controller._reservations != {(request["id"], request["version"]): prior["reserved"]}):
        raise ValueError("Unreconciled controller obligations must not be overwritten")
    selected_hash = digest(selected)
    if proof.get("selected_finance_book_sha256", selected_hash) != selected_hash:
        raise ValueError("Selected parent accounting is immutable after activation")
    at_issue = position(selected, proof["issued_at"])
    if any(at_issue[name] != proof["finance"][name] for name in ("settled", "committed", "reserved")):
        raise ValueError("Conditional accounting would change pre-existing issuance obligations")
    current = position(selected, instant)
    original, fingerprint = freeze(controller)
    successor = restore(original, fingerprint)
    successor.advance(instant)
    successor._committed = current["committed"]
    successor._settled = current["settled"]
    successor._reservations[(request["id"], request["version"])] = current["reserved"]
    updated = deepcopy(proof)
    updated.update(selected_finance_book_sha256=selected_hash, selected_finance_position=current)
    successor._controller_keys[slot] = (digest(updated), updated)
    return successor
