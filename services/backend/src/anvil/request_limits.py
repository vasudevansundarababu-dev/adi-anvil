"""Bound request bytes before multipart/JSON parsing, including chunked requests."""

import json
import re
from pathlib import Path
from uuid import uuid4


def safe_error_evidence(error, first_party_root):
    """Bounded static locations only; never messages, locals, paths or source lines."""
    known = {
        'Inactive or foreign software resource operation': 'software_resource_inactive_or_foreign',
        'Foreign software operation connection': 'software_resource_connection_mismatch',
        'Software resource closure changed before commit': 'software_resource_closure_changed',
        'Software resource digest changed before commit': 'software_resource_digest_changed',
        'Unexpected software resource type': 'software_resource_type',
        'Software resource changed while measuring': 'software_resource_changed_during_measurement',
        'Resource outside software operation inventory': 'software_resource_inventory',
        'Private KYC transaction cannot change scope or database role': 'private_kyc_scope_mismatch',
    }
    allowed_types = (RuntimeError, ValueError, TypeError, TimeoutError, OSError, PermissionError,
                     FileNotFoundError, Exception, ExceptionGroup, BaseExceptionGroup,
                     ConnectionError, EOFError, MemoryError, ImportError, ModuleNotFoundError,
                     AttributeError, KeyError, IndexError, AssertionError)
    result = {'exception_types': [], 'guards': [], 'locations': []}
    pending, seen, inspected_frames = [(error, 0)], set(), 0
    while pending and len(seen) < 4:
        current, depth = pending.pop()
        if id(current) in seen or depth > 3:
            continue
        seen.add(id(current))
        label = next((kind.__name__ for kind in allowed_types if type(current) is kind), 'external_exception')
        result['exception_types'].append(label)
        args = BaseException.args.__get__(current)
        guard = known.get(args[0], 'unclassified') if type(current) is RuntimeError and len(args) == 1 and type(args[0]) is str else 'unclassified'
        result['guards'].append(guard)
        trace = BaseException.__traceback__.__get__(current)
        while trace is not None and inspected_frames < 64:
            inspected_frames += 1
            code = trace.tb_frame.f_code
            path = Path(code.co_filename)
            if (path.is_absolute() and '..' not in path.parts and path.is_relative_to(first_party_root)
                    and re.fullmatch(r'[A-Za-z0-9_]{1,80}\.py', path.name)
                    and len(result['locations']) < 8):
                function = code.co_name
                if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}|<module>|<lambda>', function):
                    function = 'redacted'
                result['locations'].append({'file': path.name, 'function': function, 'line': trace.tb_lineno})
            trace = trace.tb_next
        children = []
        if isinstance(current, BaseExceptionGroup):
            children.extend(BaseExceptionGroup.exceptions.__get__(current)[:4])
        for descriptor in (BaseException.__cause__, BaseException.__context__):
            child = descriptor.__get__(current)
            if child is not None:
                children.append(child)
        for child in children:
            if len(pending) < 8:
                pending.append((child, depth + 1))
    while len(json.dumps(result, separators=(',', ':')).encode()) > 2048 and result['locations']:
        result['locations'].pop()
    return result


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
        capture = scope["method"] == "POST" and scope["path"] == "/internal/v1/marketing/native-capture"
        capture_status = scope["method"] == "GET" and scope["path"] == "/api/v1/integrations/marketing/native-capture/evidence-status"
        streaming = (
            scope["method"] == "POST"
            and re.fullmatch(
                r"/api/v1/projects/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}/workspace/benchmarks/imports",
                scope["path"],
            )
            is not None
        )
        project_import = (
            scope["method"] == "POST"
            and re.fullmatch(
                r"/api/v1/projects/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}/workspace/benchmark/import",
                scope["path"],
            )
            is not None
        )
        structured_input = (
            scope["method"] == "POST"
            and re.fullmatch(
                r"/api/v1/projects/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}/imported-projects/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}/data-inputs",
                scope["path"],
            )
            is not None
        )
        limit = (
            (
                100
                if streaming
                else 26
                if upload or project_import
                else 10
                if structured_input
                else 3
                if praxis
                else 2
                if manifest
                else 1
            )
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
        if streaming or project_import or structured_input or capture or capture_status:
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
