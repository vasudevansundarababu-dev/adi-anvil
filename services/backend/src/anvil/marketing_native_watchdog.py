"""Fixed outside-scope watchdog launch; no attester key in this process.

Exec receives only original public metadata and pipe/pidfd handles. A future
independent attester must create/retain its key in its own isolated process.
"""

import asyncio
import hashlib
import os
import re
import select
from time import monotonic

from anvil.marketing_native_attempt import _write_at
from anvil.marketing_native_boundary import _bounded_canonical
from anvil.marketing_native_graph_process import _pipe_bytes
from anvil.marketing_native_kernel_scope import _remaining
from anvil.marketing_native_records import _parse_record


async def _write_bytes(fd, raw, deadline):
    os.set_blocking(fd, False)
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    offset = 0

    def ready():
        nonlocal offset
        if future.done():
            return
        try:
            count = os.write(fd, raw[offset:offset + 4096])
            if count <= 0:
                raise RuntimeError('marketing_watchdog_startup_write_unknown')
            offset += count
            if offset == len(raw):
                future.set_result(None)
        except BlockingIOError:
            return
        except BaseException as error:
            future.set_exception(error)

    loop.add_writer(fd, ready)
    try:
        await asyncio.wait_for(future, max(0, deadline - monotonic()))
    finally:
        loop.remove_writer(fd)


class _OuterWatchdog:
    __slots__ = ('_owner', '_child', '_command', '_result', '_state', '_pidfd', '_peer_observation_state')

    def __init__(self, owner):
        self._owner, self._child, self._command, self._result = owner, None, None, None
        self._state = 'unstarted'
        self._pidfd = None
        self._peer_observation_state = 'unobserved'

    async def start(self, interpreter):
        if self._state != 'unstarted':
            raise ValueError('marketing_original_watchdog_start_once_required')
        self._state = 'startup_unknown_no_retry'
        owner = self._owner
        deadline = owner._context['deadline_monotonic']
        _remaining(deadline)
        raw = _bounded_canonical({
            'schema_version': 'anvil.marketing-outside-watchdog-input.v1',
            'request': owner._request.canonical_bytes.decode('utf-8'),
            'kernel_binding': owner._scope._binding, 'cleanup_seconds': owner._plan['bounds']['cleanup_seconds'],
        }, 65536)
        _write_at(owner._root, 'outer-watchdog-launch-intent.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-outside-watchdog-launch-intent.v1',
            'input_sha256': hashlib.sha256(raw).hexdigest(), 'original_deadline_monotonic': deadline,
            'native_qualified': False, 'replay_permitted': False,
        }, 4096))
        initial_read, initial_write = os.pipe2(os.O_CLOEXEC)
        command_read = command_write = result_read = result_write = parent = ready_read = ready_write = None
        try:
            command_read, command_write = os.pipe2(os.O_CLOEXEC)
            result_read, result_write = os.pipe2(os.O_CLOEXEC)
            ready_read, ready_write = os.pipe2(os.O_CLOEXEC)
            parent = os.pidfd_open(os.getpid(), 0)
            self._command, self._result = command_write, result_read
            command_write = result_read = None
            self._child = await asyncio.wait_for(asyncio.create_subprocess_exec(
                str(interpreter), '-I', '-B', '-m', 'anvil.marketing_native_watchdog_worker',
                str(initial_read), str(command_read), str(result_write), str(parent), str(ready_write),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                close_fds=True, pass_fds=(initial_read, command_read, result_write, parent, ready_write),
                env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/nonexistent'},
                start_new_session=True, umask=0o077,
            ), max(0, deadline - monotonic()))
            self._pidfd = os.pidfd_open(self._child.pid, 0)
            os.close(ready_write)
            ready_write = None
            await _write_bytes(initial_write, raw, deadline)
            os.close(initial_write)
            initial_write = None
            if await _pipe_bytes(ready_read, cap=1, deadline=deadline) != b'R':
                raise RuntimeError('marketing_original_watchdog_not_observed_ready')
            self._state = 'watching_original_operation'
            self.require_live()
        finally:
            for fd in (initial_read, initial_write, command_read, command_write, result_read, result_write,
                       parent, ready_read, ready_write):
                if fd is not None:
                    os.close(fd)

    def require_live(self):
        if (self._state != 'watching_original_operation' or self._child is None or self._pidfd is None
                or self._child.returncode is not None or select.select([self._pidfd], [], [], 0)[0]
                or monotonic() >= self._owner._context['deadline_monotonic'] - self._owner._plan['bounds']['cleanup_seconds']):
            raise RuntimeError('marketing_original_outside_watchdog_not_alive')

    async def guard_framework(self, framework):
        self.require_live()
        monitor = asyncio.create_task(self._child.wait())
        failure = None
        try:
            done, _ = await asyncio.wait({framework, monitor}, return_when=asyncio.FIRST_COMPLETED,
                                         timeout=max(0, self._owner._context['deadline_monotonic'] - monotonic()))
            if monitor in done:
                raise RuntimeError('marketing_outside_watchdog_exited_during_operation')
            if framework not in done:
                raise TimeoutError('marketing_original_framework_deadline')
            self.require_live()
            return framework.result()
        except BaseException as error:
            failure = error
            raise
        finally:
            if not monitor.done():
                monitor.cancel()
            if not framework.done():
                framework.cancel()
            try:
                await asyncio.wait_for(asyncio.gather(monitor, framework, return_exceptions=True),
                                       max(0, self._owner._context['deadline_monotonic'] - monotonic()))
            except BaseException as cleanup:
                if failure is not None:
                    raise failure from cleanup
                raise

    async def finish(self, *, disarm):
        if self._state != 'watching_original_operation':
            raise RuntimeError('marketing_watchdog_outcome_unknown_no_retry')
        self._state = 'watchdog_reply_unknown_no_retry'
        deadline = self._owner._context['deadline_monotonic']
        _remaining(deadline)
        if os.write(self._command, b'D' if disarm else b'C') != 1:
            raise RuntimeError('marketing_watchdog_command_unknown')
        os.close(self._command)
        self._command = None
        raw = await _pipe_bytes(self._result, cap=2048, deadline=deadline)
        reply = _parse_record(raw)
        if (set(reply) != {'schema_version', 'state', 'observation_sha256', 'native_qualified'}
                or reply['schema_version'] != 'anvil.marketing-outside-watchdog-return.v1'
                or reply['state'] not in {'operation_empty_observed_unqualified', 'cleanup_observations_retained_unqualified'}
                or type(reply['observation_sha256']) is not str or not re.fullmatch(r'[a-f0-9]{64}', reply['observation_sha256'])
                or reply['native_qualified'] is not False):
            raise RuntimeError('marketing_watchdog_return_unknown')
        code = await asyncio.wait_for(self._child.wait(), max(0, deadline - monotonic()))
        if code != 0:
            raise RuntimeError('marketing_watchdog_process_failed')
        self._state = 'joined_unqualified'
        return reply

    def close(self):
        for field in ('_command', '_result', '_pidfd'):
            fd = getattr(self, field)
            if fd is not None:
                setattr(self, field, None)
                os.close(fd)
        # EOF asks the independent child to clean up. No kill of the watchdog,
        # new allowance, automatic second launch or successful-stop claim.
