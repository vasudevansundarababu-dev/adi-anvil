"""KYC Judgment v1 (G2): the RL Gym checks each rubric criterion of capability `kyc-judgment-rubric-v1` runs. When
Studio registers that rubric's verifier-blocks configurations, RL Gym registers them as runner version 2 with these
judgment lines in `extra_blocks`, so the checks are part of the configuration's hash and version. Each qualifies on
its regression fixtures (precomputed judgment lines: pass, fail, not applicable, critical)."""

CAPABILITY = "kyc-judgment-rubric-v1"
CHECKS = {
    "rules_applied": ["rules_applied", "rule_in_force"],
    "decision_next_action": ["decision", "risk_rating"],
    "evidence_judgment": ["audit_faithfulness"],
}
CASE = "kc-judgment-001"


def _block(criterion, check):
    return {
        "id": f"{criterion}.{check}",
        "kind": "judgment",
        "check": check,
        "name": check.replace("_", " "),
        "on_fail": "CRITICAL" if check == "audit_faithfulness" else "STATE_MUTATION_ERROR",
    }


def _case(name, results, expect):
    return {
        "name": name,
        "case_id": CASE,
        "evidence": {"snapshots": {"start": {}, "end": {}}},
        "reference": {},
        "judgment_results": results,
        "expect": expect,
    }


def regressions(criterion):
    ids = [f"{criterion}.{c}" for c in CHECKS[criterion]]

    def lines(*verdicts, critical=False):
        return {
            i: {
                "verdict": v,
                "actual": None,
                "expected": None,
                "critical": critical and v == "fail",
            }
            for i, v in zip(ids, verdicts, strict=False)
        }

    n = len(ids)
    out = [
        _case(f"{criterion}_all_right", lines(*["pass"] * n), "pass"),
        _case(f"{criterion}_one_wrong", lines("fail", *["pass"] * (n - 1)), "fail"),
        _case(f"{criterion}_not_applicable", lines(*["not_applicable"] * n), "not_applicable"),
    ]
    if n > 1:
        out.append(
            _case(
                f"{criterion}_one_line_not_applicable",
                lines("pass", *["not_applicable"] * (n - 1)),
                "pass",
            )
        )
    if criterion == "evidence_judgment":
        out.append(_case(f"{criterion}_invented_evidence", lines("fail", critical=True), "fail"))
    return out


def config_for(criterion, studio_config):
    """The configuration RL Gym registers for this criterion, or None when RL Gym adds no checks to it."""
    if criterion not in CHECKS:
        return None
    return {
        **studio_config,
        "runner_version": 2,
        "extra_blocks": [_block(criterion, c) for c in CHECKS[criterion]],
        "regression_cases": regressions(criterion),
    }


# --- the activation bridge (Studio 6779e3f): one evaluator per rubric criterion, config.grader names RL Gym's grader --
PREFIX = "kyc-judgment.g2."
GRADERS = {
    "tool_calls": ["tool_calls"],
    "procedure_output": ["procedure_output"],
    "rules_applied": ["rules_applied", "rule_in_force"],
    "evidence_judgment": ["evidence_judgment"],
    "decision_next_action": ["decision", "risk_rating"],
    "rationale": ["rationale"],
    "process_adherence": ["process_adherence"],
    "evidence_faithfulness": ["audit_faithfulness"],
    "missing_facts": ["missing_facts"],
    "consistency": ["consistency"],
}


def grader_of(config):
    """The rubric criterion a configuration's `grader` names, or None for any other configuration."""
    g = (config or {}).get("grader") or ""
    name = g[len(PREFIX) :] if g.startswith(PREFIX) else None
    return name if name in GRADERS else None


def inputs_from(evidence, reference, judgment_part=None, case=None):
    """The judgment inputs from an episode's (or a known case's) evidence."""
    evidence = evidence or {}
    return {
        "final": evidence.get("final_output"),
        "tool_events": evidence.get("tool_events"),
        "transcript": evidence.get("transcript") or [],
        "aliases": evidence.get("aliases") or {},
        "fired": evidence.get("scenario_events_fired") or [],
        "reference": reference,
        "library": (judgment_part or {}).get("library"),
        "case": case,
    }


def known_case_lines(criterion, case):
    """Known-case tests: the criterion's judgment lines computed from the known case itself."""
    from anvil.rlgym.scoring import judgment

    x = inputs_from(case.get("evidence"), case.get("reference"))
    return {f"{criterion}.{c}": judgment.evaluate(c, x) for c in GRADERS[criterion]}
