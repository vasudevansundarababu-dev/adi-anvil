"""D-059 (T1): a suite-level option lets each task also take the untagged cases of its application type. Off by default:
every existing suite samples, matches and hashes exactly as before. On: a task takes its own tagged cases and the
untagged (clean or problem) cases of its type, never another task's tags; every untagged case needs a reference answer
from Studio's scorer, and one without is excluded and counted, never guessed."""

import inspect

from anvil.rlgym.runs import sampling
from anvil.rlgym.suites import service as suites

TASKS = [
    {
        "task_id": "t-custodial",
        "revision": 2,
        "case_selector": {
            "application_type": "custodial",
            "edge_cases": ["sanctions_dob_mismatch"],
        },
    },
    {
        "task_id": "t-individual",
        "revision": 3,
        "case_selector": {"application_type": "individual", "edge_cases": ["passport_only"]},
    },
]


def case(cid, t, completeness, tags=()):
    return {
        "case_id": cid,
        "application_type": t,
        "completeness": completeness,
        "edge_cases": list(tags),
        "edge_families": [],
    }


ROWS = (
    [case(f"c-clean-{i}", "custodial", "complete") for i in range(5)]
    + [case(f"c-problem-{i}", "custodial", "incomplete") for i in range(5)]
    + [case(f"c-sanc-{i}", "custodial", "incomplete", ["sanctions_dob_mismatch"]) for i in range(5)]
    + [case(f"c-other-{i}", "custodial", "incomplete", ["passport_only"]) for i in range(3)]
    + [case(f"c-unknown-{i}", "custodial", "incomplete", ["no_task_tag"]) for i in range(3)]
    + [case(f"i-clean-{i}", "individual", "complete") for i in range(5)]
    + [case(f"i-problem-{i}", "individual", "incomplete") for i in range(5)]
    + [case(f"i-pass-{i}", "individual", "incomplete", ["passport_only"]) for i in range(5)]
    + [case(f"x-clean-{i}", "teen_joint", "complete") for i in range(3)]
)
PLAN = {
    "sample_size": 8,
    "stratify_by": ["application_type"],
    "completeness_quotas": {"complete": 50, "incomplete": 50},
    "required_edges": {},
    "sampling_seed": 11,
    "missing_policy": "use_available",
}
ON = {**PLAN, "untagged_cases": True}
CATALOG = {
    "cells": {
        "custodial|complete": 5,
        "custodial|incomplete": 16,
        "individual|complete": 5,
        "individual|incomplete": 10,
    },
    "dimensions": {"application_type": {"custodial": 21, "individual": 15}},
}


def by_id(cid):
    return next(r for r in ROWS if r["case_id"] == cid)


# --- matching --------------------------------------------------------------------------------------------------------


def test_off_by_default_an_untagged_case_matches_no_edge_focused_task():
    assert sampling.match_task(by_id("c-clean-0"), TASKS, 11) is None
    assert sampling.match_task(by_id("c-problem-0"), TASKS, 11) is None
    assert sampling.match_task(by_id("c-clean-0"), TASKS, 11, untagged=False) is None


def test_on_a_task_takes_untagged_cases_of_its_type_clean_or_problem():
    for cid in ("c-clean-0", "c-problem-3"):
        assert sampling.match_task(by_id(cid), TASKS, 11, untagged=True)["task_id"] == "t-custodial"
    assert (
        sampling.match_task(by_id("i-clean-1"), TASKS, 11, untagged=True)["task_id"]
        == "t-individual"
    )


def test_on_a_task_never_takes_another_tasks_tag_or_a_tag_no_task_has():
    # c-other carries passport_only (the individual task's tag) on a custodial case: no custodial task has it.
    assert sampling.match_task(by_id("c-other-0"), TASKS, 11, untagged=True) is None
    assert sampling.match_task(by_id("c-unknown-0"), TASKS, 11, untagged=True) is None
    # A type no task covers stays unmatched.
    assert sampling.match_task(by_id("x-clean-0"), TASKS, 11, untagged=True) is None


def test_on_tagged_cases_still_go_to_their_own_task():
    assert (
        sampling.match_task(by_id("c-sanc-2"), TASKS, 11, untagged=True)["task_id"] == "t-custodial"
    )
    assert (
        sampling.match_task(by_id("i-pass-2"), TASKS, 11, untagged=True)["task_id"]
        == "t-individual"
    )


def test_a_plain_task_still_wins_for_untagged_cases_when_the_option_is_on():
    plain = {
        "task_id": "t-plain",
        "revision": 1,
        "case_selector": {"application_type": "custodial"},
    }
    assert sampling.match_task(by_id("c-clean-0"), TASKS + [plain], 11)["task_id"] == "t-plain"
    assert (
        sampling.match_task(by_id("c-clean-0"), TASKS + [plain], 11, untagged=True)["task_id"]
        == "t-plain"
    )


# --- selection ---------------------------------------------------------------------------------------------------------


def test_off_the_selection_is_exactly_as_before():
    cells = suites.compute_cells(PLAN, CATALOG)
    picked, counts, short = sampling.select_cases(PLAN, cells, ROWS, TASKS)
    assert all(c["edge_cases"] for c in picked)
    assert {s["cell_key"] for s in short} == {"custodial|complete", "individual|complete"}
    # The explicit False is the same as no key.
    again = sampling.select_cases({**PLAN, "untagged_cases": False}, cells, ROWS, TASKS)
    assert [c["case_id"] for c in again[0]] == [c["case_id"] for c in picked]


def test_on_the_complete_and_incomplete_quotas_fill_with_untagged_cases():
    cells = suites.compute_cells(ON, CATALOG)
    picked, counts, short = sampling.select_cases(ON, cells, ROWS, TASKS)
    assert not short
    assert len(picked) == 8
    assert counts["custodial|complete"] == 2 and counts["individual|complete"] == 2
    assert all(c["case_id"].split("-")[1] in ("clean", "problem", "sanc", "pass") for c in picked)
    specs, unmatched = sampling.expand(ON, picked, TASKS, [], [("m", 1)], 1)
    assert not unmatched and len(specs) == 8
    assert {
        s["task"]["task_id"] for s in specs if s["case"]["application_type"] == "custodial"
    } == {"t-custodial"}


def test_edge_minimums_still_count_toward_their_stratum_with_the_option_on():
    plan = {**ON, "required_edges": {"sanctions_dob_mismatch": 2, "passport_only": 2}}
    cells = suites.compute_cells(plan, CATALOG)
    picked, counts, short = sampling.select_cases(plan, cells, ROWS, TASKS)
    assert counts["edge:sanctions_dob_mismatch"] == 2 and counts["edge:passport_only"] == 2
    assert sum(1 for c in picked if "sanctions_dob_mismatch" in c["edge_cases"]) >= 2
    assert not any(c["case_id"].startswith("c-other") for c in picked)


# --- reference check -----------------------------------------------------------------------------------------------------


def test_an_untagged_case_without_a_reference_is_excluded_counted_and_replaced():
    cells = suites.compute_cells(ON, CATALOG)
    first, _, _ = sampling.select_cases(ON, cells, ROWS, TASKS)
    missing = {c["case_id"] for c in first if not c["edge_cases"]}
    asked = []

    def refs(ids):
        asked.append(list(ids))
        return {i for i in ids if i not in missing}

    picked, counts, short, excluded = sampling.select_checked(ON, cells, ROWS, TASKS, refs)
    assert set(excluded) >= missing
    assert not set(excluded) & {c["case_id"] for c in picked}
    assert all(not c["edge_cases"] for c in ROWS if c["case_id"] in excluded)
    # Tagged cases are never asked about (their references are checked as before, at start).
    assert all(by_id(i)["edge_cases"] == [] for batch in asked for i in batch)
    # Each case is asked about once.
    flat = [i for batch in asked for i in batch]
    assert len(flat) == len(set(flat))
    assert len(picked) == 8 and not short


def test_off_the_reference_check_asks_nothing():
    cells = suites.compute_cells(PLAN, CATALOG)

    def refs(ids):
        raise AssertionError("not asked when the option is off")

    picked, counts, short, excluded = sampling.select_checked(PLAN, cells, ROWS, TASKS, refs)
    assert excluded == []
    assert [c["case_id"] for c in picked] == [
        c["case_id"] for c in sampling.select_cases(PLAN, cells, ROWS, TASKS)[0]
    ]


def test_when_no_untagged_case_has_a_reference_the_cells_come_up_short_never_guessed():
    cells = suites.compute_cells(ON, CATALOG)
    picked, counts, short, excluded = sampling.select_checked(
        ON, cells, ROWS, TASKS, lambda ids: set()
    )
    assert all(c["edge_cases"] for c in picked)
    assert {s["cell_key"] for s in short} >= {"custodial|complete", "individual|complete"}
    assert len(excluded) >= 4


# --- availability per cell ---------------------------------------------------------------------------------------------


def test_each_cell_shows_how_many_tagged_and_untagged_cases_a_task_can_take():
    cells = suites.compute_cells({**ON, "required_edges": {"passport_only": 1}}, CATALOG)
    got = sampling.takeable_counts(cells, ROWS, TASKS, 11)
    assert got["custodial|complete"] == {"tagged": 0, "untagged": 5}
    # 5 sanctions cases are the custodial task's; passport_only and no_task_tag on custodial cases are not takeable.
    assert got["custodial|incomplete"] == {"tagged": 5, "untagged": 5}
    assert got["individual|incomplete"] == {"tagged": 5, "untagged": 5}
    assert got["edge:passport_only"] == {"tagged": 5, "untagged": 0}


# --- hash, plan, manifest -----------------------------------------------------------------------------------------------


def test_the_suite_hash_includes_the_option_only_when_it_is_on():
    row = {**PLAN, "case_set_name": None, "untagged_cases": False}
    off = suites.plan_content(row)
    assert "untagged_cases" not in off
    assert off == {
        k: row[k]
        for k in (
            "sample_size",
            "stratify_by",
            "completeness_quotas",
            "required_edges",
            "sampling_seed",
            "missing_policy",
        )
    }
    assert suites.plan_content({**row, "untagged_cases": True}) == {**off, "untagged_cases": True}
    # Rows read before the column existed (no key) hash the same as off.
    assert suites.plan_content({k: v for k, v in row.items() if k != "untagged_cases"}) == off


def test_the_option_is_part_of_the_plan_and_validated():
    import pytest

    from anvil.rlgym.common import GymError

    assert suites.DEFAULT_PLAN["untagged_cases"] is False
    suites.validate_plan(ON)
    with pytest.raises(GymError):
        suites.validate_plan({**ON, "untagged_cases": "yes"})


def test_the_manifest_records_the_option_and_the_excluded_cases():
    from anvil.rlgym.runs import service as runs

    src = inspect.getsource(runs._manifest)
    assert "untagged_cases" in src and "untagged_without_reference" in src
    assert "select_checked" in inspect.getsource(runs.admission_check)


def test_the_case_set_preview_makes_the_same_checked_selection():
    from anvil.rlgym.suites import cases

    src = inspect.getsource(cases.case_set)
    assert "select_checked" in src and "untagged" in src


def test_graders_are_untouched():
    from anvil.rlgym.results import scorer

    assert "untagged" not in inspect.getsource(scorer)
