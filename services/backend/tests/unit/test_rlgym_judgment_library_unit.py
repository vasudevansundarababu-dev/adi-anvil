"""KYC Judgment v1 (C1/C2): the policy library resolver and the condition compiler's per-party and multi-valued
evaluation. Which rules apply is computed from the PM-approved conditions over the case's facts (§13), with the
version in force, derived facts (us_person, never stated) and rules withdrawn or published mid-episode (C3)."""

from anvil.rlgym.runs import clauses, library

# --- multi-valued facts (C1 §8): eq/in when any value matches; ne/not_in when none does; [] is a decided "none" -----


def test_multi_valued_facts():
    f = {"citizenship": ["US", "MX"], "document_kinds": []}
    ev = lambda p: clauses.evaluate(p, f)[0]  # noqa: E731
    assert ev({"fact": "citizenship", "op": "eq", "value": "MX"}) is True
    assert ev({"fact": "citizenship", "op": "in", "value": ["CA", "US"]}) is True
    assert ev({"fact": "citizenship", "op": "ne", "value": "MX"}) is False
    assert ev({"fact": "citizenship", "op": "not_in", "value": ["FR"]}) is True
    assert ev({"fact": "document_kinds", "op": "eq", "value": "passport"}) is False
    assert ev({"fact": "document_kinds", "op": "ne", "value": "passport"}) is True
    assert ev({"fact": "document_kinds", "op": "present"}) is False
    assert ev({"fact": "document_kinds", "op": "absent"}) is True
    assert ev({"fact": "citizenship", "op": "gt", "value": 3}) is False


def test_scalar_facts_behave_as_before():
    f = {"product": "custodial", "age": 17}
    assert clauses.evaluate({"fact": "product", "op": "in", "value": ["custodial"]}, f)[0] is True
    assert clauses.evaluate({"fact": "age", "op": "lt", "value": 18}, f)[0] is True
    assert clauses.evaluate({"fact": "missing", "op": "eq", "value": 1}, f)[0] is None


# --- the library ----------------------------------------------------------------------------------------------------------

ACC = {"fact": "process", "op": "eq", "value": "account_opening"}


def ver(n, cond, effective=None, effect="obligation", text=None):
    t = text or f"text of version {n}"
    return {
        "version": n,
        "effective": effective or {"mode": "from_date", "from": "2026-01-01"},
        "effect": effect,
        "condition": cond,
        "text": t,
        "text_sha256": library.text_sha(t),
    }


LIB = {
    "derived_facts": [
        {
            "id": "us_person",
            "type": "boolean",
            "definition": {"fact": "citizenship", "op": "in", "value": ["US"]},
            "defined_by": {"rule_id": "R-US-PERSON-DEFINITION", "version": 1},
        }
    ],
    "rules": [
        {"rule_id": "R-US-PERSON-DEFINITION", "subject": "party", "versions": [ver(1, None)]},
        {
            "rule_id": "R-US-ID-NUMBER",
            "subject": "party",
            "versions": [ver(1, {"all": [ACC, {"fact": "us_person", "op": "eq", "value": True}]})],
        },
        {
            "rule_id": "R-NON-US-ID-NUMBER",
            "subject": "party",
            "versions": [ver(1, {"all": [ACC, {"fact": "us_person", "op": "eq", "value": False}]})],
        },
        {
            "rule_id": "R-REMOTE-NON-DOC",
            "subject": "case",
            "versions": [
                ver(1, {"all": [ACC, {"fact": "opening_channel", "op": "eq", "value": "remote"}]})
            ],
        },
        {
            "rule_id": "R-CTR-FILING",
            "subject": "case",
            "versions": [
                ver(1, {"fact": "process", "op": "eq", "value": "currency_transaction_reporting"})
            ],
        },
        {
            "rule_id": "GB-03",
            "subject": "party",
            "versions": [
                ver(1, {"all": [ACC, {"fact": "party_role", "op": "eq", "value": "minor"}]}),
                {
                    **ver(
                        2,
                        {"all": [ACC, {"fact": "party_role", "op": "eq", "value": "minor"}]},
                        {"mode": "scenario_only"},
                        "withdrawn",
                    ),
                    "supersedes": 1,
                },
            ],
        },
        {
            "rule_id": "GB-LATER",
            "subject": "case",
            "versions": [
                ver(1, ACC, {"mode": "from_date", "from": "2026-01-01"}),
                {**ver(4, ACC, {"mode": "from_date", "from": "2026-12-01"}), "supersedes": 1},
            ],
        },
        {"rule_id": "GB-STRICTER-APPLIES", "subject": "case", "versions": [ver(1, None)]},
    ],
}
CASE = {
    "schema_version": "adi.utility.registry-case.v2",
    "case_id": "kj-1",
    "submitted_at": "2026-10-15T10:00:00Z",
    "facts": {"process": "account_opening", "opening_channel": "remote", "product": "teen_joint"},
    "parties": [
        {"party_id": "p1", "facts": {"party_role": "primary", "citizenship": ["MX"]}},
        {"party_id": "p2", "facts": {"party_role": "minor", "citizenship": ["US", "MX"]}},
    ],
}


def ids(res):
    return {(r["rule_id"], r["version"]): sorted(r["party_ids"]) for r in res["applies"]}


def test_which_rules_apply_per_party_with_derived_us_person():
    got = ids(library.applicable(LIB, CASE))
    assert got[("R-US-ID-NUMBER", 1)] == ["p2"]
    assert got[("R-NON-US-ID-NUMBER", 1)] == ["p1"]
    assert got[("R-REMOTE-NON-DOC", 1)] == []
    assert got[("GB-03", 1)] == ["p2"]
    assert (
        "R-CTR-FILING",
        1,
    ) not in got  # another process: a distractor resolves to "doesn't apply"
    # A null condition always applies (the definition rule, "apply the stricter").
    assert ("GB-STRICTER-APPLIES", 1) in got and ("R-US-PERSON-DEFINITION", 1) in got


def test_the_version_in_force_is_by_submission_date():
    got = ids(library.applicable(LIB, CASE))
    assert ("GB-LATER", 1) in got and ("GB-LATER", 4) not in got
    later = {**CASE, "submitted_at": "2026-12-15T10:00:00Z"}
    assert ("GB-LATER", 4) in ids(library.applicable(LIB, later))


def test_a_scenario_publication_puts_the_next_version_in_force_from_its_sequence():
    fired = [{"rule_id": "GB-03", "from_version": 1, "to_version": 2, "published_at_sequence": 12}]
    before = library.applicable(LIB, CASE, fired=fired, as_of_sequence=10)
    assert ("GB-03", 1) in ids(before)
    after = library.applicable(LIB, CASE, fired=fired, as_of_sequence=13)
    # Version 2 withdraws the rule: in force, but it applies nothing.
    assert ("GB-03", 1) not in ids(after) and ("GB-03", 2) not in ids(after)
    assert library.in_force(LIB, "GB-03", CASE, fired=fired, as_of_sequence=13)["version"] == 2
    # A scenario_only version is never in force without a publication.
    assert library.in_force(LIB, "GB-03", CASE)["version"] == 1


def test_a_missing_fact_is_unresolved_never_guessed():
    case = {**CASE, "parties": [{"party_id": "p1", "facts": {"party_role": "primary"}}]}
    res = library.applicable(LIB, case)
    assert ("R-US-ID-NUMBER", 1) not in ids(res)
    assert any(u["rule_id"] == "R-US-ID-NUMBER" for u in res["unresolved"])


def test_hashes_are_checked():
    bad = {
        **LIB,
        "rules": [
            {
                **LIB["rules"][0],
                "versions": [{**LIB["rules"][0]["versions"][0], "text_sha256": "0" * 64}],
            }
        ],
    }
    assert library.hash_problems(bad) == ["R-US-PERSON-DEFINITION v1"]
    assert library.hash_problems(LIB) == []


def test_registry_case_v1_rows_still_work_as_case_facts_only():
    v1 = {"case_id": "c", "facts": {"process": "account_opening", "opening_channel": "branch"}}
    got = ids(library.applicable(LIB, v1))
    assert ("R-REMOTE-NON-DOC", 1) not in got and ("GB-STRICTER-APPLIES", 1) in got
