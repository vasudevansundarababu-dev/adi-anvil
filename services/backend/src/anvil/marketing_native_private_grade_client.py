"""Attester-owned one-shot fixed private-grade GET; no signer or fallback.

Only this exact independently qualified path may carry private grader bytes.
Neither partial data, ordinary status signatures nor a reserved descriptor can
be interpreted as protected input. No mock transport is accepted at this entry.
"""

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic

import httpx

from anvil.marketing_capture_attestation import STOP, _instant
from anvil.marketing_capture_status_client import HEADER_CAP, _BoundedTLS, _ssl
from anvil.marketing_native_kernel_scope import _remaining
from anvil.marketing_private_grade_auth import PATH, RESPONSE_CAP, PrivateGradeTransport, verify
from anvil.praxis_generic_contract import canonical


class _PrivateGradeTLS(_BoundedTLS):
    # Fixed source constants; no request body/path/query/factory from IPC.
    _request_path = PATH
    _response_cap = RESPONSE_CAP


@dataclass(frozen=True, slots=True)
class PrivateGradeObservation:
    raw_body: bytes = field(repr=False)
    body_sha256: str
    tls_certificate_sha256: str
    request_headers: tuple = field(repr=False)
    response_headers: tuple = field(repr=False)
    origin: str = 'certificate_verified_private_api'


class PrivateGradeUnknown(RuntimeError):
    def __init__(self):
        super().__init__('Original private grade transport/custody unknown; no retry')


def read_own_private_grade(enrollment, signed_header, *, absolute_deadline):
    _remaining(absolute_deadline)
    verify(signed_header, enrollment)
    binding = PrivateGradeTransport.model_validate_json(canonical(enrollment['private_grade_transport']))
    started = monotonic()
    expiry = min(_instant(enrollment['expires_at']), binding.not_after, STOP)
    hard = min(absolute_deadline - binding.cleanup_reserve_seconds, started + 5,
               started + (expiry - datetime.now(timezone.utc)).total_seconds() - binding.cleanup_reserve_seconds)
    if hard <= monotonic():
        raise ValueError('marketing_private_grade_original_cleanup_reserve_required')
    context = _ssl(binding, absolute_deadline=hard)

    async def get():
        body = bytearray()
        async with asyncio.timeout(max(0, hard - monotonic())):
            async with httpx.AsyncClient(verify=context, trust_env=False, follow_redirects=False,
                    timeout=httpx.Timeout(max(0.001, hard - monotonic())), transport=_PrivateGradeTLS(context, hard),
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=0)) as client:
                async with client.stream('GET', binding.origin + PATH, headers={
                    'X-Anvil-Capture-Enrollment': enrollment['enrollment_id'],
                    'X-Anvil-Private-Grade-Attestation': signed_header,
                    'Accept': 'application/json', 'Accept-Encoding': 'identity', 'Cache-Control': 'no-store',
                }) as response:
                    headers = tuple(response.headers.raw)
                    if (response.status_code != 200 or response.history or str(response.url) != binding.origin + PATH
                            or len(headers) > 64 or sum(len(k) + len(v) + 4 for k, v in headers) > HEADER_CAP
                            or response.headers.get('content-encoding', 'identity') != 'identity'
                            or response.headers.get('content-type', '').split(';')[0].strip() != 'application/json'):
                        raise PrivateGradeUnknown()
                    stream = response.extensions.get('network_stream')
                    peer = stream.get_extra_info('ssl_object') if stream is not None else None
                    certificate = peer.getpeercert(binary_form=True) if peer is not None else None
                    if (type(certificate) is not bytes or not 0 < len(certificate) <= 65536
                            or peer.server_hostname != 'anvil-qa.adi-labs.ai'):
                        raise PrivateGradeUnknown()
                    async for chunk in response.aiter_raw():
                        if monotonic() >= hard or len(body) + len(chunk) > binding.response_limit:
                            raise PrivateGradeUnknown()
                        body.extend(chunk)
                    if not body or monotonic() >= hard:
                        raise PrivateGradeUnknown()
                    raw = bytes(body)
                    return PrivateGradeObservation(raw, hashlib.sha256(raw).hexdigest(), hashlib.sha256(certificate).hexdigest(),
                                                    tuple(response.request.headers.raw), headers)
    try:
        return asyncio.run(get())
    except BaseException:
        # No partial protected bytes, signed header or TLS details enter an
        # exception string/log/public reply. The original operation cannot retry.
        raise PrivateGradeUnknown() from None
