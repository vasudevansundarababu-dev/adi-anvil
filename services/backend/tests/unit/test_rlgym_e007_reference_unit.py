"""E-007 §7.2, V-04, V-01: the reference agent follows S5 with the reference answers through the offered tools; every
place it can't is a named failure; V-04/V-01 rows read the latest reference run. Synthetic; no Docker, no model."""

from anvil.rlgym.verification import reference
from anvil.rlgym.verification import service as verification


def actor(tools, steps):
    return {"sections": {"S3": {"tools": tools}, "S5": {"steps": steps}}}


ALL = [
    "application.read",
    "parties.list",
    "documents.list",
    "document.read",
    "identity.check",
    "information.request",
    "finding.write",
    "recommend",
]
STEPS = [
    {"tool": "application.read"},
    {"tool": "documents.list"},
    {"tool": "document.read"},
    {
        "tool": "identity.check",
        "followUps": [
            {"if": "the ID is expired", "tools": ["finding.write", "information.request"]}
        ],
    },
    {"tool": "recommend"},
]
REF = {
    "recommendation": "request_information",
    "request_type": "id_document",
    "referral": "none",
    "screening_issue": "none",
    "reason_keyword": "expired",
}


class Env:
    """A tiny fake environment: one application with two parties; party b's ID expired before submission."""

    def __call__(self, action):
        t, a = action["tool"], action.get("args") or {}
        recs = {
            "application.read": [
                {"application_id": "APP", "revision": 2, "submitted_at": "2026-11-01"}
            ],
            "parties.list": [
                {"party_id": "a", "role": "primary"},
                {"party_id": "b", "role": "joint"},
            ],
            "documents.list": [
                {
                    "document_id": f"{a.get('party_id')}-id",
                    "party_id": a.get("party_id"),
                    "kind": "government_id",
                    "content": {
                        "expires_on": "2026-09-01" if a.get("party_id") == "b" else "2030-01-01"
                    },
                }
            ],
        }.get(t)
        return {
            "ok": True,
            "state": "completed",
            "output": {"records": recs} if recs is not None else {},
        }


def drive(act, ref=REF):
    failures, calls = [], []
    gen = reference.agent(
        act,
        ref,
        "APP",
        failures,
        operations=[
            {
                "operation_id": "recommend",
                "input_schema": {"properties": {"policy_bundle": {"const": "golden-kyc-1.0.0"}}},
            }
        ],
    )
    action, env = next(gen), Env()
    while "final" not in action:
        calls.append(action)
        action = gen.send(env(action))
    return calls, failures


def test_follows_s5_and_requests_from_the_party_who_lacks_the_item():
    calls, failures = drive(actor(ALL, STEPS))
    assert not failures
    req = next(c for c in calls if c["tool"] == "information.request")
    assert req["args"]["party_id"] == "b" and req["args"]["type"] == "id_document"
    rec = calls[-1]
    assert rec["tool"] == "recommend" and rec["args"]["decision"] == "request_information"
    assert (
        rec["args"]["policy_bundle"] == "golden-kyc-1.0.0" and rec["args"]["assessed_revision"] == 2
    )
    assert (
        "screening"
        not in next(c for c in calls if c["tool"] == "finding.write")["args"]["issue"].lower()
    )


def test_a_tool_s3_does_not_offer_is_a_named_failure():
    _, failures = drive(actor([t for t in ALL if t != "recommend"], STEPS))
    assert any(f["reason"] == "S5 step 5 uses recommend, which S3 does not offer" for f in failures)


def test_no_way_to_find_parties_is_a_named_failure():
    _, failures = drive(actor([t for t in ALL if t != "parties.list"], STEPS))
    assert any("no offered tool lists parties" in f["reason"] for f in failures)


def test_summary_is_plain_and_bound_to_the_steps():
    a = reference.summary(actor(ALL, STEPS))
    assert (
        "S5 step 4: Run identity.check for each party" in a["text"]
        and "then: If the case needs information" in a["text"]
    )
    b = reference.summary(actor(ALL, STEPS[:-1]))
    assert a["sha256"] != b["sha256"]  # a changed task needs a new confirmation


def _rr(confirmed=True, full=True, replay=True, failures=()):
    return {
        "id": "rr-1",
        "created_at": "x",
        "judge": "mock",
        "tasks": [
            {
                "task_id": "t1",
                "revision": 1,
                "confirmed": {"verdict": "confirmed"} if confirmed else None,
                "cases": [
                    {
                        "case_id": "c1",
                        "points": "25/25" if full else "20/25",
                        "full_marks": full,
                        "failures": [{"reason": r} for r in failures],
                        "verdicts": {} if full else {"next_action": {"verdict": "fail"}},
                        "replay": {
                            "observations_match": replay,
                            "end_state_match": True,
                            "verdicts_match": True,
                            "first_different_step": None if replay else 4,
                        },
                    }
                ],
            }
        ],
    }


def rows(monkeypatch, rr):
    from anvil.rlgym.verification import reference_run

    monkeypatch.setattr(reference_run, "latest", lambda c, ws, sv: rr)
    return verification.reference_rows(
        None, "ws", {"suite_version_id": "sv"}, {"tasks": [{"task_id": "t1", "revision": 1}]}
    )


def test_v04_v01_rows(monkeypatch):
    v04, v01 = rows(monkeypatch, _rr())
    assert (v04["outcome"], v01["outcome"]) == ("PASS", "PASS")
    v04, _ = rows(monkeypatch, _rr(confirmed=False))
    assert (
        v04["outcome"] == "INSUFFICIENT_EVIDENCE"
        and "reference approach not confirmed" in v04["detail"]
    )
    v04, _ = rows(
        monkeypatch,
        _rr(full=False, failures=["S5 step 15 uses recommend, which S3 does not offer"]),
    )
    assert v04["outcome"] == "FAIL" and "S5 step 15 uses recommend" in v04["detail"]
    _, v01 = rows(monkeypatch, _rr(replay=False))
    assert v01["outcome"] == "FAIL"
    v04, v01 = rows(monkeypatch, None)
    assert v04["outcome"] == v01["outcome"] == "INSUFFICIENT_EVIDENCE"
