"""E-005 §3: split by one or two properties, a named case set, and the role-checked expected-outcome read. The default
split (application type × completeness) keeps today's cells and picks, so existing suites are unchanged."""

import pytest

from anvil.rlgym import integrations
from anvil.rlgym.common import GymError
from anvil.rlgym.runs import sampling
from anvil.rlgym.suites import cases
from anvil.rlgym.suites import service as suites

ROWS = [
    {
        "case_id": f"{t}-{tag or 'clean'}-{i}",
        "application_type": t,
        "completeness": ("complete", "incomplete")[i % 2],
        "edge_cases": [tag] if tag else [],
        "edge_families": [tag + "_family"] if tag else [],
        "facts": {"product": t},
    }
    for t in ("individual", "custodial")
    for tag in (None, "passport_only", "minor_without_tin")
    for i in range(6)
]
PLAN = {
    "sample_size": 8,
    "completeness_quotas": {"complete": 50, "incomplete": 50},
    "required_edges": {},
    "sampling_seed": 7,
    "missing_policy": "use_available",
}


def test_two_property_split_spreads_over_the_combinations_the_cases_have():
    plan = {**PLAN, "stratify_by": ["application_type", "edge_case"]}
    cells = suites.compute_cells(plan, {"_rows": ROWS})
    keys = sorted(c["cell_key"] for c in cells)
    assert "custodial|minor_without_tin|complete" in keys and "individual|none|incomplete" in keys
    assert sum(c["quota"] for c in cells) == 8
    picked, counts, short = sampling.select_cases(plan, cells, ROWS)
    assert len(picked) == 8 and not short
    again, _, _ = sampling.select_cases(plan, cells, ROWS)
    assert [c["case_id"] for c in again] == [c["case_id"] for c in picked]


def test_completeness_as_a_split_property_gets_equal_shares():
    plan = {**PLAN, "stratify_by": ["completeness"]}
    cells = suites.compute_cells(plan, {"_rows": ROWS})
    assert {c["cell_key"]: c["quota"] for c in cells} == {"complete": 4, "incomplete": 4}


def test_default_split_is_unchanged():
    catalog = {
        "dimensions": {"application_type": {"individual": 18, "custodial": 18}},
        "cells": {
            "individual|complete": 9,
            "individual|incomplete": 9,
            "custodial|complete": 9,
            "custodial|incomplete": 9,
        },
    }
    plan = {**PLAN, "stratify_by": ["application_type"]}
    cells = suites.compute_cells(plan, catalog)
    assert sorted(c["cell_key"] for c in cells) == [
        "custodial|complete",
        "custodial|incomplete",
        "individual|complete",
        "individual|incomplete",
    ]


@pytest.mark.parametrize(
    "bad",
    [
        {"stratify_by": ["a", "b", "c"]},
        {"stratify_by": ["edge_case", "edge_case"]},
        {"stratify_by": ["shoe_size"]},
        {"case_set_name": ""},
        {"case_set_name": "x" * 81},
    ],
)
def test_plan_validation(bad):
    with pytest.raises(GymError):
        suites.validate_plan({**PLAN, **bad})
    suites.validate_plan(
        {**PLAN, "stratify_by": ["edge_family", "product"], "case_set_name": "KYC set A"}
    )


class Actor:
    id = "u-1"
    kind = "person"

    def __init__(self, profile):
        self.profile = profile

    def require_person(self):
        pass


def test_only_rl_engineers_and_admins_see_expected_outcomes_and_each_read_is_audited(monkeypatch):
    monkeypatch.setattr(cases, "_sv_env", lambda c, ws, sv: ({}, {"id": "env@8", "registry": None}))
    sent, audits = [], []
    monkeypatch.setattr(
        integrations,
        "registry_get",
        lambda path, **kw: sent.append((path, kw)) or {"reference": {"x": 1}},
    )
    monkeypatch.setattr(cases, "audit", lambda *a, **k: audits.append(a[3]))

    class Ctx:
        c, ws = None, "ws"

    ctx = Ctx()
    ctx.actor = Actor("viewer")
    with pytest.raises(GymError) as e:
        cases.case_detail(ctx, "sv", "case-1")
    assert e.value.code == "FORBIDDEN" and not sent
    ctx.actor = Actor("rl_engineer")
    out = cases.case_detail(ctx, "sv", "case-1")
    assert out["read_only"] is True and out["reference"] == {"x": 1}
    headers = sent[0][1]["headers"]
    assert headers["X-ADI-Audience"] == "engineer" and headers["X-ADI-Viewer-Role"] == "rl_engineer"
    assert audits == ["case.expected_outcome_viewed"]


def test_request_variant_is_inside_a_family_never_sets_an_outcome_and_is_audited(monkeypatch):
    monkeypatch.setattr(cases, "_sv_env", lambda c, ws, sv: ({}, {"id": "golden-kyc-openenv@8"}))
    monkeypatch.setattr(cases, "_env_key", lambda c, env_id: "golden-kyc-openenv")
    posted, audits = [], []
    monkeypatch.setattr(
        integrations,
        "registry_post",
        lambda path, body, headers=None, timeout=15: (
            posted.append((path, body, headers)) or {"inbox_item_id": "ib-1"}
        ),
    )
    monkeypatch.setattr(cases, "audit", lambda *a, **k: audits.append(a[3]))

    class Ctx:
        c, ws = None, "ws"

    ctx = Ctx()
    body = {
        "family_id": "expired_id",
        "kind": "boundary",
        "name": "Expires today",
        "reason": "boundary",
        "products": ["individual"],
    }
    ctx.actor = Actor("viewer")
    with pytest.raises(GymError):
        cases.request_variant(ctx, "sv", body, "k-1")
    ctx.actor = Actor("rl_engineer")
    with pytest.raises(GymError) as e:
        cases.request_variant(ctx, "sv", {**body, "outcome": {"recommendation": "x"}}, "k-1")
    assert e.value.code == "FORBIDDEN"
    out = cases.request_variant(ctx, "sv", body, "k-1")
    path, sent, headers = posted[0]
    assert path == "/environments/golden-kyc-openenv/edge-case-variants" and headers == {
        "Idempotency-Key": "k-1"
    }
    assert sent["family_id"] == "expired_id" and "outcome" not in sent
    assert (
        sent["proposed_by"]["role"] == "rl_engineer" and sent["proposed_by"]["request_id"] == "k-1"
    )
    assert out == {"inbox_item_id": "ib-1"} and audits == ["edge_variant.requested"]
