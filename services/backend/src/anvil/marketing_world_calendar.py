"""Explicit operator proposal for twelve source-backed report-review windows.

Campaign business dates stay unchanged. An episode opens when its first weekly
report is available; the fifth review also includes the pre-order approval
event. This is a source proposal, never an applied environment or admission.
"""

from copy import deepcopy

from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_world_outcome_data import _read
from anvil.praxis_generic_contract import digest


def propose(case_id, files, pins, service_contract):
    path = f"cases/{case_id}/weekly_reports.jsonl"
    rows = _read(path, files, pins)
    if (case_id not in {"GT2-R01", "GT2-R02"} or service_contract.get("case_id") != case_id
            or {r.get("week") for r in rows} != set(range(1, 13))):
        raise ValueError("Complete twelve-week source reports for the exact case required")
    clocks = [max(timestamp(r["released_at"]) for r in rows if r["week"] == week) for week in range(1, 13)]
    if any(a >= b for a, b in zip(clocks, clocks[1:])):
        raise ValueError("Distinct ordered original weekly release times required")
    conditional = service_contract["conditional_campaign_approval_sources"]
    issued = {timestamp(conditional[branch]["issued_at_if_selected"]) for branch in ("positive", "null", "negative")}
    if len(issued) != 1:
        raise ValueError("Private outcomes cannot choose different public observation clocks")
    issue = next(iter(issued))
    first_order = timestamp(service_contract["case"]["experiment_proposal_contract"]["start"] + "T00:00:00Z")
    eligible = [index for index, clock in enumerate(clocks) if clock < first_order]
    if not eligible or issue >= first_order:
        raise ValueError("No report review can include a non-retroactive approval event")
    index = eligible[-1]
    clocks[index] = max(clocks[index], issue)
    if any(a >= b for a, b in zip(clocks, clocks[1:])) or not issue <= clocks[index] < first_order:
        raise ValueError("Twelve source-backed review slots conflict with conditional approval timing")
    return {"schema_version": "anvil.marketing-operator-observation-program.v1", "case_id": case_id,
            "observation_count": 12, "campaign_source_dates_changed": False,
            "episode_observation_start": clocks[0].isoformat(),
            "windows": [{"week": week, "instant": clock.isoformat(),
                         "source_paths": [path, f"cases/{case_id}/experiment_proposal_contract.json"]}
                        for week, clock in enumerate(clocks, 1)],
            "source_provenance": {path: pins[path]}, "service_contract_sha256": digest(service_contract),
            "approval_observation": index + 1, "applied": False, "qualified": False}


def with_program(world, program):
    """Explicit operator-only source transformation; never called implicitly."""
    if (world.get("case_id") != program.get("case_id") or program.get("observation_count") != 12
            or program.get("applied") is not False or program.get("qualified") is not False
            or len(world.get("windows", [])) != 12
            or world.get("service_contract_sha256") != program.get("service_contract_sha256")):
        raise ValueError("Exact unapplied operator calendar proposal and source required")
    value = deepcopy(world)
    value["start"] = program["episode_observation_start"]
    for previous, selected in zip(value["windows"], program["windows"]):
        previous.update(instant=selected["instant"], source_paths=deepcopy(selected["source_paths"]))
    return value
