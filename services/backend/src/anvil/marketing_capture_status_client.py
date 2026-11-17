"""Root-attester-only direct status read; no key access, signer or retry.

The actual isolated attester must construct its own fixed-purpose signed GET
from its original enrolled key. Passing a dict/header here establishes no native
authority. Mock transport observations are explicitly unusable as live TLS proof.
"""

import asyncio
import hashlib
import math
import os
import ssl
import stat
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Literal

import httpx

from anvil.marketing_capture_attestation import STOP, _instant
from anvil.marketing_capture_status import PATH, RESPONSE_CAP, Transport, validate_response, verify
from anvil.praxis_generic_contract import canonical, digest

CA_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")
HEADER_CAP = 8192
READ_MAX_SECONDS = 5


@dataclass(frozen=True, slots=True)
class Observation:
    origin: Literal["certificate_verified_api", "software_mock_unqualified"]
    body_sha256: str
    tls_certificate_sha256: str | None
    request_headers: tuple[tuple[bytes, bytes], ...] = field(repr=False)
    response_headers: tuple[tuple[bytes, bytes], ...] = field(repr=False)
    raw_body: bytes = field(repr=False)
    status: dict = field(repr=False)


class ReadUnknown(RuntimeError):
    """Diagnostic partial response stays unqualified; no automatic retry."""

    def __init__(self, *, request_headers=(), response_headers=(), partial_body=b""):
        super().__init__("Original API evidence status read unknown; no retry or seal")
        self.request_headers = request_headers
        self.response_headers = response_headers
        self.partial_body = partial_body


def _ssl(binding, *, absolute_deadline):
    # Never follow a substituted link or open a blocking pipe/device. The
    # immutable image's regular CA file is read in bounded chunks, with the
    # ORIGINAL operation cutoff checked before and after local work as well.
    if monotonic() >= absolute_deadline:
        raise ValueError("Original status deadline reached before CA validation")
    descriptor = os.open(CA_BUNDLE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 1048576:
            raise ValueError("Original qualified regular CA bundle required")
        chunks = []
        total = 0
        while True:
            if monotonic() >= absolute_deadline:
                raise ValueError("Original status deadline reached during CA validation")
            chunk = os.read(descriptor, min(32768, 1048577 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > 1048576:
                raise ValueError("Original qualified CA bundle exceeds bound")
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    if not 0 < len(raw) <= 1048576 or hashlib.sha256(raw).hexdigest() != binding.ca_bundle_sha256:
        raise ValueError("Original qualified CA bundle changed")
    context = ssl.create_default_context(cadata=raw.decode("ascii"))
    if context.verify_mode != ssl.CERT_REQUIRED or context.check_hostname is not True:
        raise ValueError("Certificate and hostname verification required")
    if monotonic() >= absolute_deadline:
        raise ValueError("Original status deadline reached after CA validation")
    return context


class _BoundedTLSResponse(httpx.AsyncByteStream):
    def __init__(self, reader, writer, length, hard):
        self.reader, self.writer, self.remaining, self.hard = reader, writer, length, hard

    async def __aiter__(self):
        try:
            while self.remaining:
                chunk = await self.reader.read(min(self.remaining, RESPONSE_CAP))
                if not chunk:
                    raise ValueError("Incomplete bounded original status body")
                self.remaining -= len(chunk)
                yield chunk
        except BaseException:
            self.writer.close()
            raise

    async def aclose(self):
        self.writer.close()
        if monotonic() >= self.hard:
            raise TimeoutError('Original TLS close cutoff reached')
        async with asyncio.timeout(self.hard - monotonic()):
            await self.writer.wait_closed()


class _BoundedTLS(httpx.AsyncBaseTransport):
    """One fixed HTTP/1.1 request; bound raw headers BEFORE parsing fields.

    TLS/OS internals and independent whole-process supervision still require
    exact-image qualification. No httpcore incomplete-header parser is used.
    """

    _request_path = PATH
    _response_cap = RESPONSE_CAP

    def __init__(self, context, hard):
        self.context, self.hard, self.used = context, hard, False

    async def handle_async_request(self, request):
        if self.used or request.method != "GET" or str(request.url) != "https://anvil-qa.adi-labs.ai" + self._request_path:
            raise ValueError("Only one original fixed status request permitted")
        self.used = True
        remaining = self.hard - monotonic()
        if remaining <= 0:
            raise TimeoutError("Original status deadline")
        reader, writer = await asyncio.open_connection(
            "anvil-qa.adi-labs.ai", 443, ssl=self.context,
            server_hostname="anvil-qa.adi-labs.ai", ssl_handshake_timeout=remaining,
            limit=HEADER_CAP,
        )
        try:
            headers = [(key, value) for key, value in request.headers.raw if key.lower() != b"connection"]
            wire = b"GET " + self._request_path.encode("ascii") + b" HTTP/1.1\r\n"
            wire += b"".join(key + b": " + value + b"\r\n" for key, value in headers)
            wire += b"Connection: close\r\n\r\n"
            if len(wire) > HEADER_CAP or any(b"\r" in x or b"\n" in x for pair in headers for x in pair):
                raise ValueError("Bounded fixed status request headers required")
            writer.write(wire)
            await writer.drain()
            raw = await reader.readuntil(b"\r\n\r\n")
            if len(raw) > HEADER_CAP:
                raise ValueError("Original status headers exceed bound")
            lines = raw[:-4].split(b"\r\n")
            if len(lines) > 65 or not lines[0].startswith(b"HTTP/1.1 200 "):
                raise ValueError("Exact successful HTTP/1.1 status required")
            parsed = []
            for line in lines[1:]:
                key, separator, value = line.partition(b":")
                if (not separator or not key or any(x <= 32 or x >= 127 for x in key)
                        or any(x < 32 and x != 9 or x == 127 for x in value)):
                    raise ValueError("Invalid bounded original status header")
                parsed.append((key, value.strip(b" \t")))
            lengths = [value for key, value in parsed if key.lower() == b"content-length"]
            if (len(lengths) != 1 or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= self._response_cap
                    or any(key.lower() == b"transfer-encoding" for key, _ in parsed)):
                raise ValueError("Exact bounded status framing required")
            return httpx.Response(200, headers=parsed,
                                  stream=_BoundedTLSResponse(reader, writer, int(lengths[0]), self.hard),
                                  extensions={"network_stream": writer})
        except BaseException:
            writer.close()
            raise


def read(enrollment, signed_header, *, absolute_deadline, transport=None):
    """One direct GET under the ORIGINAL operation/cleanup budget only.

    absolute_deadline must come from the independent original root operation,
    never a fresh timer/owner-supplied replacement. No runtime call is enabled
    merely by this utility; original qualification/profile/egress remain required.
    """
    started = monotonic()
    if (type(absolute_deadline) not in (int, float) or not math.isfinite(absolute_deadline)
            or absolute_deadline <= started
            or transport is not None and type(transport) is not httpx.MockTransport):
        raise ValueError("Original bounded root-attester status operation required")
    verify(signed_header, enrollment)
    binding = Transport.model_validate(enrollment["status_transport"])
    end = min(_instant(enrollment["expires_at"]), binding.not_after, STOP)
    hard = min(absolute_deadline - binding.cleanup_reserve_seconds, started + READ_MAX_SECONDS,
               started + (end - datetime.now(timezone.utc)).total_seconds() - binding.cleanup_reserve_seconds)
    if hard <= monotonic():
        raise ValueError("Original physical cleanup reserve forbids status read")
    ssl_context = _ssl(binding, absolute_deadline=hard) if transport is None else True
    url = binding.origin + PATH
    original_request_headers = ()
    original_response_headers = ()
    body = bytearray()

    async def get():
        nonlocal original_request_headers, original_response_headers
        remaining = hard - monotonic()
        if remaining <= 0:
            raise TimeoutError("original status deadline")
        async with asyncio.timeout(remaining):
            async with httpx.AsyncClient(verify=ssl_context, trust_env=False, follow_redirects=False,
                                         timeout=httpx.Timeout(remaining),
                                         transport=_BoundedTLS(ssl_context, hard) if transport is None else transport,
                                         limits=httpx.Limits(max_connections=1, max_keepalive_connections=0)) as client:
                async with client.stream("GET", url, headers={
                    "X-Anvil-Capture-Enrollment": enrollment["enrollment_id"],
                    "X-Anvil-Capture-Attestation": signed_header,
                    "Accept": "application/json", "Accept-Encoding": "identity", "Cache-Control": "no-store",
                }) as response:
                    original_request_headers = tuple(response.request.headers.raw)
                    original_response_headers = tuple(response.headers.raw)
                    if (response.status_code != 200 or str(response.url) != url or response.history
                            or len(original_response_headers) > 64
                            or sum(len(k) + len(v) + 4 for k, v in original_response_headers) > HEADER_CAP
                            or response.headers.get("content-encoding", "identity") != "identity"
                            or len(response.headers.get_list("content-type")) != 1
                            or response.headers["content-type"].split(";")[0].strip() != "application/json"):
                        raise ValueError("exact original API response required")
                    lengths = response.headers.get_list("content-length")
                    if len(lengths) > 1 or lengths and (not lengths[0].isascii() or not lengths[0].isdigit()
                                                        or not 0 < int(lengths[0]) <= RESPONSE_CAP):
                        raise ValueError("bounded status response length required")
                    certificate_sha = None
                    if transport is None:
                        stream = response.extensions.get("network_stream")
                        peer = stream.get_extra_info("ssl_object") if stream is not None else None
                        certificate = peer.getpeercert(binary_form=True) if peer is not None else None
                        if (type(certificate) is not bytes or not 0 < len(certificate) <= 65536
                                or peer.server_hostname != "anvil-qa.adi-labs.ai"):
                            raise ValueError("actual verified API TLS peer required")
                        certificate_sha = hashlib.sha256(certificate).hexdigest()
                    async for chunk in response.aiter_raw():
                        if monotonic() >= hard or len(body) + len(chunk) > RESPONSE_CAP:
                            raise ValueError("original bounded status read required")
                        body.extend(chunk)
                    if lengths and len(body) != int(lengths[0]):
                        raise ValueError("incomplete status response")
                    verify(signed_header, enrollment)
                    status = validate_response(bytes(body), enrollment)
                    if monotonic() >= hard:
                        raise ValueError("actual status before cleanup required")
                    return Observation("certificate_verified_api" if transport is None else "software_mock_unqualified",
                                       hashlib.sha256(body).hexdigest(), certificate_sha, original_request_headers,
                                       original_response_headers, bytes(body), status.model_dump(mode="json"))

    try:
        return asyncio.run(get())
    except Exception:
        raise ReadUnknown(request_headers=original_request_headers, response_headers=original_response_headers,
                          partial_body=bytes(body)) from None


def bind_reference(operation_binding, raw_status, enrollment, *, quiescence, now=None):
    """Pure size/content check, NOT TLS provenance, a seal or native authority.

    The qualified root attester must obtain raw_status through its OWN direct
    read above, retain that observation, and construct its seal independently.
    A caller-supplied status/hash alone must never reach a signing interface.
    """
    from anvil.marketing_native_wire_bounds import bounded_json
    from anvil.marketing_world_quiescence import Quiescence, Scope

    if type(operation_binding) is not dict or "api_evidence" in operation_binding:
        raise ValueError("Original complete operation binding without replacement reference required")
    status = validate_response(raw_status, enrollment, now=now)
    if status.state != "ready":
        raise ValueError("Reserved or unknown API content cannot be sealed")
    original = Quiescence.model_validate(quiescence)
    descriptor = status.descriptor
    if (any(getattr(original, key) != getattr(status.scope, key) for key in Scope.model_fields)
            or descriptor["quiescence_id"] != str(original.quiescence_id)
            or descriptor["quiescence_receipt_sha256"] != original.receipt_sha256
            or descriptor["graph_ledger_sha256"] != original.graph_ledger_sha256
            or descriptor["reconstruction_sha256"] != original.reconstruction_sha256
            or descriptor["fence_epoch"] != original.fence_epoch):
        raise ValueError("API content differs from independent original quiescence receipt")
    value = deepcopy(operation_binding)
    value["api_evidence"] = {"manifest_id": str(status.manifest_id),
                             "manifest_sha256": status.descriptor["manifest_sha256"],
                             "descriptor_sha256": digest(status.descriptor)}
    # Check the COMPLETE actual inner object, not a nominal descriptor budget.
    # The native encoder must additionally check escaped outer framing/wire caps.
    bounded_json(value, 4096, max_nodes=3000)
    raw = canonical(value)
    if len(raw) > 4096:
        raise ValueError("Complete operation binding cannot fit original capture limit")
    return raw
