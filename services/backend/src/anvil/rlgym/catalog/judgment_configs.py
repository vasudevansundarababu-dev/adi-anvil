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


def checks_for(criterion, config):
    """The judgment checks a bridge grader runs. consistency follows BANK-OPERATING-RULES-DRAFT §5e only when its
    configuration says so (`"rule": "5e"`, evaluator version 2+), so version 1's verdicts keep their meaning."""
    checks = list(GRADERS[criterion])
    if (config or {}).get("rule") == "5e":
        five_e = {"consistency": "consistency_5e", "risk_rating": "risk_rating_5e"}
        checks = [five_e.get(c, c) for c in checks]
    return checks


def _kc_final(rec, outcome, requests, referral):
    return {
        "recommendation": rec,
        "officer_verification": False,
        "risk_rating": {"required": False, "level": None, "factors": []},
        "assessments": [
            {
                "party_id": "kc-5e-p1",
                "outcome": outcome,
                "issues": [],
                "requests": requests,
                **({"referral": referral} if referral else {}),
            }
        ],
    }


_KC_REF = {"status": "complete", "gradable": True, "conditions_approved": True}
# The consistency fix version's added known cases (§5e.4 and §5e.3): a possible match with missing information is
# request_information and still referred; a referral with nothing outstanding is specialist_review.
CONSISTENCY_5E_KNOWN_CASES = {
    "request_with_referral": {
        "expect": "pass",
        "evidence": {
            "final_output": _kc_final(
                "request_information", "request_information", ["id_document"], "sanctions"
            )
        },
        "reference": _KC_REF,
    },
    "referral_without_request": {
        "expect": "fail",
        "evidence": {"final_output": _kc_final("request_information", "clear", [], "sanctions")},
        "reference": _KC_REF,
    },
}


def _kc_decision(rec, parties, level="high"):
    rr = {"required": True, "level": level, "factors": ["custodian_not_parent_or_guardian"]}
    final = {
        "recommendation": rec,
        "officer_verification": False,
        "risk_rating": rr,
        "assessments": parties,
    }
    ref = {
        **_KC_REF,
        "recommendation": rec,
        "officer_verification": False,
        "risk_rating": rr,
        "parties": [{**p, "referral": p.get("referral")} for p in parties],
    }
    return {"evidence": {"final_output": final}, "reference": ref}


_EDD = {"party_id": "kc-5e-p1", "outcome": "specialist_review", "requests": [], "referral": "edd"}
_ASK = {
    "party_id": "kc-5e-p2",
    "outcome": "request_information",
    "requests": ["relationship_proof"],
}
# decision_next_action fix version 3 (§5e): high risk with a request outstanding → request_information, EDD still
# referred (pass); high risk with nothing outstanding → specialist_review with EDD (pass); the same but approved
# (fail).
DECISION_5E_KNOWN_CASES = {
    "high_risk_with_request": {
        "expect": "pass",
        **_kc_decision("request_information", [_EDD, _ASK]),
    },
    "high_risk_specialist_review": {
        "expect": "pass",
        **_kc_decision("specialist_review", [_EDD]),
    },
    "high_risk_approved": {"expect": "fail", **_kc_decision("ready_for_approval", [_EDD])},
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


def known_case_lines(criterion, case, shared=None, config=None):
    """Known-case tests: the criterion's judgment lines computed from the known case itself."""
    from anvil.rlgym.scoring import judgment

    # Known cases test the grader's logic, not a result: a reference resting on placeholder rules is graded (an
    # awaiting_sme reference still isn't).
    x = {**inputs_from(case.get("evidence"), case.get("reference")), "placeholder_ok": True}
    # Shared truth Studio puts beside the known cases (e.g. the cases' mandatory SOP steps).
    x.update({k: v for k, v in (shared or {}).items() if k in ("mandatory_steps",)})
    return {f"{criterion}.{c}": judgment.evaluate(c, x) for c in checks_for(criterion, config)}
