import asyncio

import pytest

from anvil.request_limits import RequestLimits


@pytest.mark.parametrize(
    "headers,chunks,status",
    [
        ([(b"content-length", b"1048577")], [], 413),
        ([], [b"x" * 600000, b"y" * 600000], 413),
        ([(b"content-length", b"-1")], [], 400),
        ([(b"content-length", b"1"), (b"content-length", b"2")], [], 400),
        ([(b"content-length", b"invalid")], [], 400),
        ([], [b"{}"], 200),
    ],
)
def test_size_limit_precedes_parser(headers, chunks, status):
    sent, invoked = [], []

    async def app(scope, receive, send):
        invoked.append(True)
        body = await receive()
        assert body["body"] == b"{}"
        await send({"type": "http.response.start", "status": 200})

    async def receive():
        chunk = chunks.pop(0)
        return {"type": "http.request", "body": chunk, "more_body": bool(chunks)}

    async def send(message):
        sent.append(message)

    asyncio.run(
        RequestLimits(app)(
            {"type": "http", "method": "POST", "path": "/api/v1/test", "headers": headers},
            receive,
            send,
        )
    )
    assert sent[0]["status"] == status
    assert bool(invoked) == (status == 200)
