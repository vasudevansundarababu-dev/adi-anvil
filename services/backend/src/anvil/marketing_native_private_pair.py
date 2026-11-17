"""Operator-owned prestarted control/receiver pair, source only and gated.

Prestart precedes independently binding the ACTUAL process IDs in the original
operator records and the single API prepare. Supply uses that same request/job/
prepared operation. This module never issues an approval, edits operator records,
calls API prepare, generates a qualification, or recreates an expired pair.
"""

import asyncio
import hashlib
import os
import signal
import stat
from pathlib import Path
from time import monotonic

from anvil.marketing_native_actor_scope import _pid_identity
from anvil.marketing_native_attempt import _owned
from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    _bounded_canonical,
    marketing_native_gate,
)
from anvil.marketing_native_enrollment_client import _ready
from anvil.marketing_native_kernel_scope import _remaining
from anvil.marketing_native_private_environment import (
    ISOLATED_BASE_ENV,
    current_control_environment,
)
from anvil.marketing_native_records import _parse_record
from anvil.marketing_native_world_binding import _read_source_file

_MODULES = {'control': 'anvil.marketing_native_private_control', 'receiver': 'anvil.marketing_native_receiver_worker'}
_DATABASE_ENV = {
    'control': ('ANVIL_GOLDEN_SCHEDULER_DATABASE_URL', 'ANVIL_GRAPH_SCHEDULER_DATABASE_TARGET_SHA256'),
    'receiver': ('ANVIL_CAPTURE_PEER_DATABASE_URL', 'ANVIL_CAPTURE_PEER_DATABASE_TARGET_SHA256',
                 'ANVIL_CAPTURE_REGISTRAR_DATABASE_URL', 'ANVIL_CAPTURE_REGISTRAR_DATABASE_TARGET_SHA256'),
}


def _interpreter(runtime, deadline):
    fields = {'schema_version', 'interpreter', 'interpreter_bytes', 'interpreter_sha256',
              'control_source_sha256', 'receiver_source_sha256', 'qualification_sha256'}
    if (set(runtime) != fields or runtime['schema_version'] != 'anvil.marketing-private-pair-runtime.v1'
            or type(runtime['interpreter_bytes']) is not int or runtime['interpreter_bytes'] <= 0):
        raise ValueError('marketing_original_private_pair_runtime_required')
    for key in fields - {'schema_version', 'interpreter', 'interpreter_bytes'}:
        value = runtime[key]
        if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('marketing_original_private_pair_runtime_pins_required')
    _read_source_file('marketing_native_private_control.py', runtime['control_source_sha256'])
    _read_source_file('marketing_native_receiver_worker.py', runtime['receiver_source_sha256'])
    path = Path(runtime['interpreter'])
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('marketing_original_private_pair_interpreter_required')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            os.close(parent)
            parent = child
            _owned(os.fstat(parent), 0, directory=True)
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        before = os.fstat(fd)
        _owned(before, 0)
        if not before.st_mode & stat.S_IXUSR or before.st_size != runtime['interpreter_bytes']:
            raise ValueError('marketing_private_pair_actual_interpreter_changed')
        count, sha = 0, hashlib.sha256()
        while True:
            _remaining(deadline)
            chunk = os.read(fd, 32768)
            if not chunk:
                break
            count += len(chunk)
            if count > before.st_size:
                raise ValueError('marketing_private_pair_interpreter_grew')
            sha.update(chunk)
        after = os.fstat(fd)
        def identity(i):
            return (i.st_dev, i.st_ino, i.st_mode, i.st_size, i.st_mtime_ns, i.st_ctime_ns)
        if identity(before) != identity(after) or count != before.st_size or sha.hexdigest() != runtime['interpreter_sha256']:
            raise ValueError('marketing_private_pair_original_interpreter_bytes_required')
        return str(path), identity(before)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


async def _write_original_pipe(fd, raw, deadline):
    os.set_blocking(fd, False)
    view = memoryview(raw)
    while view:
        _remaining(deadline)
        try:
            count = os.write(fd, view[:32768])
        except BlockingIOError:
            await _ready(fd, writing=True, deadline=deadline)
            continue
        if count <= 0:
            raise RuntimeError('marketing_original_private_pair_pipe_unknown_no_retry')
        view = view[count:]


class _OriginalPrivatePair:
    def __init__(self, runtime_raw, original_deadline, *, original_cleanup_seconds=None):
        self._runtime, self._deadline = _parse_record(runtime_raw), original_deadline
        if (original_cleanup_seconds is not None and
                (type(original_cleanup_seconds) is not int or not 1 <= original_cleanup_seconds <= 600)):
            raise ValueError('marketing_original_pair_cleanup_reserve_required')
        self._original_cleanup_seconds = original_cleanup_seconds
        self._input_deadline = (original_deadline if original_cleanup_seconds is None
                                else original_deadline - original_cleanup_seconds)
        self._children, self._inputs, self._metadata = {}, {}, {}
        self._ready = None
        self._state = 'unstarted'
        self._cleanup_state = 'unused'
        self._cleanup_deadline = original_deadline
        self._work_deadline = None

    async def __aenter__(self):
        try:
            await self.prestart()
            return self
        except BaseException as original:
            try:
                await self.abort()
            except BaseException as cleanup:
                raise original from cleanup
            raise

    async def __aexit__(self, _kind, original, _traceback):
        try:
            await self.abort()
        except BaseException as cleanup:
            if original is not None:
                raise original from cleanup
            raise
        return False

    async def prestart(self):
        marketing_native_gate()
        if self._state != 'unstarted' or os.geteuid() != 0:
            raise ValueError('marketing_original_private_pair_prestart_once_required')
        self._state = 'prestart_unknown_no_retry'
        _remaining(self._input_deadline)
        interpreter, expected = _interpreter(self._runtime, self._input_deadline)
        proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            for role in ('receiver', 'control'):
                incoming, outgoing = os.pipe2(os.O_CLOEXEC)
                ready_write = None
                self._inputs[role] = outgoing
                try:
                    for fd in (incoming, outgoing):
                        os.fchmod(fd, 0o600)
                    args = [interpreter, '-I', '-B', '-m', _MODULES[role], str(incoming)]
                    inherited = [incoming]
                    if role == 'receiver':
                        self._ready, ready_write = os.pipe2(os.O_CLOEXEC)
                        os.fchmod(self._ready, 0o600)
                        os.fchmod(ready_write, 0o600)
                        args.append(str(ready_write))
                        inherited.append(ready_write)
                    args.append(str(self._deadline))
                    env = current_control_environment() if role == 'control' else dict(ISOLATED_BASE_ENV)
                    public_environment_sha = hashlib.sha256(_bounded_canonical(env, 8192)).hexdigest()
                    for name in _DATABASE_ENV[role]:
                        value = os.environ.get(name)
                        if type(value) is not str or not value:
                            raise ValueError('marketing_original_fixed_database_source_required')
                        env[name] = value
                    child = await asyncio.wait_for(asyncio.create_subprocess_exec(*args, env=env,
                        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                        close_fds=True, pass_fds=tuple(inherited), start_new_session=True, umask=0o077),
                        max(0, self._input_deadline - monotonic()))
                    self._children[role] = {'child': child, 'pidfd': None}
                    self._children[role]['pidfd'] = os.pidfd_open(child.pid, 0)
                    ticks = _pid_identity(proc, child.pid, self._input_deadline)[1]
                    actual = os.stat('/proc/' + str(child.pid) + '/exe')
                    ident = (actual.st_dev, actual.st_ino, actual.st_mode, actual.st_size, actual.st_mtime_ns, actual.st_ctime_ns)
                    if ident != expected:
                        raise ValueError('marketing_private_pair_actual_exec_changed')
                    command = b'\0'.join(value.encode() for value in args) + b'\0'
                    command_fd = os.open(str(child.pid) + '/cmdline', os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                                         dir_fd=proc)
                    try:
                        actual_command = os.read(command_fd, 8193)
                    finally:
                        os.close(command_fd)
                    if actual_command != command:
                        raise ValueError('marketing_private_pair_actual_command_changed')
                    self._metadata[role] = {'pid': child.pid, 'start_ticks': ticks,
                        'command_sha256': hashlib.sha256(actual_command).hexdigest(), 'input_deadline_monotonic': self._deadline}
                    if role == 'control':
                        self._metadata[role]['environment_sha256'] = public_environment_sha
                finally:
                    os.close(incoming)
                    if ready_write is not None:
                        os.close(ready_write)
            self._state = 'prestarted_waiting_original_bound_records_NOT_qualified'
            return {role: dict(value) for role, value in self._metadata.items()}
        finally:
            os.close(proc)

    def public_prestart_metadata(self):
        """Only actual original process identities, before job input; no lease."""
        if self._state != 'prestarted_waiting_original_bound_records_NOT_qualified':
            raise ValueError('marketing_original_prestart_metadata_not_available')
        return {role: dict(value) for role, value in self._metadata.items()}

    def original_input_deadline(self):
        """Candidate input stops before its ORIGINAL cleanup tail, never later."""
        if self._state != 'prestarted_waiting_original_bound_records_NOT_qualified':
            raise ValueError('marketing_original_prestart_input_deadline_unavailable')
        return self._input_deadline

    async def supply_original(self, job, prepared_raw, request):
        marketing_native_gate()
        if self._state != 'prestarted_waiting_original_bound_records_NOT_qualified':
            raise ValueError('marketing_original_private_pair_supply_once_required')
        self._state = 'original_supply_unknown_no_retry'
        from anvil.marketing_native_attempt import MarketingAttemptStore
        from anvil.marketing_native_enrollment_receiver import _original_receiver_facts
        from anvil.marketing_native_mounts import _opening_context
        from anvil.marketing_native_private_records import resolve_private_marketing_records

        records = resolve_private_marketing_records(request)
        with MarketingAttemptStore() as store:
            root, _, plan = _opening_context(store, request)
            try:
                context = _parse_record(store._read(root, 'component-context.json'))
                facts = _original_receiver_facts(request, records, context)
                control_profile = _parse_record(dict(records.records)['host'])['payload']['control_process']
                if (any(control_profile[k] != self._metadata['control'][k] for k in self._metadata['control'])
                        or (facts.receiver_pid, facts.receiver_start_ticks) != (
                            self._metadata['receiver']['pid'], self._metadata['receiver']['start_ticks'])
                        or (facts.receiver_uid, facts.receiver_gid) != (0, 0)):
                    raise ValueError('marketing_pair_original_bound_process_profiles_required')
                self._cleanup_deadline = min(self._deadline, context['deadline_monotonic'])
                cleanup = plan['bounds']['cleanup_seconds']
                if type(cleanup) is not int or not 1 <= cleanup <= 600:
                    raise ValueError('marketing_pair_original_cleanup_reserve_required')
                if self._original_cleanup_seconds is not None and cleanup != self._original_cleanup_seconds:
                    raise ValueError('marketing_original_pair_cleanup_plan_changed')
                self._work_deadline = self._cleanup_deadline - cleanup
                _remaining(self._work_deadline)
            finally:
                os.close(root)
        receiver = _bounded_canonical({'schema_version': 'anvil.marketing-original-receiver-input.v1',
            'request': request.canonical_bytes.decode(), 'original_deadline_monotonic': self._deadline}, 65536)
        await _write_original_pipe(self._inputs['receiver'], receiver, self._work_deadline)
        os.close(self._inputs.pop('receiver'))
        os.set_blocking(self._ready, False)
        await _ready(self._ready, writing=False, deadline=self._work_deadline)
        if os.read(self._ready, 2) != b'R':
            raise RuntimeError('marketing_original_receiver_listening_unknown_no_retry')
        os.close(self._ready)
        self._ready = None
        from anvil.marketing_native_job_packet import encode_original_job

        control = _bounded_canonical({'schema_version': 'anvil.marketing-original-private-control-input.v2',
            'request': request.canonical_bytes.decode(), 'job': encode_original_job(job),
            'once_prepared': prepared_raw.decode()}, DOCUMENT_CAP)
        await _write_original_pipe(self._inputs['control'], control, self._work_deadline)
        os.close(self._inputs.pop('control'))
        codes = await asyncio.wait_for(asyncio.gather(*(v['child'].wait() for v in self._children.values())),
                                        max(0, self._work_deadline - monotonic()))
        if any(type(code) is not int or code != 0 for code in codes):
            raise RuntimeError('marketing_original_private_pair_failed_no_retry')
        self._state = 'original_pair_exits_observed'
        return {'state': self._state, 'native_qualified': False}  # Actual API acceptance is retained separately.

    async def abort(self):
        if self._cleanup_state != 'unused':
            raise RuntimeError('marketing_original_pair_cleanup_already_consumed_no_retry')
        self._cleanup_state = 'unknown_no_retry'
        # Close original startup fences before killing only retained children.
        errors = []
        inputs = list(self._inputs.values())
        self._inputs.clear()
        for fd in inputs:
            try:
                os.close(fd)
            except BaseException as error:
                errors.append(error)  # No retry of an ambiguously closed FD.
        if self._ready is not None:
            ready = self._ready
            self._ready = None
            try:
                os.close(ready)
            except BaseException as error:
                errors.append(error)
        # Terminate BOTH exact owned children before checking any expired wait
        # budget. Expiry cannot suppress cleanup signals or skip the second
        # child because the first wait failed. It never creates a fresh grace.
        for value in self._children.values():
            child, pidfd = value['child'], value['pidfd']
            if child.returncode is None:
                try:
                    if pidfd is None:
                        child.kill()
                    else:
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # Await the original owned child; this isn't reap proof.
                except BaseException as error:
                    errors.append(error)
        for value in self._children.values():
            child, pidfd = value['child'], value['pidfd']
            try:
                if child.returncode is None:
                    _remaining(self._cleanup_deadline)
                    await asyncio.wait_for(child.wait(), max(0, self._cleanup_deadline - monotonic()))
                else:
                    await child.wait()  # Already observed terminal; no new wait budget.
            except BaseException as error:
                errors.append(error)
            finally:
                if pidfd is not None:
                    value['pidfd'] = None
                    try:
                        os.close(pidfd)
                    except BaseException as error:
                        errors.append(error)
        if errors:
            raise RuntimeError('marketing_original_pair_cleanup_unknown_no_retry') from errors[0]
        self._cleanup_state = 'original_children_reaped'
