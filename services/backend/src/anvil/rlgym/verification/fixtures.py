"""E-007 §3.12: the four KYC regression fixtures. Each is a synthetic episode (start and end state, tool log) with the
case's reference answers. Their expected outcomes are drafts until an SME confirms them ("awaiting SME"); the report
shows each with what the independent assertions say and what next_action's grader versions say, so the phase 1 exit
test is visible: the Minor wrong-party fixture is a MISMATCH under next_action v1 (grader pass, assertion fail).
"""

CASE = "fx-case-001"


def _start(parties, docs, submitted="2026-11-01T09:00:00Z"):
    return {
        "applications": [{"application_id": CASE, "submitted_at": submitted}],
        "parties": [{"application_id": CASE, **p} for p in parties],
        "documents": docs,
        "findings": [],
        "recommendations": [],
        "information_requests": [],
        "referrals": [],
    }


def _checked(parties):
    return [
        {"tool": t, "args": {"party_id": p["party_id"]}, "ok": True}
        for p in parties
        for t in ("identity.check", "screening.check")
    ] + [{"tool": "recommend", "args": {}, "ok": True}]


MINOR = [{"party_id": "p-adult", "role": "primary"}, {"party_id": "p-minor", "role": "minor"}]
MINOR_DOCS = [
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
        "content": {"tin": "missing"},
    },
]
JOINT = [{"party_id": "p-a", "role": "primary"}, {"party_id": "p-b", "role": "joint"}]
EXPIRED_DOCS = [
    {
        "document_id": "d-a",
        "party_id": "p-a",
        "kind": "government_id",
        "content": {"expires_on": "2028-01-01"},
    },
    {
        "document_id": "d-b",
        "party_id": "p-b",
        "kind": "government_id",
        "content": {"expires_on": "2026-09-30"},
    },
]
SOLO = [{"party_id": "p-s", "role": "primary"}]
PASSPORT_DOCS = [{"document_id": "d-s", "party_id": "p-s", "kind": "passport", "content": {}}]


def _fixture(fid, title, parties, docs, ref, end_extra, expect, shows):
    start = _start(parties, docs)
    end = {**start, **end_extra}
    return {
        "id": fid,
        "title": title,
        "bundle": {
            "case_id": CASE,
            "tool_events": _checked(parties),
            "snapshots": {"start": start, "end": end},
        },
        "reference": ref,
        "expect": expect,
        "shows": shows,
    }


FIXTURES = [
    _fixture(
        "FX-1",
        "Minor without a TIN: the TIN is requested from the adult (wrong party)",
        MINOR,
        MINOR_DOCS,
        {"recommendation": "request_information", "request_type": "tin", "referral": "none"},
        {
            "recommendations": [
                {"recommendation": "request_information", "rationale": "TIN missing"}
            ],
            "information_requests": [{"type": "tin", "party_id": "p-adult"}],
        },
        {"KYC.REQUEST_PARTY": "FAIL"},
        "MISMATCH under next_action v1 (grader pass, assertion fail); v2 (D-041) agrees with the assertion",
    ),
    _fixture(
        "FX-2",
        "Sanctions name match: referred to sanctions with the analyst review still open",
        SOLO,
        PASSPORT_DOCS,
        {"recommendation": "specialist_review", "request_type": "none", "referral": "sanctions"},
        {
            "recommendations": [
                {"recommendation": "specialist_review", "rationale": "possible match"}
            ],
            "referrals": [{"specialty": "sanctions"}],
        },
        {"KYC.RECOMMENDATION": "PASS", "KYC.REFERRAL": "PASS"},
        "the referral is made and the case is held for review",
    ),
    _fixture(
        "FX-3",
        "Joint applicant's ID expired before submission: a new ID is requested from that applicant",
        JOINT,
        EXPIRED_DOCS,
        {
            "recommendation": "request_information",
            "request_type": "id_document",
            "referral": "none",
        },
        {
            "recommendations": [
                {"recommendation": "request_information", "rationale": "ID expired"}
            ],
            "information_requests": [{"type": "id_document", "party_id": "p-b"}],
        },
        {"KYC.REQUEST_PARTY": "PASS"},
        "the request names the party whose ID expired",
    ),
    _fixture(
        "FX-4",
        "Passport only: proof of address is requested",
        SOLO,
        PASSPORT_DOCS,
        {
            "recommendation": "request_information",
            "request_type": "proof_of_address",
            "referral": "none",
        },
        {
            "recommendations": [
                {"recommendation": "request_information", "rationale": "no proof of address"}
            ],
            "information_requests": [{"type": "proof_of_address", "party_id": "p-s"}],
        },
        {"KYC.REQUEST_PARTY": "PASS"},
        "proof of address is requested from the only applicant",
    ),
]


def assert_fixture(f):
    from anvil.rlgym.verification import assertions

    return assertions.run_all(f["bundle"], f["reference"])


def grader_next_action(f, config):
    """next_action's verdict on a fixture under a configuration (v1: the template block only; v2: D-041)."""
    from anvil.rlgym.scoring import sandbox_runner as runner

    block = {
        "id": "next_action.request",
        "op": "exists_where",
        "row": "any",
        "kind": "state",
        "table": "information_requests",
        "column": "type",
        "value": {"case_reference": "reference_answers.request_type"},
        "on_fail": "STATE_MUTATION_ERROR",
    }
    out = runner.run_blocks(
        {
            "config": config,
            "blocks": [block],
            "case_id": CASE,
            "evidence": {"snapshots": f["bundle"]["snapshots"]},
            "reference": f["reference"],
            "expected_values_from": "case_reference",
        }
    )
    return out["verdict"]
