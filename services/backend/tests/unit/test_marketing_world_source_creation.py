"""New private source creation controls; mocked entropy, no source persistence."""

import pytest
from test_marketing_world_registry import setup

from anvil import marketing_world_registry as registry
from anvil.marketing_world_definition import definition


def test_creation_generates_private_seed_once_and_verification_never_regenerates(monkeypatch):
    body, dataset, _, _ = setup(monkeypatch)
    del body["branch_seed"]
    calls = []
    seed = "0123456789abcdef" * 4
    monkeypatch.setattr(registry.secrets, "token_hex", lambda size: calls.append(size) or seed)
    prepared = registry.new_candidate(body, dataset)
    assert calls == [32] and prepared["definition"]["branch_seed"] == seed
    assert "branch_seed" not in body
    assert registry.candidate(prepared["definition"], dataset) == prepared
    assert calls == [32]
    controller = definition(prepared["definition"]).controller(0)
    assert seed not in str(controller.capture()) and seed not in str(controller._initial)


def test_supplied_model_or_plan_seed_is_rejected_before_entropy_or_persistence(monkeypatch):
    body, dataset, _, _ = setup(monkeypatch)
    monkeypatch.setattr(
        registry.secrets,
        "token_hex",
        lambda *args: pytest.fail("Caller-selected seed cannot enter new source creation"),
    )
    with pytest.raises(ValueError, match="host-generated"):
        registry.new_candidate(body, dataset)
