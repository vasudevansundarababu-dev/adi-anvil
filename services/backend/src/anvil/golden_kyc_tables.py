"""Ten fixed versioned business tables; unknown facts are never false.

Rows compile only to existing bounded scalar ZEN templates. No uploaded JDM,
custom functions, remote loaders or arbitrary expressions are admitted.
"""

from anvil.golden_kyc_data import VERSION, age
from anvil.policy_rules import Rule, evaluate_zen


def _check(field, value, expected=True, kind="equals"):
    if value is None:
        return {
            "outcome": "unknown",
            "field": field,
            "reason": "Required observed fact unavailable",
        }
    return evaluate_zen(Rule(kind=kind, field=field, value=expected), {field: value}) | {
        "field": field
    }


def _table(identifier, rows, applicable=True):
    if not applicable:
        return {"table": identifier, "version": VERSION, "outcome": "not_applicable", "rows": []}
    outcomes = [r["outcome"] for r in rows]
    outcome = (
        "fail"
        if "fail" in outcomes
        else "error"
        if "error" in outcomes
        else "unknown"
        if "unknown" in outcomes
        else "pass"
    )
    return {"table": identifier, "version": VERSION, "outcome": outcome, "rows": rows}


def evaluate_tables(snapshot, observed):
    product, people = snapshot["product"], snapshot["parties"]
    roles = [p["role"] for p in people]
    expected_roles = {
        "individual": ["owner"],
        "adult_joint": ["owner", "owner"],
        "teen_joint": ["teen_owner", "adult_owner"],
        "custodial": ["custodian", "beneficiary"],
    }[product]
    adults = [p for p in people if p["role"] in ("owner", "adult_owner")]
    teen = next((p for p in people if p["role"] == "teen_owner"), None)
    structure = sorted(roles) == sorted(expected_roles)
    adult_eligible = (
        None
        if any(p["birth_date"] is None for p in adults)
        else all(age(p["birth_date"], snapshot["assessment_date"]) >= 18 for p in adults)
    )
    teen_eligible = (
        13 <= age(teen["birth_date"], snapshot["assessment_date"]) <= 17
        if teen and teen["birth_date"] is not None
        else None
    )
    route_results = observed.get("identity_routes_satisfied")
    eligibility = (
        None
        if product == "custodial"
        else structure and adult_eligible and (teen_eligible if product == "teen_joint" else True)
    )
    selected = snapshot["requested_product"] == product
    if not selected:
        eligibility = False
    decisions = observed.get("decision_supported")
    return [
        _table(
            "account_classification",
            [
                _check("structure", structure),
                _check(
                    "recognized_product",
                    product in ("individual", "adult_joint", "teen_joint", "custodial"),
                ),
            ],
        ),
        _table(
            "party_obligations",
            [
                _check("all_parties_assessed", observed.get("all_parties_assessed")),
                _check("cip_customer_roles", observed.get("cip_customer_roles_correct")),
            ],
        ),
        _table(
            "policy_applicability",
            [
                _check(
                    "charter_reviewed",
                    True if snapshot["charter_applicability"]["reviewed"] else None,
                ),
                _check("state_module", observed.get("state_module_qualified")),
            ],
        ),
        _table(
            "identification_completeness",
            [
                _check(
                    "declared_identification",
                    all(p.get("name") and p.get("birth_date") and p.get("address") for p in people),
                ),
                _check("route_satisfied", route_results),
            ],
        ),
        _table(
            "verification_resolution",
            [
                _check("identity_resolved", observed.get("identity_resolved")),
                _check("screening_resolved", observed.get("screening_resolved")),
                _check("address_resolved", observed.get("address_resolved")),
            ],
        ),
        _table("product_eligibility", [_check("requested_product_eligible", eligibility)]),
        _table(
            "joint",
            [
                _check("two_owners", len(people), 2),
                _check("adult_owners", adult_eligible),
                _check("joint_terms", observed.get("joint_terms_verified")),
            ],
            product == "adult_joint",
        ),
        _table(
            "teen",
            [
                _check("teen_age", teen_eligible),
                _check("adult_age", adult_eligible),
                _check("adult_relationship", observed.get("relationship_verified")),
                _check("both_joint_owners", structure),
            ],
            product == "teen_joint",
        ),
        _table(
            "custodial",
            [
                _check("custodial_roles", structure),
                _check("statutory_eligibility", observed.get("custodian_statutory_eligibility")),
                _check("transfer_category", observed.get("transfer_category_verified")),
                _check("age_election", observed.get("age_election_verified")),
            ],
            product == "custodial",
        ),
        _table("recommendation_consistency", [_check("supported_decision", decisions)]),
    ]
