import asyncio

import pytest

from anvil.request_limits import RequestBodyTooLarge, RequestLimits

PATH = "/api/v1/projects/00000000-0000-4000-8000-000000000001/workspace/benchmarks/imports"


def invoke(path, chunks, headers=(), disconnect=False):
    sent, order = [], []
    values = iter(chunks)

    async def receive():
        order.append("receive")
        try:
            return {"type": "http.request", "body": next(values), "more_body": True}
        except StopIteration:
            return (
                {"type": "http.disconnect"}
                if disconnect
                else {"type": "http.request", "body": b"", "more_body": False}
            )

    async def app(scope, incoming, send):
        order.append("app")
        size, status = 0, 200
        try:
            while True:
                message = await incoming()
                if message["type"] == "http.disconnect":
                    status = 400
                    break
                size += len(message.get("body", b""))
                if not message.get("more_body"):
                    break
        except RequestBodyTooLarge:
            status = 413
        await send({"type": "http.response.start", "status": status})
        await send({"type": "http.response.body", "body": str(size).encode()})

    async def send(value):
        sent.append(value)

    asyncio.run(
        RequestLimits(app)(
            {"type": "http", "method": "POST", "path": path, "headers": headers}, receive, send
        )
    )
    return sent, order


def test_only_exact_import_path_bypasses_buffering_and_auth_can_run_first():
    sent, order = invoke(PATH, [b"x" * 600000] * 2)
    assert sent[0]["status"] == 200
    assert order[0] == "app"
    assert sent[1]["body"] == b"1200000"
    sent, order = invoke(PATH + "/extra", [b"x" * 600000] * 2)
    assert sent[0]["status"] == 413
    assert "app" not in order


def test_chunked_bytes_still_count_over_stream_limit_without_accumulation():
    sent, order = invoke(PATH, [b"x" * (1024 * 1024)] * 101)
    assert sent[0]["status"] == 413
    assert order[0] == "app"


@pytest.mark.parametrize(
    "headers,status",
    [
        ([(b"content-length", b"104857601")], 413),
        ([(b"content-length", b"-1")], 400),
        ([(b"content-length", b"invalid")], 400),
        ([(b"content-length", b"1"), (b"content-length", b"2")], 400),
    ],
)
def test_header_rejection_precedes_app_and_body(headers, status):
    sent, order = invoke(PATH, [], headers=headers)
    assert sent[0]["status"] == status
    assert order == []


def test_disconnect_reaches_streaming_handler_without_accepted_body():
    sent, order = invoke(PATH, [b"incomplete"], disconnect=True)
    assert sent[0]["status"] == 400
    assert order[0] == "app"
