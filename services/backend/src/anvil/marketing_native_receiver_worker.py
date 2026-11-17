"""Prestarted independent receiver entry; bounded public input, no job lease.

The operator retains the original child before supplying the independently
bound request. Its ready pipe opens no graph gate: it reports only listening.
The scope is created later by control, before its first private helper request.
"""

import asyncio
import os
import select
import stat
import sys
from time import monotonic

from anvil.marketing_native_boundary import marketing_native_gate, prepare_marketing_request
from anvil.marketing_native_kernel_scope import _remaining
from anvil.marketing_native_records import _parse_record


def _input(fd, deadline):
    info = os.fstat(fd)
    if fd < 3 or not stat.S_ISFIFO(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError('marketing_receiver_original_public_input_pipe_required')
    os.set_blocking(fd, False)
    raw = bytearray()
    try:
        while True:
            _remaining(deadline)
            if not select.select([fd], [], [], max(0, deadline - monotonic()))[0]:
                raise TimeoutError('marketing_receiver_original_input_cutoff')
            chunk = os.read(fd, min(32768, 65537 - len(raw)))
            if not chunk:
                break
            if len(raw) + len(chunk) > 65536:
                raise ValueError('marketing_receiver_public_request_capacity')
            raw.extend(chunk)
        value = _parse_record(bytes(raw))
        if (set(value) != {'schema_version', 'request', 'original_deadline_monotonic'}
                or value['schema_version'] != 'anvil.marketing-original-receiver-input.v1'
                or value['original_deadline_monotonic'] != deadline or type(value['request']) is not str):
            raise ValueError('marketing_receiver_original_fixed_public_packet_required')
        return prepare_marketing_request(value['request'].encode('utf-8'))
    finally:
        os.close(fd)


def main():
    marketing_native_gate()
    if len(sys.argv) != 4 or sys.platform != 'linux' or sys.version_info[:2] != (3, 12) or os.geteuid() != 0:
        return 42
    ready = None
    try:
        from anvil.marketing_native_actor_hardening import protect_independent_receiver
        from anvil.marketing_native_attester_receiver import _serve_original

        protect_independent_receiver()
        incoming, ready, deadline = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3])
        if incoming == ready or ready < 3:
            raise ValueError('marketing_receiver_disjoint_owned_pipes_required')
        os.set_inheritable(incoming, False)
        os.set_inheritable(ready, False)
        request = _input(incoming, deadline)
        # Transfer this exact ready FD to the fixed receiver; no replacement,
        # callback, request retry or registry recovery is possible.
        ready_fd, ready = ready, None
        asyncio.run(_serve_original(request, ready_fd=ready_fd))
        return 0
    except BaseException:
        return 42
    finally:
        if ready is not None:
            os.close(ready)


if __name__ == '__main__':
    raise SystemExit(main())
