"""New complete-population integrity gates; no real QA qualification issued."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_marketing_source_population import proposal
from test_marketing_world_registry import Connection, setup

from anvil.marketing_world_definition import definition
from anvil.marketing_world_population import decode_sources
from anvil.marketing_world_registry import load
from anvil.praxis_generic_contract import canonical, digest


def test_population_is_stable_after_actual_canonical_json_roundtrip():
    value, _, _ = proposal()
    parsed = definition(json.loads(canonical(value)))
    assert digest(parsed.model_dump(mode="json")) == digest(value)
    assert len(parsed.controller(0)._initial["questions"]) == 4024


def test_reviewer_answer_path_cannot_enter_public_source_population():
    value, _, _ = proposal()
    documents = deepcopy(value["population_source_documents"])
    documents["reviewer_only/expected-answer.json"] = ["not-valid-source"]
    with pytest.raises(ValueError, match="public-only"):
        decode_sources(value["case_id"], documents, value["source_hashes"])


@pytest.mark.parametrize("collection", ["products", "questions", "campaigns"])
def test_operator_row_cannot_replace_or_supplement_the_verified_virtual_population(collection):
    value, _, _ = proposal()
    row = deepcopy(value["records"]["documents"][0])
    value["records"][collection] = [row]
    value["public_columns"][collection] = sorted(set(value["public_columns"][collection]) | set(row["public"]))
    with pytest.raises(ValueError, match="Virtual populations"):
        definition(value)


def test_fake_branch_marker_cannot_be_used_in_source_complete_world():
    value, _, _ = proposal()
    value["records"]["work"][0]["public"]["id"] = "manufactured-branch-marker"
    with pytest.raises(ValueError, match="no manufactured branch markers"):
        definition(value)


def packet(monkeypatch, *, complete):
    _, _, row, plan = setup(monkeypatch)
    value, _, _ = proposal()
    row["value"]["source"].update(definition=value, definition_sha256=digest(value))
    receipt = row["value"]["qualification"]["receipt"]
    receipt.update(schema_version="anvil.marketing-private-world-qualification.v3" if complete else "anvil.marketing-private-world-qualification.v2",
                   definition_sha256=digest(value), rights_receipt_sha256=value["rights_receipt_sha256"],
                   operator_program_id=value["operator_program_id"], operator_program_sha256=value["operator_program_sha256"])
    for name in ("opening_plan_before_feedback", "opening_twelve_review_reconstruction") + (("complete_original_source_population",) if complete else ()):
        receipt["controls"][name] = {"status": "passed", "evidence_sha256": "1" * 64}
    row["value"]["qualification"]["receipt_sha256"] = digest(receipt)
    plan["config"]["marketing_native_binding"].update(
        case_assignment={"case_id": value["case_id"], "snapshot_sha256": value["case_snapshot_sha256"]},
        execution_sha256=value["execution_sha256"], fixture_manifest_sha256=value["fixture_manifest_sha256"],
        task_id=value["campaign_context"]["task_id"], revision_id=value["campaign_context"]["revision_id"])
    return row, plan


def test_partial_source_qualification_cannot_admit_complete_population_program(monkeypatch):
    row, plan = packet(monkeypatch, complete=False)
    with pytest.raises(RuntimeError, match="independently_qualified"):
        load(Connection([row]), SimpleNamespace(job_id="job", lease_token="lease", plan_id="plan"), plan)


def test_exact_manufactured_v3_controls_select_only_the_source_complete_candidate(monkeypatch):
    row, plan = packet(monkeypatch, complete=True)
    world, _, _ = load(Connection([row]), SimpleNamespace(job_id="job", lease_token="lease", plan_id="plan"), plan)
    assert world.schema_version == "anvil.marketing-private-world-definition.v6"
    assert not hasattr(world, "native_qualified")
