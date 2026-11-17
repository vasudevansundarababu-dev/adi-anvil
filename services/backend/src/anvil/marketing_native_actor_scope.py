"""Original two-subgroup cgroup-v2 producer source; no native admission.

Control stays outside; SDK and graph are enrolled while their startup pipes are
closed. Kernel observations do not qualify namespace/key isolation or hard bounds.
No existing group is reused, removed or repaired after an uncertain operation.
"""

import hashlib
import os
import re
import select
import stat
from pathlib import Path
from time import monotonic

from anvil.marketing_native_attempt import _write_at
from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical
from anvil.marketing_native_kernel_scope import (
    ROOT,
    _directory,
    _fd_mount,
    _observe,
    _read,
    _remaining,
    _snapshot,
)
from anvil.marketing_native_records import _parse_record
from anvil.marketing_native_world_binding import _read_source_file

ROLES = frozenset({'framework', 'graph'})
PROFILE = 'opening-framework-and-graph-cgroup2-v2'


def _write_control(fd, name, value, deadline):
    if name not in {'pids.max', 'memory.max', 'cpu.max', 'cgroup.subtree_control', 'cgroup.procs', 'cgroup.kill',
                    'cgroup.freeze', 'cgroup.max.depth', 'cgroup.max.descendants'}:
        raise ValueError('marketing_fixed_actor_kernel_control_required')
    _remaining(deadline)
    if type(value) is not bytes or not 0 < len(value) <= 128:
        raise ValueError('marketing_bounded_actor_kernel_control_required')
    control = os.open(name, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
    try:
        info = os.fstat(control)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('marketing_owned_actor_kernel_control_required')
        if os.write(control, value) != len(value):
            raise RuntimeError('marketing_actor_kernel_write_unknown_no_retry')
        _remaining(deadline)
    finally:
        os.close(control)


def _pid_identity(proc, pid, deadline):
    raw = _read(proc, str(pid) + '/stat', 4096, deadline)
    if ') ' not in raw:
        raise ValueError('marketing_original_actor_process_identity_required')
    tail = raw.rsplit(') ', 1)[1].split()
    if len(tail) < 20:
        raise ValueError('marketing_original_actor_process_identity_required')
    return int(tail[1]), int(tail[19])


def require_original_graph_child(store, request, *, deadline, private=False):
    """Read-only custody guard; never grants enrollment/native qualification.

    Reopen the child's own readonly cgroup view. The parent's mount ID changes
    across the private bind mount and cannot substitute for this observation.
    Stored enrollment intent alone is insufficient: actual PID/start/membership
    and both original kernel directory identities must also match now.
    """
    from anvil.marketing_native_mounts import _context_version

    _remaining(deadline)
    root, claim, _ = _context_version(store, request, opening=True)
    proc = scope = graph = None
    try:
        context = _parse_record(store._read(root, 'component-context.json'))
        raw = store._read(root, 'actor-scope-binding.json')
        binding = _parse_record(raw)
        children = _parse_record(store._read(root, 'actor-scope-children.json'))
        enrolled = _parse_record(store._read(root, 'graph-scope-enrollment-intent.json'))
        spawn = _parse_record(store._read(root, 'graph-process-spawn-intent.json'))
        digest = hashlib.sha256(raw).hexdigest()
        if (deadline != context['deadline_monotonic']
                or binding['original_deadline_monotonic'] != deadline
                or any(binding[key] != expected for key, expected in (
                    ('request_sha256', claim['request_sha256']), ('plan_sha256', claim['plan_sha256']),
                    ('operation_nonce', context['operation_nonce']), ('boot_id', context['boot_id'])))
                or binding['schema_version'] != 'anvil.marketing-original-kernel-scope.v1'
                or children['schema_version'] != ('anvil.marketing-original-actor-scope-children.v2' if private else
                                                   'anvil.marketing-original-actor-scope-children.v1')
                or children['binding_sha256'] != digest or children['native_qualified'] is not False
                or set(children['children']) != (ROLES | {'host_helpers'} if private else ROLES)
                or set(enrolled) != {'schema_version', 'role', 'pid', 'start_ticks',
                                    'original_scope_binding_sha256', 'original_deadline_monotonic', 'native_qualified'}
                or enrolled['schema_version'] != 'anvil.marketing-actor-child-enrollment-intent.v1'
                or enrolled['role'] != 'graph' or enrolled['original_scope_binding_sha256'] != digest
                or enrolled['original_deadline_monotonic'] != deadline or enrolled['native_qualified'] is not False
                or type(enrolled['pid']) is not int or enrolled['pid'] != os.getpid()
                or type(enrolled['start_ticks']) is not int or enrolled['start_ticks'] <= 0):
            raise ValueError('marketing_original_enrolled_graph_child_required')
        nonce = context['operation_nonce']
        if type(nonce) is not str or not re.fullmatch(r'[a-f0-9]{64}', nonce):
            raise ValueError('marketing_original_graph_child_nonce_required')
        proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        expected = '0::/anvil-marketing/' + nonce[:20] + '/graph'
        if (spawn.get('schema_version') != 'anvil.marketing-original-graph-process-intent.v2'
                or spawn.get('request_sha256') != claim['request_sha256']
                or type(spawn.get('parent_pid')) is not int or spawn['parent_pid'] != os.getppid()
                or type(spawn.get('parent_start_ticks')) is not int
                or _pid_identity(proc, spawn['parent_pid'], deadline)[1] != spawn['parent_start_ticks']
                or _pid_identity(proc, os.getpid(), deadline) != (os.getppid(), enrolled['start_ticks'])
                or _read(proc, 'self/cgroup', 4096, deadline).strip() != expected
                or _read(proc, 'sys/kernel/random/boot_id', 64, deadline).strip() != context['boot_id']):
            raise ValueError('marketing_original_graph_child_process_changed')
        # Open every path component without following symlinks.
        scope = _directory(None, ROOT)
        for name in ('anvil-marketing', nonce[:20]):
            child = _directory(scope, name)
            os.close(scope)
            scope = child
        info = os.fstat(scope)
        if (info.st_dev, info.st_ino) != (binding['cgroup_device'], binding['cgroup_inode']):
            raise ValueError('marketing_original_graph_child_scope_replaced')
        graph = _directory(scope, 'graph')
        identity = children['children']['graph']
        info = os.fstat(graph)
        if (info.st_dev, info.st_ino) != (identity['device'], identity['inode']):
            raise ValueError('marketing_original_graph_child_subgroup_replaced')
        mount, _ = _fd_mount(proc, graph, deadline)
        rows = [line.split() for line in _read(proc, 'self/mountinfo', 65536, deadline).splitlines()]
        matches = [row for row in rows if row and row[0] == str(mount)]
        if len(matches) != 1:
            raise ValueError('marketing_original_graph_child_visible_mount_required')
        row = matches[0]
        separator = row.index('-')
        if (separator < 6 or len(row) != separator + 4 or row[4] != ROOT
                or row[separator + 1] != 'cgroup2' or 'ro' not in row[5].split(',')):
            raise ValueError('marketing_original_graph_child_readonly_cgroup_view_required')
        _remaining(deadline)
        return True
    finally:
        for fd in (graph, scope, proc, root):
            if fd is not None:
                os.close(fd)


class _ActorKernelScope:
    __slots__ = ('_store', '_attempt', '_deadline', '_proc', '_base', '_root', '_nodes',
                 '_identities', '_members', '_binding', '_binding_raw', '_closed', '_private', '_helpers')

    def __init__(self, store, attempt, claim, plan, context, records, *, private=False):
        if type(private) is not bool:
            raise ValueError('marketing_explicit_private_scope_variant_required')
        self._private, self._helpers = private, {}
        self._proc = self._base = self._root = None
        self._nodes, self._members, self._identities = {}, {}, {}
        self._closed = False
        self._store, self._attempt = store, attempt
        self._deadline = context['deadline_monotonic']
        _remaining(self._deadline)
        host = _parse_record(dict(records.records)['host'])['payload']
        profile = host.get('actor_scope')
        fields = {'schema_version', 'profile_id', 'scope_root', 'source_sha256',
                  'kernel_observer_sha256', 'graph_process_sha256', 'watchdog_source_sha256',
                  'watchdog_worker_sha256', 'actor_owner_sha256', 'actor_capture_sha256', 'actor_timing_sha256',
                  'child_hardening_sha256', 'peer_observer_sha256',
                  'qualification_sha256', 'cpus', 'memory_mb', 'pids_limit'}
        if private:
            fields.add('helper_process_sha256')
        if private:
            from anvil.marketing_native_verifier_renderer import private_context_assets

            private_assets, _ = private_context_assets(records)
            resources = private_assets['resources']
        else:
            resources = _parse_record(dict(records.records)['task'])['payload']['render_assets']['resources']
        if (type(profile) is not dict or set(profile) != fields
                or profile['schema_version'] != ('anvil.marketing-actor-scope-profile.v3' if private else
                                                  'anvil.marketing-actor-scope-profile.v2')
                or profile['profile_id'] != ('opening-framework-graph-host-helpers-cgroup2-v1' if private else PROFILE)
                or profile['scope_root'] != ROOT + '/anvil-marketing'
                or any(type(profile[k]) is not str or not re.fullmatch(r'[a-f0-9]{64}', profile[k])
                       for k in ('source_sha256', 'kernel_observer_sha256', 'graph_process_sha256',
                                 'watchdog_source_sha256', 'watchdog_worker_sha256', 'actor_owner_sha256',
                                 'actor_capture_sha256', 'actor_timing_sha256', 'child_hardening_sha256',
                                 'peer_observer_sha256', 'qualification_sha256'))
                or any(type(profile[k]) is not int or profile[k] <= 0 or profile[k] != resources[k]
                       for k in ('cpus', 'memory_mb', 'pids_limit'))):
            raise ValueError('marketing_independent_original_actor_scope_profile_required')
        # These are file/source custody checks only. The private qualification
        # reference must still be independently admitted before gates can open.
        _read_source_file(Path(__file__).name, profile['source_sha256'])
        _read_source_file('marketing_native_kernel_scope.py', profile['kernel_observer_sha256'])
        _read_source_file('marketing_native_graph_process.py', profile['graph_process_sha256'])
        _read_source_file('marketing_native_watchdog.py', profile['watchdog_source_sha256'])
        _read_source_file('marketing_native_watchdog_worker.py', profile['watchdog_worker_sha256'])
        _read_source_file('marketing_native_actor_owner.py', profile['actor_owner_sha256'])
        _read_source_file('marketing_native_actor_capture.py', profile['actor_capture_sha256'])
        _read_source_file('marketing_native_actor_timing.py', profile['actor_timing_sha256'])
        _read_source_file('marketing_native_actor_hardening.py', profile['child_hardening_sha256'])
        _read_source_file('marketing_native_attester_peer.py', profile['peer_observer_sha256'])
        if private:
            _read_source_file('marketing_native_helper_process.py', profile['helper_process_sha256'])
        nonce = context['operation_nonce']
        if type(nonce) is not str or not re.fullmatch(r'[a-f0-9]{64}', nonce):
            raise ValueError('marketing_original_actor_scope_nonce_required')
        _write_at(attempt, 'actor-scope-intent.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-original-actor-scope-intent.v1',
            **{key: claim[key] for key in ('job_id', 'request_sha256', 'plan_sha256', 'scope')},
            'operation_nonce': nonce, 'profile_sha256': hashlib.sha256(_bounded_canonical(profile, DOCUMENT_CAP)).hexdigest(),
            'original_deadline_monotonic': self._deadline, 'native_qualified': False, 'replay_permitted': False,
        }, DOCUMENT_CAP))
        try:
            self._proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            root = _directory(None, ROOT)
            try:
                self._base = _directory(root, 'anvil-marketing')
            finally:
                os.close(root)
            os.mkdir(nonce[:20], 0o700, dir_fd=self._base)  # Exclusive, no reuse/unlink.
            self._root = _directory(self._base, nonce[:20])
            info = os.fstat(self._root)
            mount, _ = _fd_mount(self._proc, self._root, self._deadline)
            self._binding = {
                'schema_version': 'anvil.marketing-original-kernel-scope.v1',
                'request_sha256': claim['request_sha256'], 'plan_sha256': claim['plan_sha256'],
                'operation_nonce': nonce, 'boot_id': context['boot_id'],
                'original_deadline_monotonic': self._deadline,
                'cgroup_device': info.st_dev, 'cgroup_inode': info.st_ino, 'cgroup_mount_id': mount,
            }
            self._binding_raw = _bounded_canonical(self._binding, DOCUMENT_CAP)
            _observe(self._binding_raw, deadline=self._deadline, byte_limit=16384)
            _write_control(self._root, 'pids.max', str(profile['pids_limit']).encode(), self._deadline)
            _write_control(self._root, 'memory.max', str(profile['memory_mb'] * 1048576).encode(), self._deadline)
            _write_control(self._root, 'cpu.max', (str(profile['cpus'] * 100000) + ' 100000').encode(), self._deadline)
            _write_control(self._root, 'cgroup.max.depth', b'1', self._deadline)
            _write_control(self._root, 'cgroup.max.descendants', b'3' if private else b'2', self._deadline)
            _write_control(self._root, 'cgroup.subtree_control', b'+pids +memory +cpu', self._deadline)
            for role in sorted(ROLES | {'host_helpers'} if private else ROLES):
                os.mkdir(role, 0o700, dir_fd=self._root)
                self._nodes[role] = _directory(self._root, role)
                node = os.fstat(self._nodes[role])
                self._identities[role] = (node.st_dev, node.st_ino)
            _write_at(attempt, 'actor-scope-binding.json', self._binding_raw)
            _write_at(attempt, 'actor-scope-children.json', _bounded_canonical({
                'schema_version': ('anvil.marketing-original-actor-scope-children.v2' if private else
                                   'anvil.marketing-original-actor-scope-children.v1'),
                'binding_sha256': hashlib.sha256(self._binding_raw).hexdigest(),
                'children': {role: {'device': identity[0], 'inode': identity[1], 'mount_id': mount}
                             for role, identity in self._identities.items()},
                'native_qualified': False,
            }, 4096))
            for name, expected in (('pids.max', str(profile['pids_limit'])),
                                   ('memory.max', str(profile['memory_mb'] * 1048576)),
                                   ('cpu.max', str(profile['cpus'] * 100000) + ' 100000'),
                                   ('cgroup.max.depth', '1'), ('cgroup.max.descendants', '3' if private else '2')):
                if _read(self._root, name, 128, self._deadline).strip() != expected:
                    raise ValueError('marketing_original_actor_resource_limit_readback_changed')
            self._outside()
        except BaseException:
            self.close()
            raise

    def _outside(self):
        _remaining(self._deadline)
        if self._closed:
            raise ValueError('marketing_actor_scope_closed')
        parent = '/anvil-marketing/' + self._binding['operation_nonce'][:20]
        own = _read(self._proc, 'self/cgroup', 4096, self._deadline).strip()
        if not own.startswith('0::/') or '\n' in own or own[3:] == parent or own[3:].startswith(parent + '/'):
            raise ValueError('marketing_independent_control_must_be_outside_actor_scope')
        if _read(self._proc, 'sys/kernel/random/boot_id', 64, self._deadline).strip() != self._binding['boot_id']:
            raise ValueError('marketing_actor_scope_original_boot_changed')
        current = _directory(self._base, self._binding['operation_nonce'][:20])
        try:
            info = os.fstat(current)
            if (info.st_dev, info.st_ino) != (self._binding['cgroup_device'], self._binding['cgroup_inode']):
                raise ValueError('marketing_actor_scope_replaced')
        finally:
            os.close(current)

    def enroll(self, role, pid, ticks):
        self._outside()
        if _read(self._root, 'cgroup.freeze', 32, self._deadline).strip() != '0':
            raise ValueError('marketing_original_actor_scope_already_fenced')
        if role not in ROLES or role in self._members or type(pid) is not int or pid <= 1 or type(ticks) is not int or ticks <= 0:
            raise ValueError('marketing_original_actor_child_enrollment_once_required')
        if _pid_identity(self._proc, pid, self._deadline) != (os.getpid(), ticks):
            raise ValueError('marketing_original_direct_child_identity_required')
        pidfd = os.pidfd_open(pid, 0)
        self._members[role] = {'pid': pid, 'start_ticks': ticks, 'pidfd': pidfd, 'state': 'enrollment_unknown_no_replay'}
        _write_at(self._attempt, role + '-scope-enrollment-intent.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-actor-child-enrollment-intent.v1', 'role': role,
            'pid': pid, 'start_ticks': ticks, 'original_scope_binding_sha256': hashlib.sha256(self._binding_raw).hexdigest(),
            'original_deadline_monotonic': self._deadline, 'native_qualified': False,
        }, DOCUMENT_CAP))
        _write_control(self._nodes[role], 'cgroup.procs', str(pid).encode(), self._deadline)
        expected = '0::/anvil-marketing/' + self._binding['operation_nonce'][:20] + '/' + role
        if (_pid_identity(self._proc, pid, self._deadline) != (os.getpid(), ticks)
                or _read(self._proc, str(pid) + '/cgroup', 4096, self._deadline).strip() != expected):
            raise RuntimeError('marketing_actor_child_membership_unknown_no_replay')
        self._members[role]['state'] = 'enrolled_before_release'

    def require_pair(self):
        self._outside()
        if _read(self._root, 'cgroup.freeze', 32, self._deadline).strip() != '0':
            raise ValueError('marketing_original_actor_scope_already_fenced')
        if set(self._members) != ROLES or any(v['state'] != 'enrolled_before_release' for v in self._members.values()):
            raise ValueError('marketing_both_original_children_required_before_release')

    def enroll_helper(self, pid, ticks, operation_id):
        """One actual control child, still behind its fixed pre-exec fence."""
        self._outside()
        if (not self._private or type(operation_id) is not str or not re.fullmatch(r'[a-z_]+(?::[a-z_]+){1,3}', operation_id)
                or operation_id in self._helpers or type(pid) is not int or type(ticks) is not int
                or _read(self._root, 'cgroup.freeze', 32, self._deadline).strip() != '0'
                or _pid_identity(self._proc, pid, self._deadline) != (os.getpid(), ticks)):
            raise ValueError('marketing_original_host_helper_enrollment_once_required')
        pidfd = os.pidfd_open(pid, 0)
        self._helpers[operation_id] = {'pid': pid, 'start_ticks': ticks, 'pidfd': pidfd, 'state': 'enrollment_unknown_no_replay'}
        tag = hashlib.sha256(operation_id.encode('ascii')).hexdigest()
        _write_at(self._attempt, 'host-helper-' + tag + '-intent.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-host-helper-enrollment-intent.v1', 'operation_id': operation_id,
            'pid': pid, 'start_ticks': ticks, 'original_scope_binding_sha256': hashlib.sha256(self._binding_raw).hexdigest(),
            'original_deadline_monotonic': self._deadline, 'native_qualified': False,
        }, 4096))
        _write_control(self._nodes['host_helpers'], 'cgroup.procs', str(pid).encode(), self._deadline)
        expected = '0::/anvil-marketing/' + self._binding['operation_nonce'][:20] + '/host_helpers'
        if (_pid_identity(self._proc, pid, self._deadline) != (os.getpid(), ticks)
                or _read(self._proc, str(pid) + '/cgroup', 4096, self._deadline).strip() != expected):
            raise RuntimeError('marketing_original_helper_membership_unknown_no_replay')
        self._helpers[operation_id]['state'] = 'enrolled_before_exec_release'

    def observe_helper_exit(self, operation_id):
        self._outside()
        value = self._helpers.get(operation_id)
        if value is None or value['state'] != 'enrolled_before_exec_release' or not select.select([value['pidfd']], [], [], 0)[0]:
            raise ValueError('marketing_original_helper_exit_not_observed')
        value['state'] = 'owned_helper_exit_observed_NOT_subtree_empty'
        tag = hashlib.sha256(operation_id.encode('ascii')).hexdigest()
        _write_at(self._attempt, 'host-helper-' + tag + '-exit.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-host-helper-exit-observed.v1', 'operation_id': operation_id,
            'pid': value['pid'], 'start_ticks': value['start_ticks'],
            'binding_sha256': hashlib.sha256(self._binding_raw).hexdigest(),
            'original_deadline_monotonic': self._deadline, 'whole_operation_stopped': False, 'native_qualified': False,
        }, 4096))

    def graph_child_guard(self):
        # Used only in the already forked graph child. Parent-side membership
        # dictionaries are NOT used as authority across the fork boundary.
        _remaining(self._deadline)
        expected = '0::/anvil-marketing/' + self._binding['operation_nonce'][:20] + '/graph'
        proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            if _read(proc, 'self/cgroup', 4096, self._deadline).strip() != expected:
                raise ValueError('marketing_graph_execution_outside_original_scope')
        finally:
            os.close(proc)
        return True

    def stop_graph(self, *, phase_deadline=None):
        deadline = self._deadline if phase_deadline is None else phase_deadline
        if type(deadline) not in (int, float) or deadline > self._deadline:
            raise ValueError('marketing_original_graph_stop_phase_required')
        _remaining(deadline)
        self._outside()
        if self._members.get('graph', {}).get('state') != 'enrolled_before_release':
            raise ValueError('marketing_original_graph_scope_required_for_stop')
        self._members['graph']['state'] = 'stop_unknown_no_replay'
        node = os.fstat(self._nodes['graph'])
        if (node.st_dev, node.st_ino) != self._identities['graph']:
            raise ValueError('marketing_original_graph_scope_identity_changed')
        _write_at(self._attempt, 'graph-scope-stop-intent.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-graph-scope-stop-intent.v1',
            'binding_sha256': hashlib.sha256(self._binding_raw).hexdigest(),
            'original_deadline_monotonic': self._deadline, 'native_qualified': False,
        }, DOCUMENT_CAP))
        _write_control(self._nodes['graph'], 'cgroup.freeze', b'1', deadline)
        _write_control(self._nodes['graph'], 'cgroup.kill', b'1', deadline)
        events_fd = os.open('cgroup.events', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                            dir_fd=self._nodes['graph'])
        try:
            poller = select.poll()
            poller.register(events_fd, select.POLLPRI | select.POLLERR)
            for _ in range(64):
                _remaining(deadline)
                os.lseek(events_fd, 0, os.SEEK_SET)
                observed = os.read(events_fd, 513)
                if len(observed) > 512:
                    raise ValueError('marketing_graph_scope_events_capacity')
                values = dict(line.split() for line in observed.decode('ascii').splitlines())
                if values.get('populated') == '0' and values.get('frozen') == '1':
                    break
                if set(values) != {'populated', 'frozen'} or any(v not in {'0', '1'} for v in values.values()):
                    raise ValueError('marketing_graph_scope_events_unknown')
                poller.poll(max(0, min(50, int((deadline - monotonic()) * 1000))))
            else:
                raise RuntimeError('marketing_graph_scope_stop_unknown_no_retry')
        finally:
            os.close(events_fd)
        # Two bounded snapshots must actually be empty; a requested kill alone
        # grants no proof. SDK remains alive in its sibling verifier scope.
        budget = [16384 - 2048]
        first = _snapshot(self._nodes['graph'], self._proc, self._binding['cgroup_mount_id'], deadline, budget)
        second = _snapshot(self._nodes['graph'], self._proc, self._binding['cgroup_mount_id'], deadline, budget)
        if ([{k: v for k, v in row.items() if k != 'raw_fdinfo'} for row in first]
                != [{k: v for k, v in row.items() if k != 'raw_fdinfo'} for row in second]):
            raise ValueError('marketing_graph_scope_changed_during_empty_observation')
        result = {'schema_version': 'anvil.marketing-empty-graph-subscope-observation.v1',
                  'binding_sha256': hashlib.sha256(self._binding_raw).hexdigest(),
                  'first': first, 'second': second, 'whole_operation_stopped': False,
                  'capture_ready': False, 'native_qualified': False}
        _write_at(self._attempt, 'graph-scope-empty.json', _bounded_canonical(result, 16384))
        self._members['graph']['state'] = 'empty_observed_NOT_whole_operation'
        return result

    def observe_operation_empty(self):
        self._outside()
        return _observe(self._binding_raw, deadline=self._deadline, byte_limit=16384)

    def close(self):
        self._closed = True
        descriptors = [*(v['pidfd'] for v in self._members.values()), *(v['pidfd'] for v in self._helpers.values()),
                       *self._nodes.values(), self._root, self._base, self._proc]
        self._nodes, self._members, self._helpers = {}, {}, {}
        self._root = self._base = self._proc = None
        for fd in descriptors:
            if fd is not None:
                os.close(fd)
        # No rmdir, unlink, new group, re-enrollment or cleanup success claim.
