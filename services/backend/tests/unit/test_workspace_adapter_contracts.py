import httpx
import pytest

from anvil.providers import ActorRequest
from anvil.workspace_adapter_contracts import (
    ContractBlocked,
    bytes_echo,
    contains_secret,
    execute_mock,
)


def test_contract_rejects_real_transport_before_database_or_secret_access():
    with pytest.raises(ContractBlocked, match="mock_transport_required"):
        execute_mock(
            None,
            "invalid",
            {},
            ActorRequest(model="test", actor_text="Actor only", max_output_tokens=1),
            transport=httpx.HTTPTransport(),
        )


def test_credential_echo_checks_nested_keys_values_and_json_escaping():
    key = 'test-only-key-"\\-redaction'
    assert contains_secret({"nested": [{"value": key}]}, key)
    assert contains_secret({key: 1}, key)
    assert not contains_secret({"nested": [None, 123, "ordinary output"]}, key)
    import json

    assert bytes_echo(json.dumps({"output": key}).encode(), key)
    assert bytes_echo(("malformed-prefix " + json.dumps(key)).encode(), key)
    from urllib.parse import quote

    assert contains_secret({"header": quote(key, safe="")}, key)
    assert bytes_echo(("[" * 2000 + "0" + "]" * 2000).encode(), key)


def test_unsafe_sdk_environment_is_rejected_before_database(monkeypatch):
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", "authorization: Bearer unrelated-test-key")
    with pytest.raises(ContractBlocked, match="sdk_environment_override"):
        execute_mock(
            None,
            "invalid",
            {},
            ActorRequest(model="test", actor_text="Actor only", max_output_tokens=1),
            transport=httpx.MockTransport(lambda req: None),
        )
