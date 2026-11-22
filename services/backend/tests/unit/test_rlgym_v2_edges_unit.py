"""Edge cases and slice tags (work package 2.12): activation checks, minimums, and the four parts of a new case kind.
No database."""

import sys

import pytest

from anvil.config import ROOT
from anvil.rlgym.catalog import inbox, templates
from anvil.rlgym.common import GymError

sys.path.insert(0, str(ROOT / "services/stubs"))
import golden_kyc as g  # noqa: E402


def test_v11_edge_cases_pass_and_each_rule_is_enforced():
    doc = g.template(g.EDGES_VERSION)
    assert templates._edge_case_checks(doc)[0]["ok"]
    assert (
        templates._edge_case_checks(g.template(g.BLOCKS_VERSION)) == []
    )  # no edge cases: no check
    bad = {**doc, "edge_cases": [dict(e) for e in doc["edge_cases"]]}
    bad["edge_cases"][0]["expected_outcome"] = {}
    bad["edge_cases"][1]["minimum"] = None
    bad["edge_cases"][2]["complexity"] = "trivial"
    bad["edge_cases"].append(dict(bad["edge_cases"][3]))
    reasons = " | ".join(templates._edge_case_checks(bad)[0]["reasons"])
    for needle in (
        "screening_hit: expected outcome needs a recommendation",
        "minor_without_tin: minimum cases",
        "complexity 'trivial' is not in the template's S1 list",
        "address_mismatch: duplicate edge-case tag",
    ):
        assert needle in reasons, reasons


def test_minimum_is_summed_over_products():
    assert templates.edge_minimum({"minimum": {"a": 5, "b": 7}}) == 12
    assert templates.edge_minimum({"minimum": 9}) == 9


def test_a_new_case_kind_needs_all_four_parts():
    with pytest.raises(GymError) as missing:
        inbox.edge_case_parts({"scenario_context": "x", "twist": "y"})
    assert set(missing.value.details["missing"]) == {
        "expected_outcome",
        "slice_tags.complexity",
        "slice_tags.archetype",
    }
    ok = inbox.edge_case_parts(
        {
            "scenario_context": " A trust applies. ",
            "twist": "A beneficiary is listed.",
            "expected_outcome": "escalate",
            "slice_tags": {"complexity": "judgement", "archetype": "sanctions_near_match"},
        }
    )
    assert ok["scenario_context"] == "A trust applies." and ok["rationale"] is None


def test_only_v11_task_packages_carry_slice_tags():
    v10 = g.forge_tasks("e", template_version=g.BLOCKS_VERSION)
    v11 = g.forge_tasks("e", template_version=g.EDGES_VERSION)
    assert "complexity" not in v10[0]["package"]["private"]
    assert {t["package"]["private"]["complexity"] for t in v11} == set(g.SLICE_LISTS["complexity"])
    assert all("archetype" not in t["package"]["actor"] for t in v11)


def test_a_structured_recipe_counts_as_a_recipe():
    """Studio sends recipes as structured conditions; validate accepts them (a missing or empty one is refused)."""
    doc = g.template(g.EDGES_VERSION)
    edges = [dict(e) for e in doc["edge_cases"]]
    edges[0]["recipe"] = [
        {"collection": "documents", "field": "kind", "op": "equals", "value": "screening_result"}
    ]
    edges[1]["recipe"] = []
    reasons = templates._edge_case_checks({**doc, "edge_cases": edges})[0]["reasons"]
    assert reasons == ["minor_without_tin: no generator recipe, so its data cannot be asked for"]
    from anvil.rlgym.suites import service as suites

    assert suites._recipe_text(edges[0]["recipe"]).startswith("Cases matching: [")
