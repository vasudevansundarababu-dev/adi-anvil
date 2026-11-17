"""New complete financial-read projection controls; no SQL/API execution."""

from copy import deepcopy

import pytest
from test_marketing_activation_definition import proposal
from test_marketing_world_readiness import setup

from anvil.marketing_task2_persistence import freeze
from anvil.marketing_task2_tools import execute
from anvil.marketing_world_authority import prepare as prepare_authority
from anvil.marketing_world_definition import definition
from anvil.marketing_world_finance_transition import prepare as prepare_finance
from anvil.marketing_world_financial_records import prepare_projection


def ready():
    _, value = proposal()
    world = definition(value)
    controller, execution, node, inputs, sources, *_ = setup()
    controller._initial = world.controller(0)._initial
    baseline = world.finance_book
    controller, _, proof = prepare_authority(controller, execution, node, inputs, sources, baseline)
    selected, _ = world.selected_programs(controller._outcome)
    controller = prepare_finance(controller, baseline, selected, controller._clock)
    from anvil.marketing_world_activation_definition import decode_sources

    documents = decode_sources(world.case_id, world.activation_source_documents)
    return controller, world, selected, documents, proof, execution


def test_v4_complete_financial_projection_stays_within_original_limits_and_public_scopes():
    _, value = proposal()
    world = definition(value)
    assert len(world.records["ledger"]) == 1263
    assert len(world.records["budget-envelopes"]) == 180
    assert len(world.records["budget-snapshots"]) == 6
    assert all(row.outcome_binding is None for row in world.records["ledger"])


def test_current_balance_does_not_rewrite_historical_snapshot_and_matches_reservation():
    controller, world, selected, documents, proof, execution = ready()
    before = freeze(controller)
    result = prepare_projection(controller, world.finance_source_documents, documents, selected, proof)
    assert freeze(controller) == before
    old = next(r for r in result["budget-snapshots"] if r["public"]["id"] == "GT2-R01_balance_test_request")
    assert old["public"]["active_reservations_usd_minor"] == 0
    current = result["budget-snapshots"][-1]["public"]
    assert current["active_reservations_usd_minor"] == 200000
    assert current["actual_settled_usd_minor"] == 11535890
    assert current["media_remaining_authorisable_usd_minor"] == 6609348
    controller._initial.update(result)
    observed = execute(controller, "performance", "budget_summaries.read", {"resource_ref": current["id"]}, execution)
    assert observed["status"] == "completed"
    assert observed["result"]["records"][0]["content"] == current


def test_selected_parent_ledger_replaces_only_unreleased_future_financial_records():
    controller, world, selected, documents, proof, _ = ready()
    original = {r["public"]["id"]: deepcopy(r) for r in controller._initial["ledger"]}
    result = prepare_projection(controller, world.finance_source_documents, documents, selected, proof)
    changed = [r for r in result["ledger"] if r != original[r["public"]["id"]]]
    assert len(changed) == 14
    assert all(r["released_at"] > controller._clock for r in changed)
    assert all(r["public"]["category"] == "media" for r in changed)


def test_projection_denies_unreconciled_actual_controller_finance():
    controller, world, selected, documents, proof, _ = ready()
    controller._committed += 1
    with pytest.raises(ValueError, match="disagree"):
        prepare_projection(controller, world.finance_source_documents, documents, selected, proof)
