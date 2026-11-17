"""Bounded parser/file controls with manufactured streams, never live TLS."""

import asyncio
import hashlib
from time import monotonic
from types import SimpleNamespace

import httpx
import pytest

from anvil import marketing_capture_status_client as client


def exchange(monkeypatch, raw):
    calls = []

    class Writer:
        closed = False

        def write(self, body):
            calls.append(body)

        async def drain(self):
            pass

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    writer = Writer()

    async def connect(*args, **kwargs):
        assert args == ("anvil-qa.adi-labs.ai", 443)
        assert kwargs["limit"] == client.HEADER_CAP
        assert kwargs["server_hostname"] == "anvil-qa.adi-labs.ai"
        reader = asyncio.StreamReader(limit=kwargs["limit"])
        reader.feed_data(raw)
        reader.feed_eof()
        return reader, writer

    monkeypatch.setattr(client.asyncio, "open_connection", connect)

    async def run():
        transport = client._BoundedTLS(object(), monotonic() + 2)
        request = httpx.Request("GET", "https://anvil-qa.adi-labs.ai" + client.PATH)
        response = await transport.handle_async_request(request)
        body = await response.aread()
        assert writer.closed
        with pytest.raises(ValueError, match="Only one"):
            await transport.handle_async_request(request)
        return body

    return run, calls, writer


def test_raw_header_limit_precedes_field_parser_and_has_one_fixed_request(monkeypatch):
    run, calls, _ = exchange(monkeypatch, b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}")
    assert asyncio.run(run()) == b"{}"
    assert len(calls) == 1 and b"Connection: close\r\n" in calls[0]


@pytest.mark.parametrize("raw", [
    b"HTTP/1.1 200 OK\r\nX-Large: " + b"x" * 8192 + b"\r\nContent-Length: 2\r\n\r\n{}",
    b"HTTP/1.1 301 Moved\r\nContent-Length: 2\r\n\r\n{}",
    b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}",
    b"HTTP/1.1 200 OK\r\nContent-Length: 8193\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n{}",
    b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\n{}",
    b"HTTP/1.1 200 OK\r\nBad Header: value\r\nContent-Length: 2\r\n\r\n{}",
])
def test_oversize_redirect_ambiguous_or_partial_wire_is_closed_without_retry(monkeypatch, raw):
    run, calls, writer = exchange(monkeypatch, raw)
    with pytest.raises((ValueError, asyncio.LimitOverrunError)):
        asyncio.run(run())
    assert len(calls) == 1 and writer.closed


@pytest.mark.parametrize("kind", ["symlink", "oversize", "hash", "deadline"])
def test_ca_source_is_regular_bounded_pinned_and_under_original_cutoff(monkeypatch, tmp_path, kind):
    path = tmp_path / "bundle.pem"
    path.write_bytes(b"not a certificate")
    if kind == "symlink":
        link = tmp_path / "substituted.pem"
        link.symlink_to(path)
        path = link
    elif kind == "oversize":
        path.write_bytes(b"x" * 1048577)
    monkeypatch.setattr(client, "CA_BUNDLE", path)
    binding = SimpleNamespace(ca_bundle_sha256=hashlib.sha256(b"different").hexdigest())
    with pytest.raises((ValueError, OSError)):
        client._ssl(binding, absolute_deadline=monotonic() + (-1 if kind == "deadline" else 2))
