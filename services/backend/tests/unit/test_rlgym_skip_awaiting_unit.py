"""Sampling skips cases whose reference can't be graded (run 3, 25 Nov 2026: kj-e568837d5d, awaiting the SME, was
sampled into a 40-case suite and every run reported it as not graded). With a gradability check, each selected case
(tagged or not) whose reference is awaiting is replaced by another case of its cell, and the skipped ids are reported
apart from cases without a reference. awaiting_pm counts as gradable only in a test-only project (placeholder
grading); awaiting_sme never does."""

import inspect

from test_rlgym_d059_untagged_unit import CATALOG, PLAN, ROWS, TASKS

from anvil.rlgym.runs import sampling
from anvil.rlgym.runs import service as runs
from anvil.rlgym.suites import cases as suite_cases
from anvil.rlgym.suites import service as suites


def test_an_awaiting_case_is_replaced_and_reported():
    cells = suites.compute_cells(PLAN, CATALOG)
    first, _, base_short = sampling.select_cases(PLAN, cells, ROWS, TASKS)
    awaiting = {first[0]["case_id"]}
    asked, skipped = [], []

    def gradable(ids):
        asked.append(list(ids))
        return {i for i in ids if i not in awaiting}

    picked, counts, short, excluded = sampling.select_checked(
        PLAN, cells, ROWS, TASKS, lambda ids: set(ids), gradable_for=gradable, skipped=skipped
    )
    assert skipped == sorted(awaiting)
    assert excluded == []  # no case lacked a reference
    assert not awaiting & {c["case_id"] for c in picked}
    assert len(picked) == len(first) and short == base_short  # replaced within its cell
    flat = [i for batch in asked for i in batch]
    assert len(flat) == len(set(flat))  # each case asked once


def test_without_a_gradability_check_the_selection_is_unchanged():
    cells = suites.compute_cells(PLAN, CATALOG)
    picked = sampling.select_checked(PLAN, cells, ROWS, TASKS, lambda ids: set(ids))[0]
    assert [c["case_id"] for c in picked] == [
        c["case_id"] for c in sampling.select_cases(PLAN, cells, ROWS, TASKS)[0]
    ]


def test_the_checker_follows_the_projects_placeholder_switch():
    refs = {
        "a": {"status": "awaiting_sme", "gradable": False},
        "b": {"status": "awaiting_pm", "gradable": False},
        "c": {"status": "complete", "gradable": True},
        "d": {},  # golden KYC v8: no status
    }
    assert suite_cases.gradable_ids(refs, placeholder_ok=False) == {"c", "d"}
    assert suite_cases.gradable_ids(refs, placeholder_ok=True) == {"b", "c", "d"}


def test_case_set_and_admission_use_it():
    assert "gradable_for=" in inspect.getsource(suite_cases.case_set)
    assert "gradable_for=" in inspect.getsource(runs.admission_check)


def test_the_manifest_records_skipped_cases_only_when_there_are_any():
    src = inspect.getsource(runs._manifest)
    assert (
        '"skipped_awaiting": r["skipped_awaiting"]' in src and 'if r.get("skipped_awaiting")' in src
    )
