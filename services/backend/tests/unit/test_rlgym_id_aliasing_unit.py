"""Owner decision 24 Nov 2026 (D-039): the agent sees opaque IDs. Synthetic @8-shaped data; no Docker, no model."""

import inspect
import json

from anvil.rlgym.catalog import fixes
from anvil.rlgym.runs import aliasing, worker
from anvil.rlgym.scoring import sandbox_runner as runner

CASE = "kyc-teen-joint-minor-without-tin-001"
OTHER = "kyc-individual-passport-only-003"
START = {
    "applications": [{"application_id": CASE}, {"application_id": OTHER}],
    "parties": [
        {"party_id": f"{CASE}-p1", "application_id": CASE, "role": "primary"},
        {"party_id": f"{CASE}-p2", "application_id": CASE, "role": "minor"},
        {"party_id": f"{OTHER}-p1", "application_id": OTHER, "role": "primary"},
    ],
    "documents": [
        {
            "document_id": f"{CASE}-p1-d1",
            "party_id": f"{CASE}-p1",
            "kind": "government_id",
            "content": {"tin": "1"},
        },
        {
            "document_id": f"{CASE}-p2-d1",
            "party_id": f"{CASE}-p2",
            "kind": "birth_certificate",
            "content": {"tin": "missing", "file": f"{CASE}-p2-d1_scan.pdf"},
        },
        {
            "document_id": f"{OTHER}-p1-d1",
            "party_id": f"{OTHER}-p1",
            "kind": "passport",
            "content": {},
        },
    ],
}
TAGS = ("minor-without-tin", "minor_without_tin", "passport-only", "passport_only")


def counter():
    n = iter(range(10_000))
    return lambda: f"{next(n):08X}"


def test_no_id_or_tag_reaches_the_agent_and_arguments_round_trip():
    al = aliasing.Aliaser(CASE, START, token=counter())
    shown = al.out({"records": START["documents"], "note": f"Application under review: {CASE}"})
    text = json.dumps(shown)
    assert not any(t in text for t in TAGS)
    assert CASE not in text and OTHER not in text
    assert al.out(f"{CASE}-p2-d1_scan.pdf").endswith(
        "_scan.pdf"
    )  # the ID inside a file name is replaced
    assert al.back(shown) == {
        "records": START["documents"],
        "note": f"Application under review: {CASE}",
    }
    p2 = al.forward[f"{CASE}-p2"]
    assert al.back({"party_id": p2, "items": ["tin"]}) == {
        "party_id": f"{CASE}-p2",
        "items": ["tin"],
    }
    assert al.back({"party_id": "made-up"}) == {
        "party_id": "made-up"
    }  # unknown text passes through
    assert al.record()["version"] == aliasing.VERSION and al.record()["aliases"][CASE].startswith(
        "APP-"
    )


def test_aliases_are_per_episode_and_stable_within_one():
    a, b = aliasing.Aliaser(CASE, START), aliasing.Aliaser(CASE, START)
    assert a.out(CASE) == a.out(CASE) and a.out(CASE) != b.out(CASE)
    docs = {
        "parties": [{"party_id": "p", "application_id": "case-x"}],
        "documents": [{"document_id": "doc-1", "party_id": "p"}],
    }
    out = aliasing.Aliaser("case-x", docs).out("doc-12 and doc-1")
    assert out.startswith("doc-12 and DOC-")  # a whole ID only, never inside a longer one


def _verdicts(blocks, config, snaps, reference):
    out = runner.run_blocks(
        {
            "config": config,
            "blocks": blocks,
            "case_id": CASE,
            "evidence": {"snapshots": snaps},
            "reference": reference,
            "expected_values_from": "case_reference",
        }
    )
    return out["verdict"], [(ln["block_id"], ln["verdict"]) for ln in out["block_lines"]]


def test_graders_give_identical_verdicts_with_aliasing_on_and_off_and_the_party_check_works():
    # The same agent decision, once as the environment sees it without aliasing, once as the agent wrote it with
    # aliases (mapped back by the RL Gym before the environment): the graders see the same real IDs either way.
    al = aliasing.Aliaser(CASE, START)
    plain = {"type": "tin", "party_id": f"{CASE}-p2"}
    from_agent = al.back({"type": "tin", "party_id": al.out(f"{CASE}-p2")})
    assert from_agent == plain
    fix = fixes.SUGGESTED["golden-kyc-blocks:next_action"]["config"]
    block = [
        {
            "id": "next_action.request",
            "kind": "state",
            "op": "exists_where",
            "row": "any",
            "table": "information_requests",
            "column": "type",
            "value": {"case_reference": "reference_answers.request_type"},
            "on_fail": "STATE_MUTATION_ERROR",
        }
    ]
    off = _verdicts(
        block,
        fix,
        {"start": START, "end": {**START, "information_requests": [plain]}},
        {"request_type": "tin"},
    )
    on = _verdicts(
        block,
        fix,
        {"start": START, "end": {**START, "information_requests": [from_agent]}},
        {"request_type": "tin"},
    )
    assert off == on and on[0] == "pass"  # D-041: the minor (p2) lacks the TIN
    wrong = al.back({"type": "tin", "party_id": al.out(f"{CASE}-p1")})
    assert (
        _verdicts(
            block,
            fix,
            {"start": START, "end": {**START, "information_requests": [wrong]}},
            {"request_type": "tin"},
        )[0]
        == "fail"
    )


def test_the_worker_aliases_what_the_agent_sees_and_maps_back_what_it_sends():
    src = inspect.getsource(worker.execute)
    for want in (
        'aliasing.Aliaser(episode["case_id"], (snapshots or {}).get("start"))',
        'real(action.get("args") or {})',
        "policy.send(shown(agent_obs))",
        'final = real(action["final"])',
        '"id_aliases": aliaser.record()',
    ):
        assert want in src, want
