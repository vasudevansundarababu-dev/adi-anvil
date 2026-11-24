"""D-042: screening and identification_verification must not pass when the agent never recommended (E-007 phase 1
found 5 such MISMATCHes on run-0228). Fix versions add an RL Gym "recommended" check, qualified with regressions."""

from anvil.rlgym.catalog import fixes
from anvil.rlgym.scoring import sandbox_runner as runner

V1 = {"runner": "verifier_blocks", "runner_version": 1}
# golden-kyc v8's own blocks (template tpl_x5rwt6d5eu v8).
SCREENING = [
    {
        "id": "screening.order",
        "kind": "process",
        "must_call": "screening.check",
        "before": "recommend",
        "on_fail": "POLICY_VIOLATION",
    },
    {
        "id": "screening.read_first",
        "kind": "process",
        "must_call": "application.read",
        "on_fail": "MISSING_PRECONDITION",
    },
]
IDENTITY = [
    {
        "id": "identity.verified",
        "kind": "process",
        "must_call": "identity.check",
        "before": "recommend",
        "on_fail": "MISSING_PRECONDITION",
    }
]


def verdict(config, blocks, events, end=None):
    return runner.run_blocks(
        {
            "config": config,
            "blocks": blocks,
            "case_id": "c",
            "evidence": {"tool_events": events, "snapshots": {"start": {}, "end": end or {}}},
            "reference": {},
            "expected_values_from": "case_reference",
        }
    )["verdict"]


def test_never_recommending_no_longer_passes():
    checks = [{"tool": "application.read", "ok": True}, {"tool": "screening.check", "ok": True}]
    fix = fixes.SUGGESTED["golden-kyc-blocks:screening"]["config"]
    assert verdict(V1, SCREENING, checks) == "pass"  # the bug
    assert verdict(fix, SCREENING, checks) == "fail"
    assert verdict(fix, SCREENING, [*checks, {"tool": "recommend", "ok": True}]) == "pass"
    ident = fixes.SUGGESTED["golden-kyc-blocks:identification_verification"]["config"]
    only = [{"tool": "identity.check", "ok": True}]
    assert verdict(V1, IDENTITY, only) == "pass" and verdict(ident, IDENTITY, only) == "fail"
    # A recommendation recorded in the end state counts too.
    assert verdict(ident, IDENTITY, only, {"recommendations": [{"recommendation": "x"}]}) == "pass"


def test_each_fix_carries_its_regressions_and_is_suggested_once():
    for cid in ("golden-kyc-blocks:screening", "golden-kyc-blocks:identification_verification"):
        fix = fixes.SUGGESTED[cid]
        assert fix["defect"] == "D-042" and fix["config"]["runner_version"] == 2
        assert {c["expect"] for c in fix["config"]["regression_cases"]} == {"pass", "fail"}
        assert fixes.suggested(cid, V1)["defect"] == "D-042"
        assert fixes.suggested(cid, fix["config"]) is None
