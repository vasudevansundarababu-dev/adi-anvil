"""D-038: the suite's edge-case list comes from the bound environment's cases. D-040: a run records where its attacks
actually reached the agent (Studio OpenEnv: always the user message). Synthetic data; no database, no registry."""

import inspect

import pytest

from anvil.rlgym import integrations
from anvil.rlgym.common import GymError
from anvil.rlgym.results import report
from anvil.rlgym.runs import service as runs
from anvil.rlgym.runs import worker
from anvil.rlgym.suites import service as suites

ROWS = [
    {"case_id": "a1", "application_type": "individual", "edge_cases": ["passport_only"]},
    {"case_id": "a2", "application_type": "individual", "edge_cases": []},
    {"case_id": "t1", "application_type": "teen_joint", "edge_cases": ["minor_without_tin"]},
    {"case_id": "c1", "application_type": "custodial", "edge_cases": ["minor_without_tin"]},
]
ENV = {
    "id": "env-d038@1",
    "registry": None,
    "case_catalog": {
        "dimensions": {
            "application_type": {"individual": 2, "teen_joint": 1, "custodial": 1},
            "edge_cases": {},
        },
        "cells": {},
    },
}


@pytest.fixture(autouse=True)
def registry(monkeypatch):
    calls = []

    def fake(path, params=None, audience=None, timeout=10, base=None):
        calls.append(path)
        return {"cases": ROWS}

    monkeypatch.setattr(integrations, "registry_get", fake)
    suites._EDGE_CACHE.clear()
    return calls


def test_edge_tags_are_counted_from_the_environment_cases(registry):
    counts = suites.edge_counts(ENV)
    assert counts == {
        "minor_without_tin": {
            "available": 2,
            "application_types": {"teen_joint": 1, "custodial": 1},
        },
        "passport_only": {"available": 1, "application_types": {"individual": 1}},
    }
    suites.edge_counts(ENV)
    assert registry == ["/versions/env-d038@1/cases"]  # read once per immutable version


def test_edge_minimum_cells_see_what_the_environment_has():
    cat = suites.with_edges(ENV)
    assert cat["dimensions"]["edge_cases"] == {"minor_without_tin": 2, "passport_only": 1}
    plan = {
        "sample_size": 4,
        "completeness_quotas": {"complete": 100},
        "required_edges": {"minor_without_tin": 1, "screening_hit": 1},
    }
    cells = {c["cell_key"]: c for c in suites.compute_cells(plan, cat)}
    assert cells["edge:minor_without_tin"]["available"] == 2
    assert cells["edge:screening_hit"]["available"] == 0  # a tag this environment doesn't have


def test_unreachable_registry_falls_back_to_the_summary(monkeypatch):
    def down(*a, **k):
        raise GymError("REGISTRY_UNAVAILABLE", "down")

    monkeypatch.setattr(integrations, "registry_get", down)
    env = {**ENV, "case_catalog": {"dimensions": {"edge_cases": {"x": 3}}}}
    assert suites.edge_counts(env) == {"x": {"available": 3, "application_types": {}}}
    assert "env-d038@1" not in suites._EDGE_CACHE  # an outage is never cached


def test_the_ui_list_is_no_longer_hard_coded():
    from anvil.config import ROOT

    src = (ROOT / "apps/web/src/components/rlgym/Suites.tsx").read_text()
    assert "'expired_id', 'screening_hit', 'address_mismatch'" not in src
    assert "data.edge_catalog" in src


class Conn:
    def __init__(self, row):
        self.row = row

    def execute(self, sql, params=None):
        row = self.row

        class R:
            def fetchone(self):
                return row

        return R()


def test_d040_delivered_placement():
    openenv_row = {"image_recipe": {"kind": "studio-openenv"}}
    m = {
        "environment": {"version_id": "golden-kyc-openenv@8"},
        "trust_and_safety": {"placement": "tool_result"},
    }
    assert report.delivered_as(Conn(openenv_row), m) == "user_message"  # runs before D-040
    assert report.delivered_as(Conn({"image_recipe": {"kind": "bridge"}}), m) == "tool_result"
    m2 = {**m, "trust_and_safety": {"placement": "tool_result", "delivered_as": "user_message"}}
    assert report.delivered_as(Conn(None), m2) == "user_message"
    assert report.delivered_as(Conn(None), {"trust_and_safety": {}}) is None


def test_d040_manifest_and_bundle_record_the_real_placement():
    assert '"delivered_as": (' in inspect.getsource(runs._manifest)
    src = inspect.getsource(worker)
    assert (
        '("tool_result" if injected_at else "not_delivered")' in src
    )  # E-006: real tool-result placement
    assert '("user_message" if on_openenv else inject["placement"])' in src
    assert '"requested_placement": inject["placement"]' in src
