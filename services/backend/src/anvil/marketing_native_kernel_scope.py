"""Closed read-only original cgroup-v2 observer, NOT a whole-actor stop proof.

No group is created, moved, frozen, killed or removed. The future caller must
obtain binding bytes from independent pre-launch enrollment. A matching raw
observation cannot authenticate itself or replace process/container/capture proof.
"""

import hashlib
import math
import os
import stat
import sys
from time import monotonic

from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical, marketing_native_gate
from anvil.marketing_native_records import _parse_record

ROOT = '/sys/fs/cgroup'
MAX_DIRECTORIES = 256
FILES = {'cgroup.events': 512, 'cgroup.procs': 8192, 'cgroup.threads': 8192}


def _remaining(deadline):
    left = deadline - monotonic()
    if type(deadline) not in (int, float) or not 0 < left <= 600:
        raise TimeoutError('marketing_original_kernel_observation_deadline')


def _directory(parent, name):
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('marketing_original_kernel_directory_custody')
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read(parent, name, cap, deadline):
    _remaining(deadline)
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('marketing_original_kernel_file_custody')
        chunks, size = [], 0
        while True:
            _remaining(deadline)
            part = os.read(fd, min(4096, cap + 1 - size))
            if not part:
                break
            chunks.append(part)
            size += len(part)
            if size > cap:
                raise ValueError('marketing_kernel_observation_capacity')
        _remaining(deadline)
        return b''.join(chunks).decode('ascii')
    finally:
        os.close(fd)


def _events(raw):
    result = {}
    for line in raw.splitlines():
        pair = line.split()
        if len(pair) != 2 or pair[0] in result or pair[1] not in ('0', '1'):
            raise ValueError('marketing_exact_kernel_cgroup_events')
        result[pair[0]] = int(pair[1])
    if set(result) != {'populated', 'frozen'} or result['populated'] != 0:
        raise ValueError('marketing_kernel_scope_not_observed_empty')


def _fd_mount(proc, fd, deadline):
    raw = _read(proc, 'self/fdinfo/' + str(fd), 1024, deadline)
    values = {}
    for line in raw.splitlines():
        key, separator, value = line.partition(':')
        if not separator or key in values:
            raise ValueError('marketing_exact_kernel_fdinfo_required')
        values[key] = value.strip()
    mount = values.get('mnt_id', '')
    if not mount.isdecimal() or int(mount) <= 0:
        raise ValueError('marketing_kernel_fd_mount_identity_required')
    return int(mount), raw


def _open_scope(nonce):
    root = _directory(None, ROOT)
    try:
        for name in ('anvil-marketing', nonce[:20]):
            child = _directory(root, name)
            previous = root
            root = child
            os.close(previous)
        return root
    except BaseException:
        os.close(root)
        raise


def _bounded_entries(fd, deadline):
    names, seen = [], set()
    # listdir/sorted would allocate the entire kernel-provided collection before
    # a length check. Consume at most4096 names and reject the next item without
    # reading the remainder. Closing the iterator is required on every failure.
    with os.scandir(fd) as entries:
        for entry in entries:
            _remaining(deadline)
            if len(names) >= 4096:
                raise ValueError('marketing_kernel_directory_entry_capacity')
            name = getattr(entry, 'name', None)
            if (type(name) is not str or not name or name in ('.', '..')
                    or '/' in name or '\x00' in name or name in seen):
                raise ValueError('marketing_kernel_directory_entry_name')
            try:
                encoded = name.encode('utf-8')
            except UnicodeError:
                raise ValueError('marketing_kernel_directory_entry_name') from None
            if len(encoded) > 255:
                raise ValueError('marketing_kernel_directory_entry_name_capacity')
            seen.add(name)
            names.append(name)
    return sorted(names)


def _snapshot(root, proc, mount_id, deadline, byte_budget):
    result = []
    device = os.fstat(root).st_dev

    def walk(fd, relative):
        _remaining(deadline)
        if len(result) >= MAX_DIRECTORIES:
            raise ValueError('marketing_kernel_subtree_capacity')
        info = os.fstat(fd)
        if info.st_dev != device:
            raise ValueError('marketing_kernel_subtree_cross_mount')
        actual_mount, fdinfo = _fd_mount(proc, fd, deadline)
        if actual_mount != mount_id:
            raise ValueError('marketing_kernel_subtree_mount_identity_changed')
        raw = {name: _read(fd, name, cap, deadline) for name, cap in FILES.items()}
        _events(raw['cgroup.events'])
        if raw['cgroup.procs'].strip() or raw['cgroup.threads'].strip():
            raise ValueError('marketing_kernel_process_or_thread_remains')
        record = {'relative': relative, 'device': info.st_dev, 'inode': info.st_ino,
                  'mount_id': actual_mount, 'raw_kernel_files': raw, 'raw_fdinfo': fdinfo}
        byte_budget[0] -= len(_bounded_canonical(record, DOCUMENT_CAP)) + 2
        if byte_budget[0] < 0:
            raise ValueError('marketing_kernel_aggregate_observation_capacity')
        result.append(record)
        names = _bounded_entries(fd, deadline)
        for name in names:
            _remaining(deadline)
            member = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(member.st_mode):
                raise ValueError('marketing_kernel_subtree_alias')
            if stat.S_ISDIR(member.st_mode):
                child = _directory(fd, name)
                try:
                    walk(child, relative + '/' + name)
                finally:
                    os.close(child)

    walk(root, '.')
    return result


def _observe(binding_raw, *, deadline, byte_limit, phase_deadline=None):
    """Privileged internal candidate, with independently enrolled input only."""
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise ValueError('marketing_original_kernel_observer_root_linux_required')
    if type(byte_limit) is not int or not 1 <= byte_limit <= DOCUMENT_CAP:
        raise ValueError('marketing_existing_kernel_proof_capacity_required')
    binding = _parse_record(binding_raw)
    fields = {'schema_version', 'request_sha256', 'plan_sha256', 'operation_nonce',
              'boot_id', 'original_deadline_monotonic', 'cgroup_device', 'cgroup_inode',
              'cgroup_mount_id'}
    if (set(binding) != fields or binding['schema_version'] != 'anvil.marketing-original-kernel-scope.v1'
            or any(type(binding[k]) is not str or len(binding[k]) != 64
                   or any(c not in '0123456789abcdef' for c in binding[k])
                   for k in ('request_sha256', 'plan_sha256', 'operation_nonce'))
            or any(type(binding[k]) is not int or binding[k] <= 0
                   for k in ('cgroup_device', 'cgroup_inode', 'cgroup_mount_id'))
            or type(deadline) not in (int, float)
            or type(binding['original_deadline_monotonic']) not in (int, float)
            or binding['original_deadline_monotonic'] != deadline):
        raise ValueError('marketing_independent_original_kernel_binding_required')
    if phase_deadline is not None:
        if (type(phase_deadline) not in (int, float) or not math.isfinite(phase_deadline)
                or phase_deadline > deadline):
            raise ValueError('marketing_original_kernel_phase_may_only_narrow_deadline')
        deadline = phase_deadline
    _remaining(deadline)
    proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    root = None
    try:
        boot = _read(proc, 'sys/kernel/random/boot_id', 64, deadline).strip()
        if binding['boot_id'] != boot:
            raise ValueError('marketing_kernel_original_boot_changed')
        mounts = _read(proc, 'self/mountinfo', DOCUMENT_CAP, deadline)
        matches = []
        scoped = ROOT + '/anvil-marketing/' + binding['operation_nonce'][:20]
        for line in mounts.splitlines():
            left, separator, right = line.partition(' - ')
            fields = left.split()
            if separator and len(fields) >= 6 and (
                fields[4] == ROOT + '/anvil-marketing' or fields[4] == scoped
                or fields[4].startswith(scoped + '/')
            ):
                raise ValueError('marketing_kernel_scope_nested_mount_alias')
            if separator and len(fields) >= 6 and fields[4] == ROOT:
                if right.split()[0] != 'cgroup2':
                    raise ValueError('marketing_original_cgroup2_mount_required')
                matches.append(int(fields[0]))
        if matches != [binding['cgroup_mount_id']]:
            raise ValueError('marketing_original_cgroup_mount_identity_changed')
        root = _open_scope(binding['operation_nonce'])
        info = os.fstat(root)
        if (info.st_dev, info.st_ino) != (binding['cgroup_device'], binding['cgroup_inode']):
            raise ValueError('marketing_original_cgroup_replaced')
        byte_budget = [byte_limit - 2048]
        first = _snapshot(root, proc, binding['cgroup_mount_id'], deadline, byte_budget)
        second = _snapshot(root, proc, binding['cgroup_mount_id'], deadline, byte_budget)
        # Directory enumeration can change an FD's seek position. Keep both raw
        # fdinfo documents, but compare scope identity rather than FD cursor.
        if ([{k: v for k, v in row.items() if k != 'raw_fdinfo'} for row in first]
                != [{k: v for k, v in row.items() if k != 'raw_fdinfo'} for row in second]):
            raise ValueError('marketing_original_kernel_scope_changed_during_observation')
        reopened = _open_scope(binding['operation_nonce'])
        try:
            current = os.fstat(reopened)
            if ((current.st_dev, current.st_ino) != (binding['cgroup_device'], binding['cgroup_inode'])
                    or _fd_mount(proc, reopened, deadline)[0] != binding['cgroup_mount_id']):
                raise ValueError('marketing_kernel_scope_path_replaced_after_observation')
        finally:
            os.close(reopened)
        if _read(proc, 'sys/kernel/random/boot_id', 64, deadline).strip() != boot:
            raise ValueError('marketing_kernel_boot_changed_during_observation')
        result = {
            'schema_version': 'anvil.marketing-empty-kernel-scope-observation.v1',
            'independent_binding_sha256': hashlib.sha256(binding_raw).hexdigest(),
            'boot_id': boot, 'observed_monotonic': monotonic(),
            'snapshot_first': first, 'snapshot_second': second,
            'whole_actor_stopped': False, 'capture_ready': False, 'native_qualified': False,
        }
        raw = _bounded_canonical(result, byte_limit)
        _remaining(deadline)
        return raw
    finally:
        if root is not None:
            os.close(root)
        os.close(proc)


def observe_original_kernel_scope(binding_raw, *, deadline, byte_limit):
    marketing_native_gate()
    return _observe(binding_raw, deadline=deadline, byte_limit=byte_limit)
