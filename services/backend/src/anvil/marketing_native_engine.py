"""Closed fixed Docker Engine container/image inspect and stop transport.

Source proposal only. Exact daemon/API/socket/image/process custody is not yet
qualified. No environment override, remote endpoint, CLI, shell or retries.
Only complete parsed replies are returned. Raw/partial HTTP failure evidence
is not retained by this transport; CLI stream custody does not cover it.
"""

import asyncio
import json
import math
import os
import re
import socket
import stat
import struct
from time import monotonic

from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    _bounded_canonical,
    _pairs,
    marketing_native_gate,
)

SOCKET = "/run/docker.sock"
API = "/v1.47"


async def _private_wait_body(reader, headers, deadline, *, byte_limit=8192):
    """Bound the fixed wait response, including Docker's flushed chunked form.

    Moby27 postContainersWait flushes headers before the result is available.
    Only explicit private operations accept chunk framing; legacy transports keep
    their existing Content-Length-only rules. No extensions/trailers or replay.
    """
    if headers.get(b'transfer-encoding') != b'chunked' or b'content-length' in headers:
        raise ValueError('marketing_private_wait_exact_chunk_framing_required')
    if byte_limit not in (8192, DOCUMENT_CAP):
        raise ValueError('marketing_existing_private_engine_byte_limit_required')
    body = bytearray()
    for _ in range(64 if byte_limit == 8192 else 4096):
        line = bytearray()
        while len(line) < 16:
            _remaining(deadline)
            line.extend(await reader.readexactly(1))
            if line.endswith(b'\r\n'):
                break
        if not re.fullmatch(rb'[0-9a-fA-F]{1,8}\r\n', line):
            raise ValueError('marketing_private_wait_bounded_chunk_length_required')
        size = int(line[:-2], 16)
        if len(body) + size > byte_limit:
            raise ValueError('marketing_private_wait_reply_capacity')
        if size == 0:
            if await reader.readexactly(2) != b'\r\n' or not body:
                raise ValueError('marketing_private_wait_trailer_or_empty_body_denied')
            _remaining(deadline)
            return bytes(body)
        body.extend(await reader.readexactly(size))
        if await reader.readexactly(2) != b'\r\n':
            raise ValueError('marketing_private_wait_chunk_delimiter_required')
        _remaining(deadline)
    raise ValueError('marketing_private_wait_chunk_count_capacity')


def _remaining(deadline):
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("marketing_engine_finite_deadline_required")
    remaining = deadline - monotonic()
    if not 0 < remaining <= 600:
        raise TimeoutError("marketing_engine_absolute_deadline")
    return remaining


async def _request(operation, container_id, *, deadline, stop_seconds=0, private=False):
    if (operation not in {"inspect", "image_inspect", "stop", "wait_private_verifier"} or type(container_id) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", container_id)
            or type(stop_seconds) is not int or not 0 <= stop_seconds <= 600):
        raise ValueError("marketing_fixed_engine_operation_required")
    if type(private) is not bool or operation == 'wait_private_verifier' and not private:
        raise ValueError('marketing_explicit_private_engine_operation_required')
    path = (API + '/containers/' + container_id + '/wait?condition=not-running' if operation == 'wait_private_verifier' else
            API + "/images/sha256:" + container_id + "/json" if operation == "image_inspect" else
            API + "/containers/" + container_id + ("/json" if operation == "inspect" else "/stop?t=" + str(stop_seconds)))
    _remaining(deadline)
    info = os.lstat(SOCKET)
    parent = os.stat("/run")
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0
            or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022):
        raise ValueError("marketing_owned_engine_socket_required")

    async def exchange():
        reader, writer = await asyncio.open_unix_connection(SOCKET, limit=8192)
        try:
            peer = writer.get_extra_info("socket")
            if peer is None or peer.family != socket.AF_UNIX:
                raise ValueError("marketing_local_engine_peer_required")
            pid, uid, _ = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
            if pid <= 1 or uid != 0:
                raise ValueError("marketing_root_engine_peer_required")
            method = "POST" if operation in {"stop", "wait_private_verifier"} else "GET"
            request = (method + " " + path + " HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Length: 0\r\n\r\n").encode("ascii")
            # Connection establishment and peer validation may consume budget.
            # Never send a previously retained grace value that no longer fits.
            # Refuse instead of changing t behind the exact durable intent.
            remaining = _remaining(deadline)
            if operation == "stop" and remaining <= stop_seconds + 1:
                raise TimeoutError("marketing_stop_grace_and_observation_reserve_exhausted")
            writer.write(request)
            await writer.drain()
            header = bytearray()
            while len(header) < 8192:
                header.extend(await reader.readexactly(1))
                if header.endswith(b"\r\n\r\n"):
                    break
            else:
                raise ValueError("marketing_engine_header_capacity")
            lines = bytes(header).split(b"\r\n")
            expected = b"HTTP/1.1 204 No Content" if operation == "stop" else b"HTTP/1.1 200 OK"
            if lines[0] != expected:
                raise RuntimeError("marketing_engine_status_unknown_no_retry")
            headers = {}
            for line in lines[1:-2]:
                key, value = line.split(b":", 1)
                key = key.lower()
                if key in headers:
                    raise ValueError("marketing_engine_duplicate_header")
                headers[key] = value.strip()
            if private and operation != 'stop' and b'transfer-encoding' in headers:
                cap = 8192 if operation == 'wait_private_verifier' else DOCUMENT_CAP
                raw = await _private_wait_body(reader, headers, deadline, byte_limit=cap)
            else:
                length = headers.get(b"content-length", b"0" if operation == "stop" else b"")
                if b"transfer-encoding" in headers or not re.fullmatch(rb"0|[1-9][0-9]{0,6}", length):
                    raise ValueError("marketing_engine_fixed_framing_required")
                length = int(length)
                cap = 8192 if operation == 'wait_private_verifier' else DOCUMENT_CAP
                if length > cap or operation == "stop" and length != 0:
                    raise ValueError("marketing_engine_body_capacity")
                raw = await reader.readexactly(length)
            _remaining(deadline)
            if operation == "stop":
                return None
            value = json.loads(raw, object_pairs_hook=_pairs)
            if type(value) is not dict:
                raise ValueError("marketing_engine_inspect_object_required")
            if operation == 'wait_private_verifier' and (set(value) - {'StatusCode', 'Error'}
                    or type(value.get('StatusCode')) is not int or value['StatusCode'] != 0
                    or value.get('Error') not in (None, {})):
                raise ValueError('marketing_actual_private_verifier_zero_exit_required')
            _bounded_canonical(value, DOCUMENT_CAP)
            return value
        finally:
            writer.close()

    return await asyncio.wait_for(exchange(), timeout=_remaining(deadline))


async def inspect_owned_container(container_id, *, deadline):
    marketing_native_gate()
    return await _request("inspect", container_id, deadline=deadline)


async def stop_owned_container(container_id, *, deadline, stop_seconds):
    marketing_native_gate()
    return await _request("stop", container_id, deadline=deadline, stop_seconds=stop_seconds)
