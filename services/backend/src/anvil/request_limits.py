"""Bound request bytes before multipart/JSON parsing, including chunked requests."""

import json
import re
from uuid import uuid4


class RequestBodyTooLarge(ValueError):
    pass


class RequestLimits:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        upload = scope["method"] == "POST" and scope["path"].endswith("/artifacts")
        manifest = scope["path"].endswith("/imports/validate")
        praxis = scope["method"] == "POST" and scope["path"].endswith("/praxis-sources")
        streaming = (
            scope["method"] == "POST"
            and re.fullmatch(
                r"/api/v1/projects/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}/workspace/benchmarks/imports",
                scope["path"],
            )
            is not None
        )
        project_import = scope["method"] == "POST" and re.fullmatch(
            r"/api/v1/projects/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}/workspace/benchmark/import",
            scope["path"],
        ) is not None
        limit = (
            (100 if streaming else 26 if upload or project_import else 3 if praxis else 2 if manifest else 1)
            * 1024
            * 1024
        )
        request_id = scope.get("state", {}).get("request_id", str(uuid4()))
        lengths = [v for k, v in scope.get("headers", []) if k.lower() == b"content-length"]
        try:
            if len(lengths) > 1 or (lengths and int(lengths[0]) < 0):
                raise ValueError
            declared = int(lengths[0]) if lengths else 0
        except ValueError:
            return await self.reject(send, 400, "Invalid Content-Length", request_id)
        if declared > limit:
            return await self.reject(send, 413, "Request exceeds size limit", request_id)
        if streaming or project_import:
            size = 0

            async def streaming_receive():
                nonlocal size
                message = await receive()
                size += len(message.get("body", b""))
                if size > limit:
                    raise RequestBodyTooLarge("Benchmark upload exceeds size limit")
                return message

            return await self.app(scope, streaming_receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                return await self.reject(send, 413, "Request exceeds size limit", request_id)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        consumed = False

        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)

    @staticmethod
    async def reject(send, status, message, request_id):
        body = json.dumps(
            {
                "error": {
                    "code": f"http_{status}",
                    "message": message,
                    "retryable": False,
                    "request_id": request_id,
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-request-id", request_id.encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
