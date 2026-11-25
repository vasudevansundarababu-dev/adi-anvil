"""D-063 (G7): a data plan split by completeness builds equal-share cells. They were stored with quota_kind 'share',
which suites.data_plan_cells' CHECK (count, percent) rejects, so the plan could never be saved. An equal share is a
fixed number of cases: the cells are 'count' cells. Other splits are unchanged."""

import re
from pathlib import Path

from anvil.rlgym.suites import service as suites

ROWS = [
    {
        "case_id": f"{t}-{c}-{i}",
        "application_type": t,
        "completeness": c,
        "edge_cases": [],
        "edge_families": [],
    }
    for t in ("individual", "custodial")
    for c in ("complete", "incomplete")
    for i in range(4)
]
PLAN = {
    "sample_size": 8,
    "completeness_quotas": {"complete": 50, "incomplete": 50},
    "required_edges": {"passport_only": 1},
    "sampling_seed": 3,
    "missing_policy": "use_available",
}
ALLOWED = set(
    re.search(
        r"quota_kind text NOT NULL CHECK \(quota_kind IN \(([^)]*)\)\)",
        (Path(__file__).resolve().parents[2] / "migrations/041_rlgym_suites.sql").read_text(),
    )
    .group(1)
    .replace("'", "")
    .split(",")
)


def test_the_constraint_allows_count_and_percent():
    assert ALLOWED == {"count", "percent"}


def test_every_split_builds_cells_the_table_accepts():
    for by in (
        ["completeness"],
        ["application_type", "completeness"],
        ["completeness", "edge_family"],
        ["edge_case"],
        ["application_type"],
    ):
        cells = suites.compute_cells(
            {**PLAN, "stratify_by": by},
            {
                "_rows": ROWS,
                "cells": {"individual|complete": 4},
                "dimensions": {"application_type": {"individual": 8, "custodial": 8}},
            },
        )
        assert cells, by
        assert {c["quota_kind"] for c in cells} <= ALLOWED, by


def test_completeness_split_cells_are_counts_of_their_equal_share():
    cells = suites.compute_cells({**PLAN, "stratify_by": ["completeness"]}, {"_rows": ROWS})
    shares = [c for c in cells if not c["cell_key"].startswith("edge:")]
    assert {c["quota_kind"] for c in shares} == {"count"}
    assert sum(c["quota"] for c in shares) == 8
    assert all(c["quota_value"] == c["quota"] for c in shares)
