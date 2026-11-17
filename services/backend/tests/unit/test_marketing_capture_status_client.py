"""One-attempt client policy with MockTransport; NO real TLS/native evidence."""

import asyncio
from datetime import datetime, timezone
from time import monotonic

import httpx
import pytest
from test_marketing_capture_status import packet, sign

from anvil import marketing_capture_status_client as client
from anvil.marketing_capture_status import PATH, RESPONSE_CAP
from anvil.praxis_generic_contract import canonical


class Body(httpx.AsyncByteStream):
    def __init__(self, parts, *, delay=0):
        self.parts, self.delay = parts, delay

    async def __aiter__(self):
        for part in self.parts:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield part


def setup(*, status=200, changes=None, parts=None, headers=None, delay=0):
    enrollment, value, key, _, _ = packet(now=datetime.now(timezone.utc))
    if changes:
        value.update(changes)
    raw = canonical(value)
    calls = []

    def handler(request):
        calls.append(request)
        response_headers = {"content-type": "application/json"} | (headers or {})
        return httpx.Response(status, headers=response_headers, stream=Body([raw] if parts is None else parts, delay=delay))

    return enrollment, sign(enrollment, key), raw, calls, httpx.MockTransport(handler)


def test_direct_client_uses_exact_origin_path_signature_and_retains_response_but_labels_mock_unqualified(monkeypatch):
    enrollment, signed, raw, calls, transport = setup()
    created = []
    actual = httpx.AsyncClient

    def construct(**kwargs):
        created.append(kwargs)
        return actual(**kwargs)

    monkeypatch.setattr(client.httpx, "AsyncClient", construct)
    monkeypatch.setenv("HTTPS_PROXY", "http://must-never-be-used.invalid")
    result = client.read(enrollment, signed, absolute_deadline=monotonic() + 60, transport=transport)
    assert len(calls) == 1 and str(calls[0].url) == "https://anvil-qa.adi-labs.ai" + PATH
    assert calls[0].method == "GET" and calls[0].content == b""
    assert calls[0].headers["x-anvil-capture-attestation"] == signed
    assert calls[0].headers["accept-encoding"] == "identity"
    assert created[0]["trust_env"] is False and created[0]["follow_redirects"] is False
    assert created[0]["verify"] is True  # Mock branch only, not actual TLS proof.
    assert result.raw_body == raw and result.response_headers and result.request_headers
    assert result.origin == "software_mock_unqualified" and result.tls_certificate_sha256 is None
    assert "x-anvil-capture-attestation" not in repr(result).lower()


@pytest.mark.parametrize("status", [301, 302, 307, 401, 500])
def test_redirect_or_error_has_one_attempt_no_followup_or_ready(status):
    enrollment, signed, _, calls, transport = setup(status=status, headers={"location": "https://other.invalid/status"})
    with pytest.raises(client.ReadUnknown) as error:
        client.read(enrollment, signed, absolute_deadline=monotonic() + 60, transport=transport)
    assert len(calls) == 1 and error.value.response_headers


@pytest.mark.parametrize("boundary", ["oversize", "encoding", "extra", "truncated"])
def test_unbounded_noncanonical_unknown_or_partial_status_never_becomes_a_seal_input(boundary):
    options = {}
    if boundary == "oversize":
        options["parts"] = [b"x" * (RESPONSE_CAP + 1)]
    elif boundary == "encoding":
        options["headers"] = {"content-encoding": "gzip"}
    elif boundary == "extra":
        options["changes"] = {"caller_claimed_ready": True}
    else:
        options["parts"] = [b'{"incomplete":']
    enrollment, signed, _, calls, transport = setup(**options)
    with pytest.raises(client.ReadUnknown):
        client.read(enrollment, signed, absolute_deadline=monotonic() + 60, transport=transport)
    assert len(calls) == 1


def test_authenticated_nonready_read_is_an_observation_not_a_seal_or_repair():
    enrollment, signed, _, calls, transport = setup(changes={"state": "materialization_unknown", "descriptor": None})
    result = client.read(enrollment, signed, absolute_deadline=monotonic() + 60, transport=transport)
    assert len(calls) == 1 and result.status["state"] == "materialization_unknown"
    assert result.status["capture_accepted"] is False and result.status["native_qualified"] is False
    with pytest.raises(ValueError, match="Reserved or unknown"):
        client.bind_reference({}, result.raw_body, enrollment, quiescence={})


def test_client_refuses_to_consume_original_physical_cleanup_reserve_before_any_request():
    enrollment, signed, _, calls, transport = setup()
    with pytest.raises(ValueError, match="cleanup reserve"):
        client.read(enrollment, signed, absolute_deadline=monotonic() + 10, transport=transport)
    assert not calls


def test_slow_stream_has_one_total_original_deadline_instead_of_resetting_per_chunk():
    enrollment, signed, _, calls, transport = setup(parts=[b"", b"", b""], delay=0.1)
    start = monotonic()
    with pytest.raises(client.ReadUnknown):
        client.read(enrollment, signed, absolute_deadline=start + 10.05, transport=transport)
    assert len(calls) == 1 and monotonic() - start < 1


def test_complete_operation_binding_is_checked_not_only_nominal_descriptor_size():
    enrollment, status, _, now, _, quiescence = packet(include_quiescence=True)
    binding = {"original_identity": {"enrollment_id": enrollment["enrollment_id"], "scope": enrollment["scope"]},
               "quoted": '🦉 "quoted"\\value'}
    raw = client.bind_reference(binding, canonical(status), enrollment, quiescence=quiescence, now=now)
    import json

    value = json.loads(raw)
    assert len(raw) <= 4096 and value["api_evidence"]["manifest_id"] == status["manifest_id"]
    assert "api_evidence" not in binding
    with pytest.raises(ValueError):
        client.bind_reference(binding | {"large": "x" * 4096}, canonical(status), enrollment, quiescence=quiescence, now=now)
    with pytest.raises(ValueError, match="without replacement"):
        client.bind_reference(value, canonical(status), enrollment, quiescence=quiescence, now=now)


@pytest.mark.parametrize("field", ["quiescence_id", "graph_ledger_sha256", "reconstruction_sha256"])
def test_same_scope_ready_content_cannot_substitute_for_independent_original_quiescence(field):
    enrollment, status, _, now, _, quiescence = packet(include_quiescence=True)
    from uuid import uuid4

    from anvil.praxis_generic_contract import digest

    quiescence[field] = str(uuid4()) if field == "quiescence_id" else "f" * 64
    quiescence.pop("receipt_sha256")
    quiescence["receipt_sha256"] = digest(quiescence)
    with pytest.raises(ValueError, match="independent original quiescence"):
        client.bind_reference({}, canonical(status), enrollment, quiescence=quiescence, now=now)
