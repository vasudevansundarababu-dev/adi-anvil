"""KYC Judgment v1: the RL Gym checks each rubric criterion runs. When Studio registers the Judgment rubric's
evaluator configurations (capability kyc-judgment-rubric-v1), RL Gym registers them as runner version 2 carrying its
judgment lines (versioned and hashed with the configuration):
- rules_applied: rules applied + the rule in force at the recommend call;
- decision_next_action: decision (per party) + risk rating;
- evidence_judgment: audit-trail faithfulness (invented evidence is critical).
They qualify on regression fixtures (pass, fail, not applicable, critical); synthetic known cases run the template's
own blocks only."""

import inspect

from anvil.rlgym.catalog import evaluators, judgment_configs

FRAMEWORK = {
    "id": "fw-python-1.0.0",
    "runtime_id": "python",
    "installed_locally": True,
    "state": "qualified",
}


def test_the_checks_per_criterion():
    assert judgment_configs.CHECKS == {
        "rules_applied": ["rules_applied", "rule_in_force"],
        "decision_next_action": ["decision", "risk_rating"],
        "evidence_judgment": ["audit_faithfulness"],
    }
    cfg = judgment_configs.config_for(
        "rules_applied", {"runner": "verifier_blocks", "runner_version": 1, "evidence": "snapshots"}
    )
    assert cfg["runner_version"] == 2
    assert [b["check"] for b in cfg["extra_blocks"]] == ["rules_applied", "rule_in_force"]
    assert (
        judgment_configs.config_for("rationale", {"runner": "verifier_blocks", "runner_version": 1})
        is None
    )


def test_each_configuration_qualifies_on_its_regressions():
    for criterion in judgment_configs.CHECKS:
        cfg = judgment_configs.config_for(
            criterion, {"runner": "verifier_blocks", "runner_version": 1, "evidence": "snapshots"}
        )
        cases = {rc["name"]: {**rc, "slots": {}} for rc in cfg["regression_cases"]}
        checks = evaluators.block_case_checks(FRAMEWORK, cfg, [], cases, "case_reference")
        assert {c["expected"] for c in checks} >= {"pass", "fail", "not_applicable"}
        assert [c["result"] for c in checks] == ["pass"] * len(checks), checks


def test_registration_and_synthetic_cases_are_wired():
    src = inspect.getsource(evaluators.create_from_studio)
    assert "judgment_configs.config_for(" in src
    assert 'case.get("judgment_results")' in inspect.getsource(evaluators.block_case_checks)
