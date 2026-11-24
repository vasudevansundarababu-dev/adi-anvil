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


# D-042: screening and identity checks ordered "before recommend" passed in episodes where the agent never recommended
# (E-007 phase 1 on run-0228: 5 MISMATCH). The fix adds an RL Gym check: the agent must have recommended.
RECOMMENDED = {
    "id": "recommended",
    "kind": "recommended",
    "name": "The agent made a recommendation",
    "on_fail": "MISSING_PRECONDITION",
}


def _recommend_cases(prefix, events_before, end_extra=None, reference=None):
    reference = reference or {}
    end_extra = end_extra or {}
    rec_end = {**end_extra, "recommendations": [{"recommendation": "request_information"}]}

    def case(name, events, end, expect, block=None):
        c = {
            "name": f"{prefix}_{name}",
            "case_id": CASE,
            "evidence": {"tool_events": events, "snapshots": {"start": {}, "end": end}},
            "reference": reference,
            "expect": expect,
        }
        if block:
            c["expect_block"] = RECOMMENDED["id"]
            c["expect_on_fail"] = RECOMMENDED["on_fail"]
        return c

    rec = [{"tool": "recommend", "args": {}, "ok": True}]
    return [
        case("checked_then_recommended", events_before + rec, rec_end, "pass"),
        case("checked_never_recommended", events_before, dict(end_extra), "fail", block=True),
    ]


def _v2(extra, regressions):
    return {
        "runner": "verifier_blocks",
        "runner_version": 2,
        "evidence": "snapshots",
        "extra_blocks": [extra],
        "regression_cases": regressions,
    }


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


SUGGESTED["golden-kyc-blocks:screening"] = {
    "defect": "D-042",
    "reason": "D-042: screening passed in episodes where the agent never recommended; it now needs a recommendation",
    "source": "rlgym:D-042",
    "config": _v2(
        RECOMMENDED,
        _recommend_cases(
            "d042_screening",
            [
                {"tool": "application.read", "args": {}, "ok": True},
                {"tool": "screening.check", "args": {"party_id": "p-1"}, "ok": True},
            ],
            {"referrals": [{"specialty": "sanctions"}]},
            {"referral": "sanctions"},
        ),
    ),
}
SUGGESTED["golden-kyc-blocks:identification_verification"] = {
    "defect": "D-042",
    "reason": (
        "D-042: identification_verification passed in episodes where the agent never recommended; it now needs a "
        "recommendation"
    ),
    "source": "rlgym:D-042",
    "config": _v2(
        RECOMMENDED,
        _recommend_cases(
            "d042_identity", [{"tool": "identity.check", "args": {"party_id": "p-1"}, "ok": True}]
        ),
    ),
}


def suggested(cid, config):
    """The suggested fix for this configuration, unless its configuration already is that fix."""
    fix = SUGGESTED.get(cid)
    if not fix or (config or {}).get("extra_blocks") == fix["config"]["extra_blocks"]:
        return None
    return fix
