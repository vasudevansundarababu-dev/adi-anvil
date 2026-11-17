"""Source-only outside-child OS observations, NOT a qualified peer receipt.

No public message supplies process identity. No key, SQL row, registration,
signing authority or run authority is produced. Profile/isolation qualification
and an independent operator receiver remain required before an issuer can use
these diagnostics. All public native gates stay closed.
"""

import ctypes
import hashlib
import os
import re
import select
import stat

from anvil.marketing_native_attempt import _write_at
from anvil.marketing_native_boundary import _bounded_canonical, marketing_native_gate
from anvil.marketing_native_kernel_scope import (
    ROOT,
    _bounded_entries,
    _directory,
    _fd_mount,
    _read,
    _remaining,
)

STATUS_FIELDS = frozenset({'Uid', 'Gid', 'Groups', 'CapInh', 'CapPrm', 'CapEff',
                           'CapBnd', 'CapAmb', 'NoNewPrivs', 'Seccomp', 'Seccomp_filters'})
NAMESPACES = frozenset({'cgroup', 'ipc', 'mnt', 'net', 'pid', 'pid_for_children',
                        'time', 'time_for_children', 'user', 'uts'})


def _link(parent, name, deadline):
    """Fixed-buffer readlinkat; never allocate the whole kernel link first."""
    _remaining(deadline)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.readlinkat.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t]
    libc.readlinkat.restype = ctypes.c_ssize_t
    buffer = ctypes.create_string_buffer(4097)
    count = libc.readlinkat(parent, name.encode('ascii'), buffer, len(buffer))
    if count < 0:
        raise OSError(ctypes.get_errno(), 'original peer kernel link unavailable')
    if count > 4096:
        raise ValueError('marketing_peer_kernel_link_capacity')
    _remaining(deadline)
    return bytes(buffer.raw[:count]).decode('utf-8', errors='strict')


def _identity(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
            'uid': info.st_uid, 'gid': info.st_gid}


def _status(proc, pid, deadline):
    fields = {}
    for line in _read(proc, str(pid) + '/status', 32768, deadline).splitlines():
        name, separator, value = line.partition(':')
        if name in STATUS_FIELDS:
            if not separator or name in fields:
                raise ValueError('marketing_exact_peer_status_required')
            fields[name] = value.strip()
    if set(fields) != STATUS_FIELDS:
        raise ValueError('marketing_complete_peer_status_required')
    for name in ('Uid', 'Gid'):
        values = fields[name].split()
        if len(values) != 4 or any(not value.isdecimal() for value in values):
            raise ValueError('marketing_exact_peer_identity_status_required')
    if any(not value.isdecimal() for value in fields['Groups'].split()):
        raise ValueError('marketing_exact_peer_groups_required')
    if any(not re.fullmatch(r'[0-9a-f]{16}', fields[name]) for name in
           ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb')):
        raise ValueError('marketing_exact_peer_capability_status_required')
    # Read actual kernel values. No caller booleans assert privacy or isolation.
    if (fields['NoNewPrivs'] != '1' or fields['Seccomp'] != '2'
            or not fields['Seccomp_filters'].isdecimal() or int(fields['Seccomp_filters']) < 1
            or any(int(fields[name], 16) != 0 for name in
                   ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'))):
        raise ValueError('marketing_peer_kernel_privilege_reduction_not_observed')
    return fields


def _snapshot(proc, pid, deadline):
    descriptors = os.open(str(pid) + '/fd', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=proc)
    namespaces = None
    try:
        namespaces = os.open(str(pid) + '/ns', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=proc)
        files = []
        for name in _bounded_entries(descriptors, deadline):
            if not name.isdecimal() or str(int(name)) != name:
                raise ValueError('marketing_exact_peer_descriptor_number_required')
            files.append({'fd': int(name), 'target': _link(descriptors, name, deadline),
                          'fdinfo': _read(proc, str(pid) + '/fdinfo/' + name, 1024, deadline)})
            # Enforce the original peer-receipt budget DURING enumeration.
            _bounded_canonical(files, 8192)
        if set(_bounded_entries(namespaces, deadline)) != NAMESPACES:
            raise ValueError('marketing_complete_fixed_peer_namespace_inventory_required')
        identities = {}
        for name in sorted(NAMESPACES):
            _remaining(deadline)
            # Intentionally follow this fixed procfs namespace magic-link to
            # observe the kernel namespace object's device/inode, never setns.
            fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC, dir_fd=namespaces)
            try:
                identities[name] = _identity(os.fstat(fd))
            finally:
                os.close(fd)
        return {'status': _status(proc, pid, deadline), 'descriptors': files, 'namespaces': identities}
    finally:
        if namespaces is not None:
            os.close(namespaces)
        os.close(descriptors)


def _observe_outside_candidate(watchdog):
    """One observation from actual owned launch handles; no caller PID accepted.

    A watchdog alone has no attester key/public-ready protocol. A separate
    attester child additionally needs its fixed key-possession exchange and all
    independent policy evidence before these diagnostics can enter a peer row.
    """
    from anvil.marketing_native_actor_scope import _pid_identity
    from anvil.marketing_native_attester_process import _IndependentAttesterProcess
    from anvil.marketing_native_launcher import _runtime_assets
    from anvil.marketing_native_watchdog import _OuterWatchdog

    if type(watchdog) not in (_OuterWatchdog, _IndependentAttesterProcess) or watchdog._peer_observation_state != 'unobserved':
        raise ValueError('marketing_original_outside_peer_observation_once_required')
    watchdog._peer_observation_state = 'observation_unknown_no_replay'
    watchdog.require_live()
    owner = watchdog._owner
    deadline = owner._context['deadline_monotonic'] - owner._plan['bounds']['cleanup_seconds']
    if type(watchdog) is _IndependentAttesterProcess:
        deadline = min(deadline, owner._phase_deadline)
    _remaining(deadline)
    _write_at(owner._root, 'outside-peer-observation-intent.json', _bounded_canonical({
        'schema_version': 'anvil.marketing-outside-peer-observation-intent.v1',
        'request_sha256': owner._claim['request_sha256'], 'operation_nonce': owner._context['operation_nonce'],
        'original_deadline_monotonic': owner._context['deadline_monotonic'],
        'observation_deadline_monotonic': deadline, 'native_qualified': False, 'replay_permitted': False,
    }, 4096))
    proc = scope = executable = None
    try:
        proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        pid = watchdog._child.pid
        parent, ticks = _pid_identity(proc, pid, deadline)
        pidfd_info = _read(proc, 'self/fdinfo/' + str(watchdog._pidfd), 1024, deadline)
        lines = {}
        for line in pidfd_info.splitlines():
            key, separator, value = line.partition(':')
            if not separator or key in lines:
                raise ValueError('marketing_exact_owned_peer_pidfd_required')
            lines[key] = value.strip()
        if (parent != os.getpid() or lines.get('Pid') != str(pid)
                or select.select([watchdog._pidfd], [], [], 0)[0]
                or _read(proc, 'sys/kernel/random/boot_id', 64, deadline).strip() != owner._context['boot_id']):
            raise ValueError('marketing_original_owned_peer_identity_changed')
        path = _read(proc, str(pid) + '/cgroup', 4096, deadline).strip()
        if not path.startswith('0::/') or '\n' in path or path != _read(proc, 'self/cgroup', 4096, deadline).strip():
            raise ValueError('marketing_original_peer_outside_control_group_required')
        relative = path[4:]
        actor = 'anvil-marketing/' + owner._context['operation_nonce'][:20]
        if relative == actor or relative.startswith(actor + '/'):
            raise ValueError('marketing_peer_inside_actor_kill_scope')
        scope = _directory(None, ROOT)
        for name in relative.split('/') if relative else ():
            if name in ('.', '..') or not re.fullmatch(r'[A-Za-z0-9_.:@-]+', name):
                raise ValueError('marketing_fixed_peer_kernel_scope_path_required')
            child = _directory(scope, name)
            os.close(scope)
            scope = child
        mount, mount_info = _fd_mount(proc, scope, deadline)
        if mount != owner._scope._binding['cgroup_mount_id']:
            raise ValueError('marketing_original_peer_scope_mount_changed')
        interpreter, expected = _runtime_assets(owner._records, owner._plan,
                                                 {**owner._context, 'deadline_monotonic': deadline}, opening=True,
                                                 private=type(watchdog) is _IndependentAttesterProcess)
        executable = os.open(str(pid) + '/exe', os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc)
        actual = os.fstat(executable)
        if (not stat.S_ISREG(actual.st_mode) or _link(proc, str(pid) + '/exe', deadline) != str(interpreter)
                or (actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns, actual.st_ctime_ns) != expected):
            raise ValueError('marketing_owned_peer_interpreter_identity_changed')
        digest, size = hashlib.sha256(), 0
        while True:
            _remaining(deadline)
            part = os.read(executable, min(65536, actual.st_size + 1 - size))
            if not part:
                break
            size += len(part)
            if size > actual.st_size:
                raise ValueError('marketing_owned_peer_executable_grew')
            digest.update(part)
        after = os.fstat(executable)
        if (size != actual.st_size or digest.hexdigest() != owner._plan['runtime']['interpreter_sha256']
                or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != expected):
            raise ValueError('marketing_owned_peer_executable_bytes_changed')
        first = _snapshot(proc, pid, deadline)
        second = _snapshot(proc, pid, deadline)
        if first != second or _pid_identity(proc, pid, deadline) != (parent, ticks):
            raise ValueError('marketing_peer_observation_changed_no_retry')
        watchdog.require_live()
        receipt = {
            'schema_version': 'anvil.marketing-attester-os-observation.v1',
            'request_sha256': owner._claim['request_sha256'], 'operation_nonce': owner._context['operation_nonce'],
            'boot_id': owner._context['boot_id'], 'original_deadline_monotonic': owner._context['deadline_monotonic'],
            'pid': pid, 'parent_pid': parent, 'start_ticks': ticks,
            'pidfd': {'identity': _identity(os.fstat(watchdog._pidfd)), 'raw_fdinfo': pidfd_info,
                      'exit_readable_observed': False},
            'interpreter': {'path': str(interpreter), 'identity': _identity(actual),
                            'bytes': size, 'sha256': digest.hexdigest()},
            'outside_cgroup': {'path': path, 'identity': _identity(os.fstat(scope)),
                               'mount_id': mount, 'raw_fdinfo': mount_info},
            'direct_kernel_snapshot': first,
            'second_identical_snapshot_sha256': hashlib.sha256(_bounded_canonical(second, 12288)).hexdigest(),
            'independent_evidence_still_required': ['loaded_source_and_image_identity', 'dumpability_and_proc_access',
                'namespace_and_signal_isolation', 'exact_allowed_fd_endpoint_custody', 'qualified_verifier_profile',
                'attester_key_and_public_ready_binding'],
            'diagnostic_only': True, 'native_qualified': False, 'admission_eligible': False,
            'capture_accepted': False, 'run_authority': 'not_granted',
        }
        raw = _bounded_canonical(receipt, 16384)
        _remaining(deadline)
        _write_at(owner._root, 'outside-peer-os-observation.json', raw)
        watchdog._peer_observation_state = 'diagnostic_observed_NOT_peer_qualification'
        return raw
    finally:
        for fd in (executable, scope, proc):
            if fd is not None:
                os.close(fd)


def observe_outside_candidate(watchdog):
    marketing_native_gate()
    return _observe_outside_candidate(watchdog)
