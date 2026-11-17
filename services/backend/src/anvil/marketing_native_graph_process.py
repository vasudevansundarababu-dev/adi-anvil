"""Fixed forked graph child; original world exists only in the enrolled child.

No world/connection serialization, caller callback or alternate entry command.
Fork safety, namespaces, FD closure and parent-death/OS bounds remain unqualified.
The independent attester has no key in this control process or its fork image.
"""

import asyncio
import ctypes
import hashlib
import os
import re
import resource
import select
import signal
import threading
from time import monotonic

from anvil.marketing_native_attempt import _write_at
from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical
from anvil.marketing_native_kernel_scope import _bounded_entries, _remaining
from anvil.marketing_native_records import _parse_record


async def _pipe_bytes(fd, *, cap, deadline):
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    output = bytearray()
    os.set_blocking(fd, False)

    def ready():
        if future.done():
            return
        try:
            chunk = os.read(fd, min(4096, cap + 1 - len(output)))
            if len(output) + len(chunk) > cap:
                raise ValueError('marketing_graph_child_reply_capacity')
            if chunk:
                output.extend(chunk)
            else:
                future.set_result(bytes(output))
        except BlockingIOError:
            return
        except BaseException as error:
            future.set_exception(error)

    loop.add_reader(fd, ready)
    try:
        return await asyncio.wait_for(future, max(0, deadline - monotonic()))
    finally:
        loop.remove_reader(fd)


def _child(owner, gate, output, parent_pid, parent_ticks):
    """No attach or business work before independent parent membership release."""
    from anvil.marketing_native_actor_scope import _pid_identity

    def original_parent_and_sdk():
        proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            deadline = owner._context['deadline_monotonic']
            if (os.getppid() != parent_pid or _pid_identity(proc, parent_pid, deadline)[1] != parent_ticks
                    or _pid_identity(proc, owner._pid, deadline) != (parent_pid, owner._ticks)):
                raise RuntimeError('marketing_graph_original_control_or_sdk_lost')
        finally:
            os.close(proc)

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), 'graph child parent-death binding failed')
    original_parent_and_sdk()
    from anvil.marketing_native_actor_hardening import harden_graph

    harden_graph()
    deadline = owner._context['deadline_monotonic']
    _remaining(deadline)
    if owner._private and os.write(output, b'R') != 1:
        raise RuntimeError('marketing_private_graph_hardening_ready_unknown')
    if not select.select([gate], [], [], max(0, deadline - monotonic()))[0] or os.read(gate, 2) != b'G':
        raise RuntimeError('marketing_graph_startup_unknown_no_replay')
    os.close(gate)
    owner._scope.graph_child_guard()
    from anvil.marketing_native_graph_caller import _run_owned

    def live():
        original_parent_and_sdk()
        owner._scope.graph_child_guard()
        from anvil.marketing_native_reconcile import _opening_context_status

        status = _opening_context_status(owner._store, owner._root, owner._claim, owner._plan)
        if status['same_boot_observed'] is not True or status['deadline_elapsed_observed'] is not False:
            raise ValueError('marketing_graph_original_context_or_boot_changed')
        return True

    # A fresh child-local loop: never run a copied parent server event loop.
    asyncio.events._set_running_loop(None)
    signal.set_wakeup_fd(-1)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_run_owned(
            owner._store, owner._connections, owner._job, owner._prepared, owner._request, owner._records,
            deadline=deadline, native_guard=live, opening=True, private=owner._private))
        live()
        receipt = {
            'schema_version': 'anvil.marketing-graph-child-return.v1',
            'state': 'original_graph_and_api_container_cleanup_returned',
            'cleanup_observation_sha256': hashlib.sha256(_bounded_canonical(result['cleanup_observation'], DOCUMENT_CAP)).hexdigest(),
            'whole_actor_stopped': False, 'capture_ready': False, 'native_qualified': False,
        }
        _write_at(owner._root, 'graph-child-cleanup-observation.json',
                  _bounded_canonical(result['cleanup_observation'], min(16384, owner._plan['bounds']['receipt_bytes'])))
        raw = _bounded_canonical(receipt, 2048)
        if os.write(output, raw) != len(raw):
            raise RuntimeError('marketing_graph_child_reply_unknown')
    finally:
        loop.close()


class _ForkedGraphProcess:
    __slots__ = ('_owner', '_pid', '_ticks', '_pidfd', '_gate', '_output', '_state', '_joined', '_hardened')

    def __init__(self, owner):
        from anvil.marketing_native_actor_scope import _pid_identity

        self._owner = owner
        self._pid = self._ticks = self._pidfd = self._gate = self._output = None
        self._state, self._joined = 'spawn_unknown_no_replay', False
        self._hardened = False
        deadline = owner._context['deadline_monotonic']
        _remaining(deadline)
        if threading.active_count() != 1:
            raise ValueError('marketing_graph_fork_requires_single_control_thread')
        task_dir = os.open('/proc/self/task', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            if _bounded_entries(task_dir, deadline) != [str(os.getpid())]:
                raise ValueError('marketing_graph_fork_requires_one_kernel_thread')
        finally:
            os.close(task_dir)
        parent_pid = os.getpid()
        proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            parent_ticks = _pid_identity(proc, parent_pid, deadline)[1]
        finally:
            os.close(proc)
        _write_at(owner._root, 'graph-process-spawn-intent.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-original-graph-process-intent.v2',
            'request_sha256': owner._claim['request_sha256'],
            'parent_pid': parent_pid, 'parent_start_ticks': parent_ticks,
            'original_deadline_monotonic': deadline, 'native_qualified': False, 'replay_permitted': False,
        }, DOCUMENT_CAP))
        read_gate, write_gate = os.pipe2(os.O_CLOEXEC)
        read_output, write_output = None, None
        try:
            read_output, write_output = os.pipe2(os.O_CLOEXEC)
            pid = os.fork()  # No QualifiedWorld exists yet; no attester key in this process.
            if pid == 0:
                code = 42
                try:
                    # Do not retain a directory FD onto the parent's writable
                    # cgroup mount: it would bypass the child's readonly view.
                    keep = {read_gate, write_output, owner._store.fd, owner._root}
                    limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
                    if limit == resource.RLIM_INFINITY or not 1 <= limit <= 1048576:
                        raise ValueError('marketing_graph_fixed_descriptor_limit_required')
                    if any(type(fd) is not int or not 3 <= fd < limit for fd in keep):
                        raise ValueError('marketing_graph_owned_descriptor_set_required')
                    start = 3
                    for fd in sorted(keep):
                        os.closerange(start, fd)
                        start = fd + 1
                    os.closerange(start, int(limit))
                    null = os.open('/dev/null', os.O_RDWR | os.O_NOFOLLOW)
                    for fd in (0, 1, 2):
                        os.dup2(null, fd)
                    if null > 2:
                        os.close(null)
                    _child(owner, read_gate, write_output, parent_pid, parent_ticks)
                    code = 0
                except BaseException:
                    pass  # No private input, lease or traceback enters any output.
                finally:
                    os._exit(code)
            self._pid = pid  # Retain actual PID before later validation can fail.
            self._gate, self._output = write_gate, read_output
            write_gate = read_output = None
            self._pidfd = os.pidfd_open(pid, 0)
            proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                actual_parent, self._ticks = _pid_identity(proc, pid, deadline)
                if actual_parent != parent_pid:
                    raise ValueError('marketing_original_forked_graph_parent_required')
            finally:
                os.close(proc)
            owner._scope.enroll('graph', pid, self._ticks)
            self._state = 'enrolled_waiting_for_actor'
        finally:
            for fd in (read_gate, write_gate, read_output, write_output):
                if fd is not None:
                    os.close(fd)

    async def observe_private_hardening_ready(self, *, deadline):
        from anvil.marketing_native_enrollment_client import _ready

        if (not self._owner._private or self._state != 'enrolled_waiting_for_actor'
                or self._hardened is not False):
            raise ValueError('marketing_original_private_graph_preG_ready_required')
        self._hardened = None
        os.set_blocking(self._output, False)
        while True:
            _remaining(deadline)
            try:
                raw = os.read(self._output, 1)
            except BlockingIOError:
                await _ready(self._output, writing=False, deadline=deadline)
                continue
            if raw != b'R':
                raise RuntimeError('marketing_private_graph_hardening_unknown_no_retry')
            self._hardened = True
            return  # No key/enrollment/run authority; G remains closed.

    async def run(self):
        if self._state != 'enrolled_waiting_for_actor':
            raise ValueError('marketing_graph_process_run_once_required')
        if self._owner._private and self._hardened is not True:
            raise ValueError('marketing_private_graph_hardening_ready_required_before_G')
        self._state = 'graph_reply_unknown_no_replay'
        owner = self._owner
        owner._scope.require_pair()
        owner._live()
        from anvil.marketing_native_actor_timing import opening_phases

        value = _parse_record(owner._request.canonical_bytes)
        phases = opening_phases(owner._plan['bounds'], deadline=owner._context['deadline_monotonic'],
                                started=owner._actor_started, now=monotonic(),
                                request_timeout=value['request_timeout_seconds'], private=owner._private)
        if os.write(self._gate, b'G') != 1:
            raise RuntimeError('marketing_graph_release_unknown')
        os.close(self._gate)
        self._gate = None
        raw = await _pipe_bytes(self._output, cap=2048, deadline=phases['actor_join_deadline_monotonic'])
        reply = _parse_record(raw)
        fields = {'schema_version', 'state', 'cleanup_observation_sha256', 'whole_actor_stopped', 'capture_ready', 'native_qualified'}
        if (set(reply) != fields or reply['schema_version'] != 'anvil.marketing-graph-child-return.v1'
                or reply['state'] != 'original_graph_and_api_container_cleanup_returned'
                or type(reply['cleanup_observation_sha256']) is not str
                or not re.fullmatch(r'[a-f0-9]{64}', reply['cleanup_observation_sha256'])
                or any(reply[key] is not False for key in ('whole_actor_stopped', 'capture_ready', 'native_qualified'))):
            raise RuntimeError('marketing_graph_child_return_unknown')
        self.join_observed(phase_deadline=phases['actor_join_deadline_monotonic'])
        scope = owner._scope.stop_graph(phase_deadline=phases['actor_join_deadline_monotonic'])
        _write_at(owner._root, 'graph-process-return.json', raw)
        self._state = 'joined_and_graph_scope_empty_NOT_whole_operation'
        _write_at(owner._root, 'graph-process-join.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-original-graph-process-join.v1',
            'pid': self._pid, 'start_ticks': self._ticks, 'wait_status': 0,
            'request_sha256': owner._claim['request_sha256'], 'plan_sha256': owner._claim['plan_sha256'],
            'operation_nonce': owner._context['operation_nonce'],
            'reply_sha256': hashlib.sha256(raw).hexdigest(),
            'graph_scope_observation_sha256': hashlib.sha256(_bounded_canonical(scope, 16384)).hexdigest(),
            'whole_operation_stopped': False, 'native_qualified': False,
        }, DOCUMENT_CAP))
        return reply

    def join_observed(self, *, allow_failure=False, phase_deadline=None):
        if self._joined or self._pid is None:
            raise ValueError('marketing_original_graph_process_join_once_required')
        deadline = self._owner._context['deadline_monotonic']
        if phase_deadline is not None:
            deadline = min(deadline, phase_deadline)
        _remaining(deadline)
        if not select.select([self._pidfd], [], [], max(0, deadline - monotonic()))[0]:
            raise TimeoutError('marketing_graph_original_join_deadline')
        pid, status = os.waitpid(self._pid, os.WNOHANG)
        if pid != self._pid:
            raise RuntimeError('marketing_graph_process_join_unknown')
        self._joined = True
        if not allow_failure and os.waitstatus_to_exitcode(status) != 0:
            raise RuntimeError('marketing_graph_child_failed_no_replay')

    async def cleanup(self):
        if self._gate is not None:
            os.close(self._gate)
            self._gate = None
        scope = self._owner._scope
        member = scope._members.get('graph', {})
        if self._pid is not None and self._pidfd is None and not self._joined:
            # fork returned this exact unreaped child synchronously. No PID
            # discovery, process-group lookup or adoption is involved. Closing
            # its original G fence precedes this acquisition-failure cleanup.
            deadline = self._owner._context['deadline_monotonic']
            _remaining(deadline)
            actual, _ = os.waitpid(self._pid, os.WNOHANG)
            if actual == self._pid:
                self._joined = True
                return
            if actual != 0:
                raise RuntimeError('marketing_original_fork_cleanup_identity_unknown')
            os.kill(self._pid, signal.SIGKILL)
            while True:
                _remaining(deadline)
                actual, _ = os.waitpid(self._pid, os.WNOHANG)
                if actual == self._pid:
                    self._joined = True
                    return
                if actual != 0:
                    raise RuntimeError('marketing_original_fork_cleanup_wait_unknown')
                await asyncio.sleep(min(.01, max(0, deadline - monotonic())))
        try:
            if member.get('state') == 'enrolled_before_release':
                scope.stop_graph()
            elif member.get('state') != 'empty_observed_NOT_whole_operation' and self._pidfd is not None:
                # An ambiguous pre-G membership write may leave the original
                # child outside its group. pidfd targets only that owned child.
                signal.pidfd_send_signal(self._pidfd, signal.SIGKILL)
        finally:
            if self._pid is not None and not self._joined and self._pidfd is not None:
                self.join_observed(allow_failure=True)

    def close(self):
        # EOF prevents an idle child from attaching. An executing child/scope
        # still needs explicit stop and join; closing these FDs proves neither.
        for field in ('_gate', '_output', '_pidfd'):
            fd = getattr(self, field)
            if fd is not None:
                setattr(self, field, None)
                os.close(fd)
