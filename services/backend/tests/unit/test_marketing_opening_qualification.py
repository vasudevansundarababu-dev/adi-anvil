"""New source-version qualification gates; receipts here are manufactured only."""

import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_marketing_activation_definition import proposal
from test_marketing_world_registry import Connection, setup

from anvil.marketing_world_opening_definition import operator_program, with_opening
from anvil.marketing_world_registry import OpeningQualification, decode_qualification, load
from anvil.praxis_generic_contract import canonical, digest


def packet(monkeypatch, *, successor=True):
    _, _, row, plan = setup(monkeypatch)
    _, previous = proposal()
    world = with_opening(previous)
    source = row["value"]["source"]
    source.update(definition=world, definition_sha256=digest(world))
    receipt = row["value"]["qualification"]["receipt"]
    receipt.update(definition_sha256=digest(world), rights_receipt_sha256=world["rights_receipt_sha256"])
    if successor:
        receipt.update(schema_version="anvil.marketing-private-world-qualification.v2",
                       operator_program_id=world["operator_program_id"], operator_program_sha256=world["operator_program_sha256"])
        for control in ("opening_plan_before_feedback", "opening_twelve_review_reconstruction"):
            receipt["controls"][control] = {"status": "passed", "evidence_sha256": "1" * 64}
    row["value"]["qualification"]["receipt_sha256"] = digest(receipt)
    native = plan["config"]["marketing_native_binding"]
    native.update(case_assignment={"case_id": world["case_id"], "snapshot_sha256": world["case_snapshot_sha256"]},
                  execution_sha256=world["execution_sha256"], fixture_manifest_sha256=world["fixture_manifest_sha256"],
                  task_id=world["campaign_context"]["task_id"], revision_id=world["campaign_context"]["revision_id"])
    return world, row, plan


def test_v5_cannot_reuse_an_older_qualification_even_with_a_matching_self_hash(monkeypatch):
    _, row, plan = packet(monkeypatch, successor=False)
    with pytest.raises(RuntimeError, match="independently_qualified"):
        load(Connection([row]), SimpleNamespace(job_id="job", lease_token="lease", plan_id="plan"), plan)


def test_explicit_v2_receipt_binds_opening_program_and_additional_independent_controls(monkeypatch):
    expected, row, plan = packet(monkeypatch)
    world, _, _ = load(Connection([row]), SimpleNamespace(job_id="job", lease_token="lease", plan_id="plan"), plan)
    assert world.operator_program_sha256 == expected["operator_program_sha256"]
    assert type(decode_qualification(row["value"]["qualification"]["receipt"])) is OpeningQualification


@pytest.mark.parametrize("control", ["opening_plan_before_feedback", "opening_twelve_review_reconstruction"])
def test_opening_receipt_requires_both_new_controls(control, monkeypatch):
    _, row, _ = packet(monkeypatch)
    receipt = deepcopy(row["value"]["qualification"]["receipt"])
    del receipt["controls"][control]
    with pytest.raises(ValueError, match="independently exercised"):
        decode_qualification(receipt)


def test_backend_operator_descriptor_matches_actual_harbor_schedule_source(monkeypatch):
    world, _, _ = packet(monkeypatch)
    execution = world["service_contract"]["execution"]
    renderer = Path(__file__).parents[2] / "src/anvil/marketing_native_renderer.py"
    tree = ast.parse(renderer.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_schedule")
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(renderer), "exec"), namespace)
    body = namespace["_schedule"]({"workflow_graph_sha256": execution["workflow_graph_sha256"]}, execution["workflow_graph"], opening=True)
    assert canonical(body) == canonical(operator_program(execution))
    assert digest(body) == world["operator_program_sha256"]
