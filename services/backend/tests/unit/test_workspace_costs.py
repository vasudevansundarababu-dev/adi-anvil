from datetime import datetime, timedelta, timezone

import pytest

from anvil import workspace_costs as costs
from anvil.workspace_execution import billed_usage, required_cost

AS_OF = datetime(2026, 11, 8, 16, tzinfo=timezone.utc)


def test_opus_standard_rates_fit_reservation_and_cache_remains_fail_closed():
    price = costs.managed("anthropic", "claude-opus-5-5")
    assert costs.current(price, now=AS_OF)
    usage = {"input_tokens": 1000, "output_tokens": 100}
    inputs, outputs = billed_usage("anthropic", usage)
    assert costs.billed_cost(price, usage, inputs, outputs) == 6000
    assert costs.billed_cost(price, usage, inputs, outputs) <= required_cost(
        {"pricing": price, "max_output_tokens": 2048, "max_calls": 1}
    )
    assert costs.managed("anthropic", "claude-opus-5-5-unknown") is None
    with pytest.raises(ValueError, match="cache"):
        billed_usage("anthropic", {**usage, "cache_read_input_tokens": 100})


def test_gemini_standard_rates_include_thinking_and_do_not_admit_mutable_alias():
    price = costs.managed("gemini", "gemini-3.8-flash")
    usage = {
        "prompt_token_count": 1000,
        "candidates_token_count": 100,
        "thoughts_token_count": 100,
        "total_token_count": 1200,
    }
    inputs, outputs = billed_usage("gemini", usage)
    assert outputs == 200
    assert costs.billed_cost(price, usage, inputs, outputs) == 1500
    assert costs.current(price, now=AS_OF)
    assert costs.managed("gemini", "gemini-flash-latest") is None


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
    assert costs.current(price, now=AS_OF)
    assert not costs.current({**price, "expires_at": "2020-01-01T00:00:00Z"}, now=AS_OF)
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


def test_documented_cache_lifetime_breakdown_prices_only_admitted_30m_writes():
    price = costs.managed("openai", "gpt-6-astra")
    usage = {
        "input_tokens_details": {
            "cached_tokens": 4000,
            "cache_write_tokens": 7000,
            "cache_write_tokens_details": {"ttl_30m_tokens": 7000, "ttl_12h_tokens": 0},
        }
    }
    assert costs.billed_cost(price, usage, 12000, 20) == 102500
    assert costs.billed_cost(price, usage, 12000, 20) <= required_cost(
        {"pricing": price, "max_output_tokens": 2048, "max_calls": 1}
    )


@pytest.mark.parametrize(
    "breakdown",
    [
        {},
        {"ttl_30m_tokens": 2},
        {"ttl_30m_tokens": True, "ttl_12h_tokens": 0},
        {"ttl_30m_tokens": -1, "ttl_12h_tokens": 3},
        {"ttl_30m_tokens": 1, "ttl_12h_tokens": 0},
        {"ttl_30m_tokens": 1, "ttl_12h_tokens": 1},
        {"ttl_30m_tokens": 2, "ttl_12h_tokens": 0, "extra": 0},
    ],
)
def test_unbalanced_unknown_or_unadmitted_cache_lifetimes_stay_blocked(breakdown):
    with pytest.raises(ValueError):
        costs.billed_cost(
            costs.managed("openai", "gpt-6-astra"),
            {
                "input_tokens_details": {
                    "cached_tokens": 0,
                    "cache_write_tokens": 2,
                    "cache_write_tokens_details": breakdown,
                }
            },
            10,
            20,
        )


@pytest.mark.parametrize(
    "provider,model",
    [
        ("openai", "gpt-6-luna"),
        ("openai", "gpt-6-astra"),
        ("openai", "gpt-6.1-sol"),
        ("openai", "gpt-6.1-terra"),
        ("anthropic", "claude-opus-5-5"),
        ("gemini", "gemini-3.8-flash"),
    ],
)
def test_verified_catalog_expires_after_existing_seven_day_window(provider, model):
    price = costs.managed(provider, model)
    verified = datetime.fromisoformat(price["verified_at"])
    expiry = datetime.fromisoformat(price["expires_at"])
    assert expiry - verified == timedelta(days=7)
    assert price["verified_at"].startswith("2026-11-08T")
    assert costs.current(price, now=verified)
    assert costs.current(price, now=expiry - timedelta(microseconds=1))
    assert not costs.current(price, now=expiry)
    assert not costs.current(price, now=expiry + timedelta(microseconds=1))
    assert not costs.current(price, now=AS_OF + timedelta(days=3650))
    assert price["provider"] == provider and price["model_id"] == model
    assert price["service_tier"] == "default"


@pytest.mark.parametrize(
    "price",
    [
        None,
        {},
        {
            "input_micro_usd_per_million_tokens": True,
            "output_micro_usd_per_million_tokens": 1,
            "expires_at": "2026-11-15T00:00:00Z",
        },
        {
            "input_micro_usd_per_million_tokens": -1,
            "output_micro_usd_per_million_tokens": 1,
            "expires_at": "2026-11-15T00:00:00Z",
        },
        {
            "input_micro_usd_per_million_tokens": 1,
            "output_micro_usd_per_million_tokens": 1,
            "expires_at": "not-a-date",
        },
        {
            "input_micro_usd_per_million_tokens": 1,
            "output_micro_usd_per_million_tokens": 1,
            "expires_at": "2026-11-15T00:00:00",
        },
    ],
)
def test_unknown_or_invalid_freshness_metadata_remains_fail_closed(price):
    assert not costs.current(price, now=AS_OF)


def test_default_production_clock_still_enforces_actual_expiration():
    price = costs.managed("openai", "gpt-6-luna")
    actual = datetime.now(timezone.utc)
    assert not costs.current({**price, "expires_at": (actual - timedelta(days=1)).isoformat()})
    assert costs.current({**price, "expires_at": (actual + timedelta(days=1)).isoformat()})


@pytest.mark.parametrize(
    "provider,model",
    [
        ("openai", "gpt-6-sol"),
        ("openai", "gpt-6-luna-latest"),
        ("anthropic", "claude-opus-5-5-latest"),
        ("gemini", "gemini-flash-latest"),
        ("unknown", "gpt-6-luna"),
    ],
)
def test_documented_but_unlisted_and_approximate_models_never_substitute(provider, model):
    assert costs.managed(provider, model) is None
    assert costs.for_model({"provider_key": provider, "model_id": model, "config": {}}) is None
