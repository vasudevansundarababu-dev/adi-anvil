import json

from anvil.providers import Result
from anvil.workspace_execution import provider_evidence


def test_unknown_response_keeps_safe_model_id_request_id_and_cache_usage_without_text():
    result = Result(
        "completed",
        text="PRIVATE-OUTPUT",
        model_returned="gpt-6-astra",
        request_id="resp_test",
        usage={
            "input_tokens": 10,
            "output_tokens": 2,
            "input_tokens_details": {
                "cached_tokens": 0,
                "cache_write_tokens": 2,
                "cache_write_tokens_details": {"ttl_30m_tokens": 2, "ttl_12h_tokens": 0},
            },
            "raw_error": "PRIVATE-ERROR",
            "headers": {"authorization": "PRIVATE-KEY"},
        },
    )
    evidence = provider_evidence(result)
    assert evidence["model_returned"] == "gpt-6-astra"
    assert evidence["request_id"] == "resp_test"
    assert (
        evidence["token_usage"]["input_tokens_details"]["cache_write_tokens_details"][
            "ttl_30m_tokens"
        ]
        == 2
    )
    assert "PRIVATE" not in json.dumps(evidence)


def test_invalid_metadata_is_not_invented_or_copied_as_billable_usage():
    evidence = provider_evidence(
        Result(
            "execution_unknown",
            model_returned="unsafe\nvalue",
            request_id="bad request",
            usage={"input_tokens": True, "output_tokens": -1},
        )
    )
    assert evidence["model_returned"] is None and evidence["request_id"] is None
    assert evidence["token_usage"] == {}
    assert provider_evidence(None) == {}
