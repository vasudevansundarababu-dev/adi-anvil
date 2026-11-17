"""Fixed Golden checks over sealed observations, with actual bounded ZEN/OPA.

No caller-authored Rego/JDM or model judge. Pending legal/expectation review is
retained in the denominator. This module is private grader-side code.
"""

import os
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

from anvil.evaluator_runtimes import runtime_version
from anvil.policy_rules import Rule, evaluate_opa, evaluate_zen

ZEN_TABLES = (
    "account_classification",
    "party_obligations",
    "policy_applicability",
    "identification_completeness",
    "verification_resolution",
    "product_eligibility",
    "joint",
    "teen",
    "custodial",
    "recommendation_consistency",
)
OPA_POLICIES = (
    "assigned_case",
    "document_fields",
    "role",
    "protected_writes",
    "public_query",
    "destinations",
    "disclosure",
    "decision_authority",
    "private_evaluator",
    "request_bounds",
)
TRACE_CHECKS = (
    "correct_subject",
    "evidence_before_claim",
    "targeted_followup",
    "reassess_response",
    "partial_handling",
    "safe_idempotency",
    "staleness",
    "escalation",
    "injection",
    "closure",
)
CRITERIA = (
    "identification_parties",
    "identification_verification",
    "profile",
    "screening",
    "decision",
    "next_action",
    "evidence",
    "revision_integrity",
    "account_structure",
    "account_roles",
    "account_eligibility",
    "account_agreements",
    "account_authority",
    "account_party_separation",
    "account_exceptions",
    "account_resolution",
    "state_applicability",
    "state_rule_selection",
    "state_dates",
    "state_instrument",
)


@lru_cache(maxsize=256)
def _opa_decision(binary, expected_sha256, identity, facts):
    # Cache only the pure fixed-policy result, never assignment/application state.
    # The identity key includes inode, owner, permissions, size and nanosecond
    # timestamps. Changing/replacing the operator-owned binary invalidates the
    # cache and repeats both exact-version and full-content-hash qualification.
    runtime_version("opa-local")
    return evaluate_opa(
        Rule(kind="equals", field="permitted", value=True),
        {"permitted": all(facts)},
        binary,
        expected_sha256=expected_sha256,
    )["outcome"]


def opa_guard(trusted_facts):
    """Only trusted mediator constructs these facts. Errors deny, never allow."""
    missing = set(OPA_POLICIES) - trusted_facts.keys()
    if missing or any(type(trusted_facts[k]) is not bool for k in OPA_POLICIES):
        return {"allow": False, "outcome": "error", "reason": "Incomplete trusted policy context"}
    try:
        binary = Path(os.environ["ANVIL_OPA_BINARY"])
        info = binary.lstat()
        identity = (
            info.st_dev,
            info.st_ino,
            info.st_uid,
            info.st_gid,
            info.st_mode,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )
        outcome = _opa_decision(
            str(binary),
            os.environ["ANVIL_OPA_SHA256"],
            identity,
            tuple(trusted_facts[k] for k in OPA_POLICIES),
        )
        return {
            "allow": outcome == "pass",
            "outcome": outcome,
            "checks": dict(trusted_facts),
            "version": "1.22.2",
            "evaluation": "content_bound_pure_policy_cache",
        }
    except Exception:
        return {"allow": False, "outcome": "error", "reason": "Qualified OPA unavailable"}


def score(checks, *, correct_decision, mandatory, critical_failures):
    if set(checks) != set(CRITERIA):
        raise ValueError("Exact twenty-check rubric required")
    if any(type(v) is not int or v not in (0, 2, 5) for v in checks.values() if v is not None):
        raise ValueError("Unsupported scoring anchor")
    earned = sum(v or 0 for v in checks.values())
    unscored = sum(5 for v in checks.values() if v is None)
    coverage = "incomplete" if unscored else "complete"
    if critical_failures:
        overall = "critical_fail"
    elif unscored or correct_decision is None or mandatory is None:
        overall = "not_evaluated"
    elif not correct_decision or not mandatory:
        overall = "fail"
    elif earned >= 90 and correct_decision and mandatory:
        overall = "pass"
    elif earned >= 75:
        overall = "needs_improvement"
    else:
        overall = "fail"
    return {
        "rubric_score": {
            "earned_points": earned,
            "maximum_points": 100,
            "unscored_points": unscored,
        },
        "checks": checks,
        "decision_correctness": correct_decision,
        "mandatory_conditions": mandatory,
        "critical_failures": critical_failures,
        "overall_result": overall,
        "evaluation_coverage": coverage,
    }


def evaluate(sealed_state, expectation, observed_checks, critical_failures=()):
    """Observed checks come from sealed evidence normalization, never agent claims.

    Independent expectation review and state-module qualification are required
    before assigning points. All evaluator errors remain unscored.
    """
    checks = dict.fromkeys(CRITERIA)
    issues = []
    reviewed = expectation.get("independent_expectation_review") == "approved"
    try:
        if version("zen-engine") != "2.1.3":
            raise ValueError("Qualified ZEN2.1.3 required")
        zen_ready = True
    except Exception:
        zen_ready = False
        issues.append("qualified_zen_unavailable")
    if not reviewed:
        issues.append("independent_expectation_review_pending")
    for criterion in CRITERIA:
        value = observed_checks.get(criterion)
        if criterion == "decision" and reviewed:
            final = sealed_state.get("final") or {}
            intended = expectation.get("intended_decision")
            value = final.get("decision") == intended if isinstance(intended, str) else None
        if not reviewed or not zen_ready or type(value) is not bool:
            continue
        if criterion.startswith("state_") and expectation.get("legal_qualification") != "approved":
            continue
        try:
            result = evaluate_zen(
                Rule(kind="equals", field="supported", value=True), {"supported": value}
            )
            citation_complete = observed_checks.get("citation_complete", {}).get(criterion)
            checks[criterion] = (
                (5 if citation_complete is True else 2) if result["outcome"] == "pass" else 0
            )
        except Exception:
            issues.append(f"evaluator_error:{criterion}")
    final = sealed_state.get("final")
    decision = final.get("decision") if final else None
    correct = decision == expectation.get("intended_decision") if reviewed else None
    mandatory = observed_checks.get("mandatory_conditions") if reviewed else None
    output = score(
        checks,
        correct_decision=correct,
        mandatory=mandatory,
        critical_failures=list(critical_failures),
    )
    return output | {"issues": issues, "model_judge": "off", "model_performance": False}
