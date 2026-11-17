"""New conditional-decision preparation controls; not API/runtime admission."""

from copy import deepcopy

import pytest
from test_marketing_world_finance import source as finance_source
from test_marketing_world_readiness import save, setup

from anvil.marketing_task2_persistence import freeze, restore
from anvil.marketing_world_authority import PREFIX, prepare
from anvil.marketing_world_finance import normalize
from anvil.praxis_generic_contract import canonical, digest


def book(case):
    files, pins = finance_source(case)
    return normalize(case, files, pins)


@pytest.mark.parametrize("case", ["GT2-R01", "GT2-R02"])
def test_conditional_successor_has_actual_readiness_and_parent_finance_without_mutating_original(case):
    controller, execution, node, inputs, sources, *_ = setup(case)
    before, fingerprint = freeze(controller)
    successor, public, private = prepare(controller, execution, node, inputs, sources, book(case))
    assert freeze(controller) == (before, fingerprint)
    assert public["decision"] == "approved" and public["simulation_only"] is True
    assert public["real_human_approval"] is False and public["additional_media_budget"] == 0
    assert successor._settled == 11535890 and successor._committed == 154762
    assert sum(successor._reservations.values()) == 200000
    assert private["persisted"] is False and private["readiness"]["ready"] is True
    assert private["conditional_source_sha256"] in {v["sha256"] for v in sources["source_provenance"].values()}
    encoded = canonical(public)
    assert b"reuse-test-" not in encoded and b'"branch"' not in encoded
    assert b"conditional_source_sha256" not in encoded
    assert not any(key.startswith(PREFIX) for key in controller._controller_keys)
    state, sha = freeze(successor)
    restored = restore(state, sha)
    assert freeze(restored) == (state, sha)


def test_ready_recommendation_with_unresolved_finding_is_not_controller_authority():
    finding = {"id": "F1", "mandatory": True, "check": "claims", "status": "open", "evidence_refs": []}
    controller, execution, node, inputs, sources, *_ = setup(finding=finding)
    before = freeze(controller)
    successor, public, private = prepare(controller, execution, node, inputs, sources, book(controller.case_id))
    assert successor is None and public["decision"] == "pending"
    assert public["campaign_authority_issued"] is False and private["persisted"] is False
    assert freeze(controller) == before


def test_experiment_alias_cannot_obtain_second_authority_or_reservation():
    controller, execution, node, inputs, sources, *_, content = setup()
    successor, *_ = prepare(controller, execution, node, inputs, sources, book(controller.case_id))
    alias = save(successor, "orchestrator", "approval-requests", "another-approval-name", deepcopy(content))
    before = freeze(successor)
    with pytest.raises(ValueError, match="alias, revision or replay"):
        prepare(successor, execution, node, {"approval_request": {"request_ref": alias}}, sources, book(controller.case_id))
    assert freeze(successor) == before


def test_first_daily_order_boundary_never_produces_approval_successor():
    controller, execution, node, inputs, sources, *_ = setup()
    controller.advance("2027-02-15T00:00:00Z")
    successor, public, private = prepare(controller, execution, node, inputs, sources, book(controller.case_id))
    assert successor is None and public["campaign_authority_issued"] is False
    assert any(r["code"] == "campaign_authority_not_yet_available_or_would_be_retroactive"
               for r in private["readiness"]["issues"])


def test_unreconciled_prior_controller_spend_is_not_overwritten():
    controller, execution, node, inputs, sources, *_ = setup()
    controller._settled = 17
    before = freeze(controller)
    with pytest.raises(ValueError, match="Unreconciled"):
        prepare(controller, execution, node, inputs, sources, book(controller.case_id))
    assert freeze(controller) == before


def test_other_case_book_cannot_fund_this_request():
    controller, execution, node, inputs, sources, *_ = setup()
    with pytest.raises(ValueError, match="Exact private"):
        prepare(controller, execution, node, inputs, sources, book("GT2-R02"))


def test_private_fixture_branch_does_not_change_public_approval_or_prestart_accounting():
    controller, execution, node, inputs, sources, *_ = setup()
    outcomes = []
    finance = book(controller.case_id)
    for branch in ("positive", "null", "negative"):
        controller._outcome = branch
        successor, public, _ = prepare(controller, execution, node, inputs, sources, finance)
        outcomes.append((digest(public), successor._settled, successor._committed, sum(successor._reservations.values())))
    assert len(set(outcomes)) == 1
