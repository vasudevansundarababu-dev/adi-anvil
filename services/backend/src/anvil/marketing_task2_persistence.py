"""Explicit private controller serialization; never an actor/export projection."""

from copy import deepcopy
from uuid import UUID

from anvil.marketing_task2_contract import ROLES, VERSION
from anvil.marketing_task2_runtime import Task2Controller, timestamp
from anvil.praxis_generic_contract import canonical, digest

FIELDS = {
    "case_id": "case_id",
    "initial": "_initial",
    "start": "_start",
    "outcome": "_outcome",
    "budget_minor": "_budget",
    "generation": "generation",
    "trial_id": "trial_id",
    "role_tokens": "_tokens",
    "controller_token": "_controller_token",
    "clock": "_clock",
    "objects": "_objects",
    "controller_keys": "_controller_keys",
    "committed": "_committed",
    "settled": "_settled",
    "events": "_events",
    "transitions": "_transitions",
    "revisions": "_revisions",
    "audit": "audit",
    "history": "history",
}
PAIRS = {
    "role_idempotency": "_keys",
    "approval_bounds": "_approval_bounds",
    "approvals": "_approvals",
    "reservations": "_reservations",
}


def freeze(controller):
    value = {
        "schema_version": "anvil.marketing-controller-state.v1",
        "profile": VERSION,
        **{key: deepcopy(getattr(controller, attr)) for key, attr in FIELDS.items()},
        **{
            key: [
                {"key": list(k), "value": deepcopy(v)}
                for k, v in sorted(getattr(controller, attr).items())
            ]
            for key, attr in PAIRS.items()
        },
    }
    if len(canonical(value)) > 16 * 1024 * 1024:
        raise ValueError("Private controller state exceeds retained bound")
    return value, digest(value)


def restore(value, fingerprint):
    if (
        set(value) != {"schema_version", "profile", *FIELDS, *PAIRS}
        or value["schema_version"] != "anvil.marketing-controller-state.v1"
        or value["profile"] != VERSION
        or digest(value) != fingerprint
        or len(canonical(value)) > 16 * 1024 * 1024
    ):
        raise ValueError("Exact private controller checkpoint required")
    UUID(value["trial_id"])
    timestamp(value["clock"])
    if (
        set(value["role_tokens"]) != set(ROLES)
        or any(type(v) is not str or not 32 <= len(v) <= 200 for v in value["role_tokens"].values())
        or type(value["controller_token"]) is not str
        or len(value["controller_token"]) < 32
        or type(value["generation"]) is not int
        or value["generation"] < 0
    ):
        raise ValueError("Private controller identities or generation invalid")
    env = Task2Controller(
        value["case_id"],
        records=value["initial"],
        start=value["start"],
        outcome=value["outcome"],
        budget_minor=value["budget_minor"],
    )
    for key, attr in FIELDS.items():
        setattr(env, attr, deepcopy(value[key]))
    for key, attr in PAIRS.items():
        pairs = value[key]
        if not isinstance(pairs, list) or any(
            set(p) != {"key", "value"} or not isinstance(p["key"], list) or len(p["key"]) != 2
            for p in pairs
        ):
            raise ValueError("Explicit controller pair-map encoding required")
        result = {tuple(p["key"]): deepcopy(p["value"]) for p in pairs}
        if len(result) != len(pairs):
            raise ValueError("Duplicate private controller map key")
        setattr(env, attr, result)
    return env
