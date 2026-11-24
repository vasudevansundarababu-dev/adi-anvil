"""Fixes the RL Gym suggests for an evaluator configuration (D20 fix versions). A person still creates the version
(Admin → Evaluators → the configuration → Create fix version → "Use suggested fix"); it is then qualified by its
known-case tests plus the regression cases it carries, and Studio is told (evaluator.registered with the reason).

D-041: next_action only checked that an information request of the right *type* exists, never *whose* request it is,
so a minor-without-TIN episode that asks the adult for the minor's TIN scored full marks (E-007 KYC.REQUEST_PARTY).
The fix keeps the template's block and adds an RL Gym check (runner_version 2, `extra_blocks`): the request must go to
the party whose start-state record lacks the item.
"""

CASE = "kc-case-001"

REQUEST_PARTY = {
    "id": "next_action.request_party",
    "kind": "request_party",
    "name": "Request goes to the party missing the item",
    "on_fail": "STATE_MUTATION_ERROR",
}


def _start(minor_tin="missing"):
    return {
        "applications": [{"application_id": CASE, "submitted_at": "2026-11-01T09:00:00Z"}],
        "parties": [
            {"party_id": "p-adult", "application_id": CASE, "role": "primary"},
            {"party_id": "p-minor", "application_id": CASE, "role": "minor"},
        ],
        "documents": [
            {
                "document_id": "d-1",
                "party_id": "p-adult",
                "kind": "government_id",
                "content": {"tin": "123-45-6789"},
            },
            {
                "document_id": "d-2",
                "party_id": "p-minor",
                "kind": "birth_certificate",
                "content": {"tin": minor_tin},
            },
        ],
        "information_requests": [],
    }


def _case(name, request_party, expect, *, start=True, block=None):
    end = {
        **_start(),
        "information_requests": [{"request_id": "r-1", "type": "tin", "party_id": request_party}],
    }
    case = {
        "name": name,
        "case_id": CASE,
        "evidence": {"snapshots": {"start": _start() if start else None, "end": end}},
        "reference": {"request_type": "tin"},
        "expect": expect,
    }
    if block:
        case["expect_block"] = block
        case["expect_on_fail"] = REQUEST_PARTY["on_fail"]
    return case


def request_party_regressions():
    """The D-041 regression fixtures: a minor without a TIN, the request sent to the right party, to the wrong party
    (the adult: the bug), and with no start state to tell them apart."""
    return [
        _case("d041_minor_tin_requested_from_minor", "p-minor", "pass"),
        _case("d041_minor_tin_requested_from_adult", "p-adult", "fail", block=REQUEST_PARTY["id"]),
        _case("d041_no_start_state", "p-minor", "blocked", start=False),
    ]


SUGGESTED = {
    "golden-kyc-blocks:next_action": {
        "defect": "D-041",
        "reason": (
            "D-041: next_action checked only the request type, never whose request it is; the request must go to the "
            "party whose record lacks the item (E-007 KYC.REQUEST_PARTY)"
        ),
        "source": "rlgym:D-041",
        "config": {
            "runner": "verifier_blocks",
            "runner_version": 2,
            "evidence": "snapshots",
            "extra_blocks": [REQUEST_PARTY],
            "regression_cases": request_party_regressions(),
        },
    }
}


def suggested(cid, config):
    """The suggested fix for this configuration, unless its configuration already is that fix."""
    fix = SUGGESTED.get(cid)
    if not fix or (config or {}).get("extra_blocks") == fix["config"]["extra_blocks"]:
        return None
    return fix
