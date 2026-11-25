"""Spec §16 (owner): ONE KYC Judgment task covers all four account types. A task's case_selector may name a list of
application types; the task then takes cases of each, the data plan stratifies by application type within the one
task, and labels name every type. A single-type selector (v8) behaves exactly as before."""

from anvil.rlgym.runs import sampling
from anvil.rlgym.suites import service as suites

ONE = {
    "task_id": "t-judgment",
    "revision": 1,
    "case_selector": {"application_type": ["individual", "adult_joint", "custodial", "teen_joint"]},
}
V8 = {
    "task_id": "t-v8",
    "revision": 1,
    "case_selector": {"application_type": "custodial", "edge_cases": ["x"]},
}


def case(cid, t, tags=()):
    return {
        "case_id": cid,
        "application_type": t,
        "completeness": "incomplete",
        "edge_cases": list(tags),
        "edge_families": [],
    }


def test_selector_types():
    assert sampling.selector_types(ONE["case_selector"]) == {
        "individual",
        "adult_joint",
        "custodial",
        "teen_joint",
    }
    assert sampling.selector_types(V8["case_selector"]) == {"custodial"}
    assert sampling.selector_types({}) == set()


def test_one_task_takes_cases_of_every_type_it_names():
    for t in ("individual", "adult_joint", "custodial", "teen_joint"):
        assert sampling.match_task(case(f"c-{t}", t), [ONE], 1)["task_id"] == "t-judgment"
    assert sampling.match_task(case("c-biz", "business"), [ONE], 1) is None


def test_a_single_type_selector_is_unchanged():
    assert sampling.match_task(case("c1", "custodial", ["x"]), [V8], 1)["task_id"] == "t-v8"
    assert sampling.match_task(case("c2", "individual", ["x"]), [V8], 1) is None


def test_the_plan_stratifies_by_type_within_the_one_task():
    catalog = {
        "cells": {
            f"{t}|{c}": 10
            for t in ("individual", "adult_joint", "custodial", "teen_joint", "business")
            for c in ("complete", "incomplete")
        },
        "dimensions": {
            "application_type": {
                t: 20 for t in ("individual", "adult_joint", "custodial", "teen_joint", "business")
            }
        },
    }
    plan = {
        **suites.DEFAULT_PLAN,
        "sample_size": 8,
        "completeness_quotas": {"complete": 50, "incomplete": 50},
    }
    cells = suites.compute_cells(
        plan, catalog, {"individual", "adult_joint", "custodial", "teen_joint"}
    )
    assert {c["dimension_values"]["application_type"] for c in cells} == {
        "individual",
        "adult_joint",
        "custodial",
        "teen_joint",
    }
    assert sum(c["quota"] for c in cells) == 8


def test_labels_name_every_type():
    assert suites.selector_label(ONE["case_selector"]).startswith(
        "individual, adult_joint, custodial, teen_joint"
    )
    assert suites.selector_label(V8["case_selector"]) == "custodial · any completeness · x"
