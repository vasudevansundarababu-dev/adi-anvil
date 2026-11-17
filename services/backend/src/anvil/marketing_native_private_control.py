"""Dedicated one-operation private control entry; never an ASGI privilege drop.

Only the original private job/prepared/request packet crosses the owned pipe.
No world exists before the graph fork. No DB factory is received or made in this
parent; the original graph child constructs its own fixed scheduler factory.
All operational entry gates remain unconditional and nothing runs on import.
"""

import asyncio
import hashlib
import os
import select
import stat
import sys
from time import monotonic

from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    marketing_native_gate,
    prepare_marketing_request,
)
from anvil.marketing_native_kernel_scope import _read, _remaining
from anvil.marketing_native_records import _parse_record


def require_private_control_custody(records, context):
    from anvil.marketing_native_actor_scope import _pid_identity
    from anvil.marketing_native_world_binding import _read_source_file

    if (sys.platform != 'linux' or sys.version_info[:2] != (3, 12)
            or sys.flags.isolated != 1 or sys.flags.ignore_environment != 1
            or sys.flags.no_user_site != 1 or not sys.dont_write_bytecode):
        raise ValueError('marketing_dedicated_isolated_private_control_required')
    original = _parse_record(dict(records.records)['host'])['payload']['control_process']
    fields = {'schema_version', 'pid', 'start_ticks', 'command_sha256', 'source_sha256',
              'input_deadline_monotonic', 'environment_sha256'}
    if (type(original) is not dict or set(original) != fields
            or original['schema_version'] != 'anvil.marketing-private-control-process.v1'
            or type(original['pid']) is not int or original['pid'] != os.getpid()
            or type(original['start_ticks']) is not int
            or original['input_deadline_monotonic'] < context['deadline_monotonic']):
        raise ValueError('marketing_original_dedicated_control_profile_required')
    _remaining(context['deadline_monotonic'])
    from anvil.marketing_native_boundary import _bounded_canonical
    from anvil.marketing_native_private_environment import current_control_environment

    if original['environment_sha256'] != hashlib.sha256(_bounded_canonical(current_control_environment(), 8192)).hexdigest():
        raise ValueError('marketing_original_control_public_environment_changed')
    _read_source_file('marketing_native_private_control.py', original['source_sha256'])
    proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        # cmdline contains NULs, so this fixed proc file needs a bounded raw read.
        fd = os.open('self/cmdline', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=proc)
        try:
            raw = os.read(fd, 8193)
        finally:
            os.close(fd)
        args = raw.rstrip(b'\x00').split(b'\x00')
        if (len(raw) > 8192 or len(args) != 7 or args[1:5] != [b'-I', b'-B', b'-m', b'anvil.marketing_native_private_control']
                or hashlib.sha256(raw).hexdigest() != original['command_sha256']
                or float(args[-1].decode('ascii')) != original['input_deadline_monotonic']
                or _pid_identity(proc, os.getpid(), context['deadline_monotonic'])[1] != original['start_ticks']
                or _read(proc, 'sys/kernel/random/boot_id', 64, context['deadline_monotonic']).strip() != context['boot_id']):
            raise ValueError('marketing_actual_one_operation_control_command_required')
    finally:
        os.close(proc)


def _packet(descriptor, deadline):
    _remaining(deadline)
    info = os.fstat(descriptor)
    if descriptor < 3 or not stat.S_ISFIFO(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError('marketing_original_private_control_pipe_required')
    os.set_blocking(descriptor, False)
    raw = bytearray()
    try:
        while True:
            _remaining(deadline)
            if not select.select([descriptor], [], [], max(0, deadline - monotonic()))[0]:
                raise TimeoutError('marketing_original_control_input_cutoff')
            chunk = os.read(descriptor, min(65536, DOCUMENT_CAP + 1 - len(raw)))
            if not chunk:
                break
            if len(raw) + len(chunk) > DOCUMENT_CAP:
                raise ValueError('marketing_original_private_control_packet_capacity')
            raw.extend(chunk)
        value = _parse_record(bytes(raw))
        if set(value) != {'schema_version', 'request', 'job', 'once_prepared'} or value['schema_version'] != 'anvil.marketing-original-private-control-input.v2':
            raise ValueError('marketing_fixed_original_private_control_packet_required')
        if type(value['job']) is not dict or type(value['request']) is not str or type(value['once_prepared']) is not str:
            raise ValueError('marketing_original_control_exact_input_types_required')
        from anvil.marketing_native_job_packet import decode_original_job

        value['job'] = decode_original_job(value['job'])
        return value
    finally:
        os.close(descriptor)


def main():
    marketing_native_gate()
    if len(sys.argv) != 3 or sys.platform != 'linux' or sys.version_info[:2] != (3, 12):
        return 42
    watcher = loop = None
    try:
        from anvil.marketing_native_actor_hardening import protect_independent_receiver

        # This dedicated control is undumpable BEFORE receiving the lease or
        # starting any preflight helper. Full capability reduction still occurs
        # only after its original SDK/graph have been spawned and enrolled.
        protect_independent_receiver()
        value = _packet(int(sys.argv[1]), float(sys.argv[2]))
        request = prepare_marketing_request(value['request'].encode('utf-8'))
        prepared = value['once_prepared'].encode('utf-8')
        # Linux pidfd watcher avoids the background waiter threads that make a
        # subsequent original graph fork inadmissible. No global app loop is
        # changed: this fixed module is a dedicated one-operation process.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        watcher = asyncio.PidfdChildWatcher()
        watcher.attach_loop(loop)
        asyncio.set_child_watcher(watcher)
        from anvil.marketing_native_launcher import launch_private_actor_framework

        loop.run_until_complete(launch_private_actor_framework(value['job'], prepared, request))
        return 0
    except BaseException:
        return 42  # Never log the lease, prepared bytes, packet or traceback.
    finally:
        if watcher is not None:
            watcher.close()
        if loop is not None:
            asyncio.set_event_loop(None)
            loop.close()


if __name__ == '__main__':
    raise SystemExit(main())
