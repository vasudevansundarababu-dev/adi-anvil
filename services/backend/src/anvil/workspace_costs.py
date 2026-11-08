"""Server-managed standard text rates; no model-form pricing or terms ceremony.

Exact catalog rates reverified 2026-11-08 UTC; seven-day freshness. Sources:
https://developers.openai.com/api/docs/pricing
https://developers.openai.com/api/docs/guides/prompt-caching
Only exact listed model IDs/global standard processing are admitted by this catalog.
Unknown or expired support never invents a zero price or unlimited spending authority.
"""

from datetime import datetime, timedelta, timezone

SOURCE = "https://developers.openai.com/api/docs/pricing"
REFERENCE = "anvil-openai-standard-2026-11-08-v1"
VERIFIED_AT = "2026-11-08T15:25:35.450801+00:00"
EXPIRES = (datetime.fromisoformat(VERIFIED_AT) + timedelta(days=7)).isoformat()
# micro-USD per million tokens: uncached input, cached input, 30m write, output.
RATES = {
    "gpt-6-luna": (100000, 10000, 125000, 500000),
    "gpt-6-astra": (10000000, 1000000, 12500000, 50000000),
    "gpt-6.1-sol": (2000000, 100000, 2500000, 10000000),
    "gpt-6.1-terra": (1000000, 50000, 1250000, 5000000),
}


def current(price, *, now=None):
    try:
        if not price or any(
            type(price.get(key)) is not int or price[key] < 0
            for key in ("input_micro_usd_per_million_tokens", "output_micro_usd_per_million_tokens")
        ):
            return False
        return datetime.fromisoformat(price["expires_at"].replace("Z", "+00:00")) > (
            now if now is not None else datetime.now(timezone.utc)
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def managed(provider, model):
    if provider == "gemini" and model == "gemini-3.8-flash":
        return {
            "source_kind": "anvil_managed_gemini",
            "reference": "anvil-gemini-standard-2026-11-08-v1",
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "verified_at": VERIFIED_AT,
            "provider": provider,
            "model_id": model,
            "expires_at": EXPIRES,
            "input_micro_usd_per_million_tokens": 750000,
            "output_micro_usd_per_million_tokens": 3750000,
            "service_tier": "default",
        }
    if provider == "anthropic" and model == "claude-opus-5-5":
        # Global standard pricing, no cache controls admitted by the broker.
        # billed_usage rejects nonzero cache usage rather than undercounting it.
        return {
            "source_kind": "anvil_managed_anthropic",
            "reference": "anvil-anthropic-standard-2026-11-08-v1",
            "source_url": "https://platform.claude.com/docs/en/about-claude/pricing",
            "verified_at": VERIFIED_AT,
            "provider": provider,
            "model_id": model,
            "expires_at": EXPIRES,
            "input_micro_usd_per_million_tokens": 4000000,
            "output_micro_usd_per_million_tokens": 20000000,
            "service_tier": "default",
        }
    rates = RATES.get(model) if provider == "openai" else None
    if not rates:
        return None
    inputs, cached, writes, outputs = rates
    return {
        "source_kind": "anvil_managed",
        "reference": REFERENCE,
        "source_url": SOURCE,
        "verified_at": VERIFIED_AT,
        "provider": provider,
        "model_id": model,
        "expires_at": EXPIRES,
        "input_micro_usd_per_million_tokens": inputs,
        "cached_input_micro_usd_per_million_tokens": cached,
        "cache_write_micro_usd_per_million_tokens": writes,
        "output_micro_usd_per_million_tokens": outputs,
        "service_tier": "default",
        "cache_ttl": "30m",
    }


def for_model(row):
    if not row:
        return None
    return managed(row["provider_key"], row["model_id"]) or row["config"].get("workspace_pricing")


def input_bound(price):
    return max(
        price["input_micro_usd_per_million_tokens"],
        price.get("cache_write_micro_usd_per_million_tokens", 0),
    )


def billed_cost(price, usage, inputs, outputs):
    input_charge = inputs * price["input_micro_usd_per_million_tokens"]
    if price.get("source_kind") == "anvil_managed":
        details = usage.get("input_tokens_details")
        if not isinstance(details, dict):
            raise ValueError("cache_usage_unknown")
        if any(
            value not in (0, None)
            for key, value in details.items()
            if key not in ("cached_tokens", "cache_write_tokens", "cache_write_tokens_details")
        ):
            raise ValueError("unsupported_usage_components")
        cached, writes = details.get("cached_tokens"), details.get("cache_write_tokens")
        if any(type(n) is not int or n < 0 for n in (cached, writes)) or cached + writes > inputs:
            raise ValueError("cache_usage_unknown")
        breakdown = details.get("cache_write_tokens_details")
        if breakdown is not None:
            if (
                not isinstance(breakdown, dict)
                or set(breakdown) != {"ttl_30m_tokens", "ttl_12h_tokens"}
                or any(type(n) is not int or n < 0 for n in breakdown.values())
                or sum(breakdown.values()) != writes
            ):
                raise ValueError("cache_usage_unknown")
            if breakdown["ttl_12h_tokens"] or price.get("cache_ttl") != "30m":
                raise ValueError("unadmitted_cache_lifetime")
        input_charge = (
            (inputs - cached - writes) * price["input_micro_usd_per_million_tokens"]
            + cached * price["cached_input_micro_usd_per_million_tokens"]
            + writes * price["cache_write_micro_usd_per_million_tokens"]
        )
    return (
        input_charge + outputs * price["output_micro_usd_per_million_tokens"] + 999999
    ) // 1000000
