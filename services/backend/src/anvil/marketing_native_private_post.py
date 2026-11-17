"""Two fixed final attester POSTs; no caller URL, signer, retry or fallback."""

import asyncio
import hashlib
from datetime import datetime, timezone
from time import monotonic

import httpx

from anvil.dataset_export_contract import json_object
from anvil.marketing_capture_attestation import PATH as CAPTURE_PATH
from anvil.marketing_capture_attestation import STOP, _instant
from anvil.marketing_capture_status_client import _ssl
from anvil.marketing_native_kernel_scope import _remaining
from anvil.marketing_native_private_actor_client import _ActorTLS
from anvil.marketing_private_result_auth import PATH as RESULT_PATH
from anvil.marketing_private_result_auth import PrivateResultTransport
from anvil.praxis_generic_contract import canonical


class _ResultTLS(_ActorTLS):
    _request_path = RESULT_PATH


class _CaptureTLS(_ActorTLS):
    _request_path = CAPTURE_PATH


class FinalPostUnknown(RuntimeError):
    def __init__(self):
        super().__init__('Original final private custody unknown; no retry')


def _post(enrollment, signed_header, raw, binding, *, deadline, result):
    # Only the two source-selected constants below can choose an operation.
    cls, path, header = ((_ResultTLS, RESULT_PATH, 'X-Anvil-Private-Result-Attestation') if result else
                        (_CaptureTLS, CAPTURE_PATH, 'X-Anvil-Capture-Attestation'))
    started = monotonic()
    hard = min(deadline, started + 5, started + (min(_instant(enrollment['expires_at']), binding.not_after, STOP)
        - datetime.now(timezone.utc)).total_seconds() - binding.cleanup_reserve_seconds)
    _remaining(hard)
    tls = _ssl(binding, absolute_deadline=hard)

    async def post():
        async with asyncio.timeout(max(0, hard - monotonic())):
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False, transport=cls(tls, hard, raw),
                    timeout=httpx.Timeout(max(.001, hard - monotonic()))) as client:
                async with client.stream('POST', 'https://anvil-qa.adi-labs.ai' + path, content=raw, headers={
                    'X-Anvil-Capture-Enrollment': enrollment['enrollment_id'], header: signed_header,
                    'Content-Type': 'application/json', 'Accept': 'application/json',
                    'Accept-Encoding': 'identity', 'Cache-Control': 'no-store'}) as response:
                    if (response.status_code != 200 or response.history
                            or response.headers.get('content-type', '').split(';')[0].strip() != 'application/json'
                            or response.headers.get('content-encoding', 'identity') != 'identity'):
                        raise FinalPostUnknown()
                    peer = response.extensions['network_stream'].get_extra_info('ssl_object')
                    cert = peer.getpeercert(binary_form=True) if peer is not None else None
                    if (type(cert) is not bytes or not 0 < len(cert) <= 65536
                            or peer.server_hostname != 'anvil-qa.adi-labs.ai'):
                        raise FinalPostUnknown()
                    body = bytearray()
                    async for chunk in response.aiter_raw():
                        if len(body) + len(chunk) > 8192:
                            raise FinalPostUnknown()
                        body.extend(chunk)
                    _remaining(hard)
                    value = json_object(bytes(body))
                    if canonical(value) != bytes(body):
                        raise FinalPostUnknown()
                    return bytes(body)
    try:
        return asyncio.run(post())
    except BaseException:
        raise FinalPostUnknown() from None


def post_owned_result(enrollment, signed_header, raw, *, deadline):
    from anvil.marketing_private_result_auth import verify
    from anvil.marketing_private_result_frame import parse

    verified = verify(signed_header, enrollment)
    original = parse(raw, enrollment, verified)
    binding = PrivateResultTransport.model_validate_json(canonical(enrollment['private_result_transport']))
    response = _post(enrollment, signed_header, raw, binding, deadline=deadline, result=True)
    value = json_object(response)
    fields = {'schema_version', 'id', 'enrollment_id', 'manifest_id', 'grade_frame_sha256', 'raw_sha256', 'raw_bytes',
              'verifier_result_sha256', 'process_receipt_sha256', 'grade_status', 'capture_accepted', 'native_qualified', 'run_authority'}
    if (set(value) != fields or value['schema_version'] != 'anvil.marketing-private-result-custody.v1'
            or any(value[k] != enrollment[k] for k in ('enrollment_id', 'manifest_id'))
            or value['grade_frame_sha256'] != original.grade_frame_sha256
            or value['raw_sha256'] != hashlib.sha256(raw).hexdigest()
            or type(value['raw_bytes']) is not int or value['raw_bytes'] != len(raw)
            or value['verifier_result_sha256'] != original.verifier_result_sha256
            or value['process_receipt_sha256'] != original.process_receipt_sha256
            or value['grade_status'] != json_object(original.verifier_result)['result']
            or value['capture_accepted'] is not False or value['native_qualified'] is not False
            or value['run_authority'] != 'not_granted'):
        raise FinalPostUnknown()
    from uuid import UUID

    if str(UUID(value['id'])) != value['id']:
        raise FinalPostUnknown()
    return response


def post_owned_capture(enrollment, signed_header, raw, *, deadline):
    from anvil.marketing_capture_attestation import matches_wire, verify
    from anvil.marketing_capture_status import Transport
    from anvil.marketing_capture_submission import parse

    attestation = verify(signed_header, enrollment)
    if not matches_wire(attestation, raw):
        raise ValueError('marketing_original_final_capture_wire_required')
    parse(raw, enrollment)
    binding = Transport.model_validate_json(canonical(enrollment['status_transport']))
    # Response semantics are validated by the fixed API acceptance contract in
    # the key worker; transport 200 by itself never grants native acceptance.
    return _post(enrollment, signed_header, raw, binding, deadline=deadline, result=False)
