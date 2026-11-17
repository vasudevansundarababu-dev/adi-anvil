"""Separate fixed container bootstrap candidate; all operational gates closed.

Original operator supplies two bounded frames: original retained runtime/network
observations, then the once-prepared original job. Only public prestart metadata
and final pair-exit status leave stdout. No prepare, credential, Q or retry API.
This entry does not create a container, namespace, mount or authority record.
"""

import asyncio
import os
import stat
import sys
from time import monotonic

from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    _bounded_canonical,
    marketing_native_gate,
    prepare_marketing_request,
)
from anvil.marketing_native_enrollment_client import _ready
from anvil.marketing_native_kernel_scope import _remaining
from anvil.marketing_native_records import _parse_record


async def _read_exact(descriptor, size, deadline):
    value = bytearray()
    while len(value) < size:
        _remaining(deadline)
        await _ready(descriptor, writing=False, deadline=deadline)
        try:
            chunk = os.read(descriptor, min(32768, size - len(value)))
        except BlockingIOError:
            continue
        if not chunk:
            raise ValueError('marketing_original_bootstrap_input_closed_no_retry')
        value.extend(chunk)
    _remaining(deadline)
    return bytes(value)


async def _frame(descriptor, deadline):
    header = await _read_exact(descriptor, 9, deadline)
    if header[-1:] != b'\n' or any(c not in b'0123456789abcdef' for c in header[:8]):
        raise ValueError('marketing_fixed_bootstrap_frame_required')
    count = int(header[:8], 16)
    if not 0 < count <= DOCUMENT_CAP:
        raise ValueError('marketing_bootstrap_original_document_capacity')
    return _parse_record(await _read_exact(descriptor, count, deadline))


async def _public_reply(value, deadline):
    raw = _bounded_canonical(value, 8192)
    view = memoryview(f'{len(raw):08x}\n'.encode() + raw)
    while view:
        _remaining(deadline)
        await _ready(1, writing=True, deadline=deadline)
        try:
            count = os.write(1, view[:32768])
        except BlockingIOError:
            continue
        if count <= 0:
            raise ValueError('marketing_original_bootstrap_reply_unknown_no_retry')
        view = view[count:]


async def _original_operation(deadline):
    from anvil.marketing_native_job_packet import decode_original_job
    from anvil.marketing_native_operator_network import (
        container_operator_pair_candidate,
        validate_container_operator_network,
    )

    first = await _frame(0, deadline)
    fields = {'schema_version', 'runtime', 'network_profile', 'operator_inspect', 'api_inspect', 'network_inspect'}
    if (set(first) != fields or first['schema_version'] != 'anvil.marketing-original-operator-bootstrap.v1'
            or type(first['runtime']) is not dict
            or any(type(first[key]) is not str for key in fields - {'schema_version', 'runtime'})):
        raise ValueError('marketing_original_operator_bootstrap_packet_required')
    candidate = validate_container_operator_network(*(first[key].encode('utf-8') for key in
        ('network_profile', 'operator_inspect', 'api_inspect', 'network_inspect')))
    pair = container_operator_pair_candidate(_bounded_canonical(first['runtime'], 8192), deadline, candidate)
    async with pair:
        input_deadline = pair.original_input_deadline()
        # The original external operator freezes ACTUAL returned identities
        # before its single prepare. No job lease or prepared bytes appear here.
        await _public_reply({'schema_version': 'anvil.marketing-operator-prestarted.v1',
            'processes': pair.public_prestart_metadata(), 'native_qualified': False}, input_deadline)
        second = await _frame(0, input_deadline)
        if (set(second) != {'schema_version', 'request', 'job', 'once_prepared'}
                or second['schema_version'] != 'anvil.marketing-original-private-control-input.v2'
                or type(second['request']) is not str or type(second['once_prepared']) is not str
                or type(second['job']) is not dict):
            raise ValueError('marketing_original_once_prepared_bootstrap_input_required')
        request = prepare_marketing_request(second['request'].encode('utf-8'))
        result = await pair.supply_original(decode_original_job(second['job']),
            second['once_prepared'].encode('utf-8'), request)
    await _public_reply({'schema_version': 'anvil.marketing-operator-pair-exit.v1', **result}, deadline)


def main():
    marketing_native_gate()
    if (len(sys.argv) != 2 or sys.platform != 'linux' or sys.version_info[:2] != (3, 12)
            or sys.flags.isolated != 1 or sys.flags.ignore_environment != 1
            or sys.flags.no_user_site != 1 or not sys.dont_write_bytecode):
        return 42
    try:
        from anvil.marketing_native_actor_hardening import protect_independent_receiver

        protect_independent_receiver()  # Before any job/lease arrives.
        deadline = float(sys.argv[1])
        _remaining(deadline)
        if deadline <= monotonic():
            return 42
        for descriptor in (0, 1):
            info = os.fstat(descriptor)
            if info.st_uid != 0 or not (stat.S_ISFIFO(info.st_mode) or stat.S_ISSOCK(info.st_mode)):
                return 42
            os.set_blocking(descriptor, False)
        asyncio.run(_original_operation(deadline))
        return 0
    except BaseException:
        return 42  # No private packet, environment or traceback leaves this process.


if __name__ == '__main__':
    raise SystemExit(main())
