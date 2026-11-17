"""Private effect-state projection; no future records, role tokens or controls."""

from copy import deepcopy

FIELDS = (
    "clock",
    "objects",
    "budget_minor",
    "committed",
    "settled",
    "reservations",
    "approvals",
    "approval_bounds",
    "revisions",
    "transitions",
)


def effect_view(state):
    return {
        "schema_version": "anvil.marketing-tool-post-state.v1",
        **{key: deepcopy(state[key]) for key in FIELDS},
    }
