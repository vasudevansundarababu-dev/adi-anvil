import copy
import hashlib
import json

import pytest

from anvil.config import ROOT
from anvil.praxis_executable import TaskV3, actor_view, parse
from anvil.praxis_export import parse_export

GOLDEN = ROOT / "contracts/praxis/golden-v3"


@pytest.mark.parametrize("path", sorted(GOLDEN.glob("*.export.json")), ids=lambda p: p.stem)
def test_golden_roundtrip_private_projection_and_independent_rule_cases(path):
    from scripts.verify_golden_imports import evaluator

    raw, envelope = parse_export(path.read_bytes())
    task = parse(raw)
    assert hashlib.sha256(raw).hexdigest() == envelope.payload_sha256
    public = json.dumps(actor_view(task), sort_keys=True)
    assert task.evaluation_private.canary not in public
    assert "evaluation_private" not in public and "expected_reward_bps" not in public
    assert '"probe"' not in public and '"examples"' not in public
    data = json.loads(task.inputs[0].content)
    evaluate = evaluator()
    observed_by_rule = {rule.id: set() for rule in [*task.criteria, *task.constraints]}
    for fixture in task.evaluation_private.fixtures:
        outcome = evaluate(
            task.domain, data, fixture.output, [c.model_dump() for c in fixture.observed_calls]
        )
        assert outcome["reward_bps"] == fixture.expected_reward_bps
        for key, expected in fixture.expected_checks.items():
            assert outcome["checks"][key] == expected
            observed_by_rule[key].add(expected)
    assert all(values == {True, False} for values in observed_by_rule.values())


def source():
    return json.loads(next(GOLDEN.glob("*.task.json")).read_text())


@pytest.mark.parametrize(
    "kind",
    [
        "traversal",
        "hash",
        "duplicate_id",
        "weights",
        "unknown_tool",
        "unknown_rule",
        "budget_override",
        "nonfinite",
        "duplicate_key",
        "image_url",
        "embedded_credentials",
        "invalid_asset_json",
    ],
)
def test_malformed_or_authority_overriding_source_rejects(kind):
    body = copy.deepcopy(source())
    if kind == "traversal":
        body["inputs"][0]["path"] = "../escape.json"
    elif kind == "hash":
        body["inputs"][0]["content"] += "tampered"
    elif kind == "duplicate_id":
        body["criteria"][0]["id"] = body["constraints"][0]["id"]
    elif kind == "weights":
        body["criteria"][0]["weight_bps"] += 1
    elif kind == "unknown_tool":
        body["constraints"][0]["prohibited_tools"] = ["unregistered_tool"]
    elif kind == "unknown_rule":
        body["evaluation_private"]["fixtures"][0]["covers"] = ["unregistered_rule"]
    elif kind == "budget_override":
        body["generation_cap_micro_usd"] = 100000000
    elif kind == "nonfinite":
        body["evaluation_private"]["fixtures"][0]["output"] = {"value": float("nan")}
    elif kind == "image_url":
        body["environment"]["image_reference"] = "https://registry.invalid/image"
    elif kind == "embedded_credentials":
        body["environment"]["image_reference"] = "user:password@registry.invalid/image"
    elif kind == "invalid_asset_json":
        body["inputs"][0]["content"] = '{"x":1,"x":2}'
        body["inputs"][0]["sha256"] = hashlib.sha256(
            body["inputs"][0]["content"].encode()
        ).hexdigest()
    if kind == "duplicate_key":
        raw = json.dumps(body).replace('"domain":', '"domain":"marketing","domain":', 1)
    else:
        raw = json.dumps(body)
    with pytest.raises(ValueError):
        parse(raw.encode())


def test_written_only_source_does_not_require_praxis_to_supply_generated_fixtures():
    body = source()
    body.pop("evaluation_private")
    task = TaskV3.model_validate(body)
    assert task.evaluation_private is None
    assert "evaluation_private" not in actor_view(task)
