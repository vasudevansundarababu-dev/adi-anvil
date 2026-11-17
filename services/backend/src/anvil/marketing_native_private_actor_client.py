"""Fixed, one-shot attester-owned actor POST. Source only; no retry or signer."""

import asyncio
import hashlib
from datetime import datetime, timezone
from time import monotonic

import httpx

from anvil.dataset_export_contract import json_object
from anvil.marketing_capture_attestation import STOP, _instant
from anvil.marketing_capture_status_client import HEADER_CAP, _BoundedTLSResponse, _ssl
from anvil.marketing_native_kernel_scope import _remaining
from anvil.marketing_private_actor_auth import PATH, PrivateActorTransport, verify
from anvil.praxis_generic_contract import canonical


class PrivateActorUnknown(RuntimeError):
    def __init__(self):
        super().__init__('Original private actor custody unknown; no retry')


class _ActorTLS(httpx.AsyncBaseTransport):
    _request_path = PATH
    def __init__(self, context, hard, original):
        self.context, self.hard, self.original, self.used = context, hard, original, False

    async def handle_async_request(self, request):
        if (self.used or request.method != 'POST'
                or str(request.url) != 'https://anvil-qa.adi-labs.ai' + self._request_path
                or request.content != self.original):
            raise PrivateActorUnknown()
        self.used = True
        left = self.hard - monotonic()
        if left <= 0:
            raise PrivateActorUnknown()
        reader, writer = await asyncio.open_connection('anvil-qa.adi-labs.ai', 443,
            ssl=self.context, server_hostname='anvil-qa.adi-labs.ai', ssl_handshake_timeout=left, limit=HEADER_CAP)
        try:
            headers = [(k, v) for k, v in request.headers.raw if k.lower() != b'connection']
            if (any(b'\r' in x or b'\n' in x for pair in headers for x in pair)
                    or [v for k, v in headers if k.lower() == b'content-length'] != [str(len(self.original)).encode()]
                    or any(k.lower() in {b'transfer-encoding', b'authorization'} for k, _ in headers)):
                raise PrivateActorUnknown()
            wire = b'POST ' + self._request_path.encode('ascii') + b' HTTP/1.1\r\n'
            wire += b''.join(k + b': ' + v + b'\r\n' for k, v in headers) + b'Connection: close\r\n\r\n'
            if len(wire) > HEADER_CAP:
                raise PrivateActorUnknown()
            writer.write(wire)
            writer.write(self.original)
            await writer.drain()
            raw = await reader.readuntil(b'\r\n\r\n')
            lines = raw[:-4].split(b'\r\n')
            if len(raw) > HEADER_CAP or len(lines) > 65 or not lines[0].startswith(b'HTTP/1.1 200 '):
                raise PrivateActorUnknown()
            parsed = []
            for line in lines[1:]:
                k, sep, v = line.partition(b':')
                if (not sep or not k or any(x <= 32 or x >= 127 for x in k)
                        or any(x < 32 and x != 9 or x == 127 for x in v)):
                    raise PrivateActorUnknown()
                parsed.append((k, v.strip(b' \t')))
            lengths = [v for k, v in parsed if k.lower() == b'content-length']
            if (len(lengths) != 1 or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= 8192
                    or any(k.lower() == b'transfer-encoding' for k, _ in parsed)):
                raise PrivateActorUnknown()
            return httpx.Response(200, headers=parsed,
                stream=_BoundedTLSResponse(reader, writer, int(lengths[0]), self.hard),
                extensions={'network_stream': writer})
        except BaseException:
            writer.close()
            raise


def retain_own_actor(enrollment, signed_header, original, *, absolute_deadline):
    _remaining(absolute_deadline)
    verified = verify(signed_header, enrollment)
    binding = PrivateActorTransport.model_validate_json(canonical(enrollment['private_actor_transport']))
    if (type(original) is not bytes or len(original) != verified.wire_bytes
            or hashlib.sha256(original).hexdigest() != verified.wire_sha256):
        raise ValueError('marketing_attester_original_actor_bytes_required')
    started = monotonic()
    expiry = min(_instant(enrollment['expires_at']), binding.not_after, STOP)
    hard = min(absolute_deadline - binding.cleanup_reserve_seconds, started + 5,
        started + (expiry - datetime.now(timezone.utc)).total_seconds() - binding.cleanup_reserve_seconds)
    _remaining(hard)
    context = _ssl(binding, absolute_deadline=hard)

    async def post():
        async with asyncio.timeout(max(0, hard - monotonic())):
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                    transport=_ActorTLS(context, hard, original),
                    timeout=httpx.Timeout(max(.001, hard - monotonic()))) as client:
                async with client.stream('POST', binding.origin + PATH, content=original, headers={
                    'X-Anvil-Capture-Enrollment': enrollment['enrollment_id'],
                    'X-Anvil-Private-Actor-Attestation': signed_header,
                    'Content-Type': 'application/json', 'Accept': 'application/json',
                    'Accept-Encoding': 'identity', 'Cache-Control': 'no-store'}) as response:
                    if (response.status_code != 200 or response.history
                            or response.headers.get('content-encoding', 'identity') != 'identity'
                            or response.headers.get('content-type', '').split(';')[0].strip() != 'application/json'):
                        raise PrivateActorUnknown()
                    peer = response.extensions['network_stream'].get_extra_info('ssl_object')
                    cert = peer.getpeercert(binary_form=True) if peer is not None else None
                    if (type(cert) is not bytes or not 0 < len(cert) <= 65536
                            or peer.server_hostname != 'anvil-qa.adi-labs.ai'):
                        raise PrivateActorUnknown()
                    body = bytearray()
                    async for chunk in response.aiter_raw():
                        if len(body) + len(chunk) > 8192:
                            raise PrivateActorUnknown()
                        body.extend(chunk)
                    value = json_object(bytes(body))
                    if (set(value) != {'schema_version', 'id', 'enrollment_id', 'manifest_id', 'raw_sha256', 'raw_bytes',
                                      'capture_accepted', 'native_qualified', 'run_authority'}
                            or value['schema_version'] != 'anvil.marketing-private-actor-custody.v1'
                            or any(value[k] != enrollment[k] for k in ('enrollment_id', 'manifest_id'))
                            or value['raw_sha256'] != verified.wire_sha256 or type(value['raw_bytes']) is not int
                            or value['raw_bytes'] != verified.wire_bytes or value['capture_accepted'] is not False
                            or value['native_qualified'] is not False or value['run_authority'] != 'not_granted'):
                        raise PrivateActorUnknown()
                    from uuid import UUID

                    if str(UUID(value['id'])) != value['id']:
                        raise PrivateActorUnknown()
                    _remaining(hard)
                    return bytes(body)
    try:
        return asyncio.run(post())
    except BaseException:
        raise PrivateActorUnknown() from None
