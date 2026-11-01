import pytest

from anvil import workspace_costs as costs
from anvil.workspace_execution import required_cost


def test_managed_rates_are_exact_expiring_and_do_not_use_a_fake_zero_default():
    row = {
        "provider_key": "openai",
        "model_id": "gpt-6-luna",
        "config": {"workspace_pricing": {"fake": True}},
    }
    price = costs.for_model(row)
    assert price["input_micro_usd_per_million_tokens"] == 100000
    assert price["output_micro_usd_per_million_tokens"] == 500000
    assert price["model_id"] == row["model_id"] and price["cache_ttl"] == "30m"
    assert costs.current(price)
    assert not costs.current({**price, "expires_at": "2020-01-01T00:00:00Z"})
    assert costs.managed("anthropic", "gpt-6-luna") is None
    assert costs.managed("openai", "gpt-6-luna-any-alias") is None
    assert costs.for_model({**row, "model_id": "unknown", "config": {}}) is None


def test_cache_partitions_and_rounding_fit_the_reserved_conservative_bound():
    for model in costs.RATES:
        price = costs.managed("openai", model)
        bound = required_cost({"pricing": price, "max_output_tokens": 2048, "max_calls": 1})
        for cached, writes in ((0, 0), (33792, 0), (0, 33792), (10000, 20000)):
            usage = {
                "input_tokens_details": {"cached_tokens": cached, "cache_write_tokens": writes}
            }
            assert costs.billed_cost(price, usage, 33792, 2048) <= bound
    price = costs.managed("openai", "gpt-6-luna")
    assert (
        costs.billed_cost(
            price, {"input_tokens_details": {"cached_tokens": 3, "cache_write_tokens": 2}}, 10, 20
        )
        == 11
    )
    assert (
        costs.billed_cost(
            price, {"input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}}, 1, 0
        )
        == 1
    )


@pytest.mark.parametrize(
    "details",
    [
        None,
        {},
        {"cached_tokens": True, "cache_write_tokens": 0},
        {"cached_tokens": -1, "cache_write_tokens": 0},
        {"cached_tokens": 6, "cache_write_tokens": 5},
        {"cached_tokens": 0, "cache_write_tokens": 0, "audio_tokens": 2},
    ],
)
def test_unknown_or_invalid_usage_is_never_a_free_success(details):
    with pytest.raises(ValueError):
        costs.billed_cost(
            costs.managed("openai", "gpt-6-luna"), {"input_tokens_details": details}, 10, 20
        )
