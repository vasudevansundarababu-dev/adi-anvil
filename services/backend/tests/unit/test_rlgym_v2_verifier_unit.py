"""Verifier blocks (adi.verifier-blocks.v1, work package 2.11): every State operator, Process ordering and args_match,
rubric shares, missing snapshots, activation checks against the bound version, synthetic known cases, and that block
values never reach the actor. No database, no Docker, no model."""

import json
import sys

import pytest

from anvil.config import ROOT
from anvil.rlgym.catalog import verifier
from anvil.rlgym.scoring import sandbox_runner as sr

sys.path.insert(0, str(ROOT / "services/stubs"))
import golden_kyc as g  # noqa: E402

CASE = "kyc-individual-001"
START = {"recommendations": [], "findings": [], "referrals": [], "notes": []}


def _run(
    blocks,
    end=None,
    start=None,
    events=(),
    final=None,
    reference=None,
    slots=None,
    source="case_reference",
):
    snapshots = None if end is None else {"start": START if start is None else start, "end": end}
    evidence = {
        "tool_events": list(events),
        "final_output": final
        or {"findings": [{"text": "A specific reason here", "evidence_ref": "doc-1"}]},
    }
    if snapshots:
        evidence["snapshots"] = snapshots
    return sr.evaluate(
        {
            "config": {"runner": "verifier_blocks", "runner_version": 1},
            "evidence": evidence,
            "reference": reference or {"recommendation": "escalate", "referral": 1},
            "blocks": blocks,
            "case_id": CASE,
            "slots": slots or {},
            "expected_values_from": source,
        }
    )


def _state(op, value=None, column="recommendation", table="recommendations", **extra):
    b = {
        "id": f"b.{op}",
        "kind": "state",
        "table": table,
        "row": "case",
        "op": op,
        "on_fail": "STATE_MUTATION_ERROR",
        **extra,
    }
    if column:
        b["column"] = column
    if value is not None:
        b["value"] = value
    return b


def _rec(value, case=CASE):
    return {"application_id": case, "recommendation": value}


def _end(*rows, **tables):
    return {**START, "recommendations": list(rows), **tables}


@pytest.mark.parametrize(
    ("block", "end", "verdict"),
    [
        (
            _state("equals", {"case_reference": "reference_answers.recommendation"}),
            _end(_rec("escalate")),
            "pass",
        ),
        (
            _state("equals", {"case_reference": "reference_answers.recommendation"}),
            _end(_rec("approve")),
            "fail",
        ),
        (
            _state("equals", {"fixed": "escalate"}),
            _end(_rec("approve"), _rec("escalate")),
            "pass",
        ),  # latest write
        (
            _state("equals", {"fixed": "escalate"}),
            _end(_rec("escalate", case="other")),
            "fail",
        ),  # another case's row
        (
            _state("in", {"fixed": ["escalate", "request_documents"]}),
            _end(_rec("escalate")),
            "pass",
        ),
        (_state("in", {"fixed": ["approve"]}), _end(_rec("escalate")), "fail"),
        (_state("contains", {"fixed": "esc"}), _end(_rec("escalate")), "pass"),
        (
            _state("contains", {"fixed": "Screening_HIT"}),
            _end(_rec("Possible screening_hit on PEP list"), _rec("approve")),
            "pass",
        ),  # any in-scope row, ignoring case: the match is in the first row, not the latest
        (_state("contains", {"fixed": "hit"}), _end(_rec("approve"), _rec("clear")), "fail"),
        (
            _state("contains", {"fixed": "hit"}),
            _end(_rec("screening hit", case="other"), _rec("approve")),
            "fail",
        ),  # another case's row is out of scope
        (_state("contains", {"fixed": "pep"}), _end(_rec(["PEP", "sanctions"])), "fail"),
        (_state("contains", {"fixed": "PEP"}), _end(_rec(["PEP", "sanctions"])), "pass"),
        (
            _state("exists_where", {"fixed": "escalate"}),
            _end(_rec("approve"), _rec("escalate")),
            "pass",
        ),
        (_state("exists_where", {"fixed": "decline"}), _end(_rec("escalate")), "fail"),
        (_state("not_exists", {"fixed": "approve"}), _end(_rec("escalate")), "pass"),
        (_state("not_exists", {"fixed": "approve"}), _end(_rec("approve")), "fail"),
        (_state("count", {"fixed": 1}, column=None), _end(_rec("escalate")), "pass"),
        (
            _state("count", {"fixed": 1}, column=None),
            _end(_rec("escalate"), _rec("approve")),
            "fail",
        ),
        (_state("changed", column=None), _end(_rec("escalate")), "pass"),
        (_state("changed", column=None), _end(), "fail"),
        (_state("unchanged", column=None), _end(), "pass"),
        (_state("unchanged", column=None), _end(_rec("escalate")), "fail"),
    ],
)
def test_each_state_operator(block, end, verdict):
    out = _run([block], end=end)
    assert out["verdict"] == verdict, out
    line = out["block_lines"][0]
    assert set(line) == {"block_id", "kind", "expected", "actual", "verdict", "on_fail"}
    assert line["verdict"] == verdict


def test_nothing_else_changed_compares_start_and_end():
    block = _state("nothing_else_changed", column=None, allow=["findings"])
    finding = {"application_id": CASE, "finding_id": "f-1"}
    assert _run([block], end=_end(_rec("escalate"), findings=[finding]))["verdict"] == "pass"
    out = _run(
        [block], end=_end(_rec("escalate"), notes=[{"application_id": CASE, "note_id": "n-1"}])
    )
    assert out["verdict"] == "fail" and out["block_lines"][0]["actual"] == {
        "changed_tables": ["notes"]
    }


def test_a_missing_snapshot_is_blocked_never_passed():
    for op in ("equals", "nothing_else_changed", "count"):
        out = _run([_state(op, {"fixed": 1})], end=None)
        assert out["verdict"] == "blocked" and out["points"] is None
        assert out["block_lines"][0]["actual"] == {"missing": "no snapshot"}
    # changed needs the start snapshot too
    out = sr.evaluate(
        {
            "config": {"runner": "verifier_blocks", "runner_version": 1},
            "evidence": {"snapshots": {"start": None, "end": _end(_rec("x"))}},
            "reference": {},
            "blocks": [_state("changed", column=None)],
            "case_id": CASE,
        }
    )
    assert out["verdict"] == "blocked"


def test_a_missing_expected_value_is_blocked():
    out = _run(
        [_state("equals", {"case_reference": "reference_answers.unknown"})],
        end=_end(_rec("escalate")),
    )
    assert out["verdict"] == "blocked" and out["block_lines"][0]["actual"] == {
        "missing": "expected value missing"
    }


def test_process_ordering_and_args_match():
    block = {
        "id": "p",
        "kind": "process",
        "must_call": "screening.check",
        "before": "recommend",
        "on_fail": "POLICY_VIOLATION",
    }
    good = [{"tool": "screening.check", "ok": True}, {"tool": "recommend", "ok": True}]
    assert _run([block], events=good)["verdict"] == "pass"
    assert _run([block], events=list(reversed(good)))["verdict"] == "fail"
    assert (
        _run([block], events=[{"tool": "screening.check", "ok": False}])["verdict"] == "fail"
    )  # a failed call
    after = {
        "id": "a",
        "kind": "process",
        "must_call": "recommend",
        "after": "screening.check",
        "on_fail": "POLICY_VIOLATION",
    }
    assert _run([after], events=good)["verdict"] == "pass"
    assert _run([after], events=[{"tool": "recommend", "ok": True}])["verdict"] == "fail"
    args = {
        "id": "m",
        "kind": "process",
        "must_call": "application.read",
        "args_match": {"case_id": "$case", "mode": {"fixed": "full"}},
        "on_fail": "MISSING_PRECONDITION",
    }
    assert (
        _run(
            [args],
            events=[
                {"tool": "application.read", "args": {"case_id": CASE, "mode": "full"}, "ok": True}
            ],
        )["verdict"]
        == "pass"
    )
    assert (
        _run(
            [args],
            events=[
                {
                    "tool": "application.read",
                    "args": {"case_id": "other", "mode": "full"},
                    "ok": True,
                }
            ],
        )["verdict"]
        == "fail"
    )
    missing_log = sr.evaluate(
        {
            "config": {"runner": "verifier_blocks", "runner_version": 1},
            "evidence": {},
            "blocks": [block],
            "case_id": CASE,
        }
    )
    assert missing_log["verdict"] == "blocked"


def test_state_and_process_gate_and_rubrics_carry_their_share():
    status = _state("equals", {"fixed": "escalate"})
    rubric = {
        "id": "r",
        "kind": "rubric",
        "rubric_id": "reason_is_specific",
        "share_percent": 20,
        "on_fail": "QUALITY",
    }
    ok = _run([status, rubric], end=_end(_rec("escalate")))
    assert ok["verdict"] == "pass" and ok["points"] == 1.0
    vague = _run([status, rubric], end=_end(_rec("escalate")), final={"findings": [{"text": "ok"}]})
    assert vague["verdict"] == "partial" and vague["points"] == 0.8
    gated = _run([status, rubric], end=_end(_rec("approve")))
    assert (
        gated["verdict"] == "fail" and gated["points"] == 0.0
    )  # a failed State check zeroes the criterion


def test_sme_slot_values_are_used_when_the_template_says_sme():
    block = _state("equals", {"slot": {"id": "expected_recommendation"}})
    out = _run(
        [block],
        end=_end(_rec("specialist_review")),
        slots={"expected_recommendation": "specialist_review"},
        source="sme",
    )
    assert out["verdict"] == "pass"
    assert (
        _run([block], end=_end(_rec("x")), source="sme")["verdict"] == "blocked"
    )  # no slot value: blocked


def test_unknown_runner_version_is_an_error_not_a_pass():
    out = sr._safe(
        {
            # D-041 added runner version 2 (template blocks plus RL Gym extra blocks); 3 is unknown.
            "config": {"runner": "verifier_blocks", "runner_version": 3},
            "blocks": [_state("count", {"fixed": 1})],
        }
    )
    assert out["verdict"] == "error"


ENV = {
    "id": "golden-kyc-openenv@v6",
    "schema": g.SCHEMA_V6,
    "operations": [{"operation_id": t} for t in g.TOOLS_V6],
}


def test_activation_refuses_undeclared_collections_fields_tools_and_codes():
    good = g.VERIFIER_BLOCKS["decision"]
    assert verifier.check_blocks(good, ENV, "case_reference", g.FAILURE_TAXONOMY) == []
    bad = [
        {**good[0], "column": "approved_by"},
        {**good[1], "table": "ledger"},
        {**good[3], "before": "account.open"},
        {**good[4], "rubric_id": "made_up"},
        {**good[0], "id": "x", "on_fail": "OOPS"},
        {**good[0], "id": "y", "value": {"case_reference": "reference_answers.secret"}},
        {**good[0], "id": "z", "op": "matches"},
    ]
    reasons = verifier.check_blocks(bad, ENV, "case_reference", g.FAILURE_TAXONOMY)
    text = " | ".join(reasons)
    for needle in (
        "recommendations.approved_by is not declared",
        "collection 'ledger' is not declared",
        "before 'account.open' is not a declared operation",
        "rubric 'made_up' is not in the RL Gym's rubric registry",
        "on_fail 'OOPS'",
        "'reference_answers.secret' is not a declared reference_answers field",
        "unknown op 'matches'",
    ):
        assert needle in text, text
    assert "above 100%" in " ".join(
        verifier.check_blocks(
            [
                {
                    "id": "r1",
                    "kind": "rubric",
                    "rubric_id": "evidence_cited",
                    "share_percent": 70,
                    "on_fail": "QUALITY",
                },
                {
                    "id": "r2",
                    "kind": "rubric",
                    "rubric_id": "evidence_cited",
                    "share_percent": 40,
                    "on_fail": "QUALITY",
                },
            ],
            ENV,
            "case_reference",
            g.FAILURE_TAXONOMY,
        )
    )
    assert "value needs slot" in " ".join(
        verifier.check_blocks(good[:1], ENV, "sme", g.FAILURE_TAXONOMY)
    )


@pytest.mark.parametrize("criterion", sorted(g.VERIFIER_BLOCKS))
def test_synthetic_known_cases_pass_fail_with_the_right_code_and_block(criterion):
    blocks = g.VERIFIER_BLOCKS[criterion]
    cases = verifier.known_cases(blocks)
    seen = {}
    for name, case in cases.items():
        out = sr.evaluate(
            {
                "config": {"runner": "verifier_blocks", "runner_version": 1},
                "evidence": case["evidence"],
                "reference": case["reference"],
                "blocks": blocks,
                "case_id": case["case_id"],
                "slots": case["slots"],
                "expected_values_from": "case_reference",
            }
        )
        seen[name] = out["verdict"]
        if name == "disallowed":
            fails = {
                (line["block_id"], line["on_fail"])
                for line in out["block_lines"]
                if line["verdict"] == "fail"
            }
            assert (case["expect_block"], case["expect_on_fail"]) in fails
    assert seen == {"allowed": "pass", "disallowed": "fail", "missing_evidence": "blocked"}


def test_block_values_never_reach_the_actor():
    """The task's actor part and the agent's inputs carry no reference or slot values, and the snapshot is not a tool."""
    tasks = g.forge_tasks("exp-test", template_version=g.BLOCKS_VERSION, project_id="prj_b10c4e21")
    actor = json.dumps([t["package"]["actor"] for t in tasks])
    for word in ("reference_answers", "expected_recommendation", "verifier", "slots", "snapshot"):
        assert word not in actor
    assert "snapshot" not in g.TOOLS and "state" not in g.TOOLS


def test_v10_blocks_sit_inside_the_template_hash():
    t = g.template(g.BLOCKS_VERSION)
    assert t["expected_values_from"] == "case_reference"
    changed = json.loads(json.dumps(t))
    changed["criteria"][[c["criterion_id"] for c in t["criteria"]].index("decision")][
        "verifier_blocks"
    ][0]["op"] = "in"
    body = {
        k: v
        for k, v in changed.items()
        if k not in ("forge_template_id", "forge_version", "spec_sha256", "template_sha256")
    }
    assert g.sha(body) != t["spec_sha256"]


def test_exists_where_with_a_none_reference_means_no_such_row():
    """Studio's reference writes "none" when nothing of that kind is expected (design choice A: referrals.specialty,
    information_requests.type)."""
    block = {
        "id": "screening.specialty",
        "kind": "state",
        "table": "referrals",
        "row": "any",
        "column": "specialty",
        "op": "exists_where",
        "value": {"case_reference": "reference_answers.referral"},
        "on_fail": "POLICY_VIOLATION",
    }
    sanctions = {"referral_id": "r-1", "specialty": "sanctions"}
    unset = {
        "referral_id": "r-2",
        "specialty": None,
    }  # an optional argument left out is stored as null
    assert (
        _run([block], end=_end(referrals=[sanctions]), reference={"referral": "sanctions"})[
            "verdict"
        ]
        == "pass"
    )
    assert (
        _run([block], end=_end(referrals=[unset]), reference={"referral": "sanctions"})["verdict"]
        == "fail"
    )
    assert (
        _run([block], end=_end(referrals=[]), reference={"referral": "none"})["verdict"] == "pass"
    )
    assert (
        _run([block], end=_end(referrals=[unset]), reference={"referral": "none"})["verdict"]
        == "pass"
    )
    wrong = _run([block], end=_end(referrals=[sanctions]), reference={"referral": "none"})
    assert wrong["verdict"] == "fail" and wrong["block_lines"][0]["actual"] == ["sanctions"]


def test_activation_refuses_a_fixed_value_outside_the_fields_enum():
    block = {
        "id": "n",
        "kind": "state",
        "table": "information_requests",
        "row": "any",
        "column": "type",
        "op": "exists_where",
        "value": {"fixed": "passport_scan"},
        "on_fail": "MISSING_PRECONDITION",
    }
    reasons = verifier.check_blocks([block], ENV, "case_reference", g.FAILURE_TAXONOMY)
    assert any("not in information_requests.type's values" in r for r in reasons), reasons
    ok = {**block, "value": {"fixed": "proof_of_address"}}
    assert verifier.check_blocks([ok], ENV, "case_reference", g.FAILURE_TAXONOMY) == []


def test_v8_tool_contract_is_unchanged_and_v6_adds_the_typed_tools():
    versions = g.environment_versions()
    assert versions["golden-kyc-openenv@v3"]["operations"] == g.TOOLS
    assert "information.request" not in g.TOOLS and "specialist.refer" not in g.TOOLS
    v6 = versions["golden-kyc-openenv@v6"]
    assert {o["operation_id"] for o in v6["operations"]} == set(g.TOOLS_V6)
    refs = [c["reference"] for c in v6["_cases"]]
    assert {r["referral"] for r in refs} <= {"sanctions", "none"}
    assert {r["request_type"] for r in refs} <= {
        "id_document",
        "proof_of_address",
        "street_address",
        "tin",
        "none",
    }


def test_nothing_else_changed_names_no_table():
    """Studio's blocks send table "*" (or omit it) for nothing_else_changed: it compares every collection."""
    for table in ("*", None):
        block = {
            "id": "d.other",
            "kind": "state",
            "op": "nothing_else_changed",
            "allow": ["findings"],
            "on_fail": "UNSAFE_ACTION",
        }
        if table:
            block["table"] = table
        status = {**g.VERIFIER_BLOCKS["decision"][0]}
        assert (
            verifier.check_blocks([status, block], ENV, "case_reference", g.FAILURE_TAXONOMY) == []
        )
        cases = verifier.known_cases([block, status])
        for name, case in cases.items():
            out = sr.evaluate(
                {
                    "config": {"runner": "verifier_blocks", "runner_version": 1},
                    "evidence": case["evidence"],
                    "reference": case["reference"],
                    "blocks": [block, status],
                    "case_id": case["case_id"],
                    "slots": case["slots"],
                    "expected_values_from": "case_reference",
                }
            )
            assert out["verdict"] == case["expect"], (table, name, out)
