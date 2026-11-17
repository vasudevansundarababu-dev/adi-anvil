"""Fixed outside-scope watchdog source; no signer, key, model or API authority.

Only original public request/kernel binding crosses startup stdin. No job lease,
prepared body, connections object or parent heap is inherited across exec.
Actual OS/runtime/isolation qualification is still required before admission.
"""

import asyncio
import hashlib
import os
import re
import select
import sys
from time import monotonic

from anvil.marketing_native_actor_scope import _write_control
from anvil.marketing_native_attempt import MarketingAttemptStore, _write_at
from anvil.marketing_native_boundary import (
    _bounded_canonical,
    marketing_native_gate,
    prepare_marketing_request,
)
from anvil.marketing_native_kernel_scope import _fd_mount, _observe, _open_scope, _read, _remaining
from anvil.marketing_native_mounts import _opening_context
from anvil.marketing_native_records import _parse_record

INPUT_CAP = 65536


def _original(raw):
    value = _parse_record(raw)
    if (set(value) != {'schema_version', 'request', 'kernel_binding', 'cleanup_seconds'}
            or value['schema_version'] != 'anvil.marketing-outside-watchdog-input.v1'
            or type(value['request']) is not str
            or type(value['cleanup_seconds']) is not int or not 1 <= value['cleanup_seconds'] <= 600):
        raise ValueError('marketing_original_watchdog_input_required')
    request = prepare_marketing_request(value['request'].encode('utf-8'))
    binding = value['kernel_binding']
    # The independent kernel observer checks the full binding schema when empty;
    # validate required startup identity without claiming the active group empty.
    if (type(binding) is not dict or binding.get('schema_version') != 'anvil.marketing-original-kernel-scope.v1'
            or binding.get('request_sha256') != hashlib.sha256(request.canonical_bytes).hexdigest()
            or type(binding.get('operation_nonce')) is not str or not re.fullmatch(r'[a-f0-9]{64}', binding['operation_nonce'])):
        raise ValueError('marketing_original_watchdog_kernel_binding_required')
    _remaining(binding['original_deadline_monotonic'])
    return request, binding, value['cleanup_seconds']


def _scope(binding):
    deadline = binding['original_deadline_monotonic']
    proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    scope = None
    try:
        path = '/anvil-marketing/' + binding['operation_nonce'][:20]
        own = _read(proc, 'self/cgroup', 4096, deadline).strip()
        if not own.startswith('0::/') or '\n' in own or own[3:] == path or own[3:].startswith(path + '/'):
            raise ValueError('marketing_watchdog_must_remain_outside_original_scope')
        if _read(proc, 'sys/kernel/random/boot_id', 64, deadline).strip() != binding['boot_id']:
            raise ValueError('marketing_watchdog_original_boot_changed')
        scope = _open_scope(binding['operation_nonce'])
        info = os.fstat(scope)
        if ((info.st_dev, info.st_ino) != (binding['cgroup_device'], binding['cgroup_inode'])
                or _fd_mount(proc, scope, deadline)[0] != binding['cgroup_mount_id']):
            raise ValueError('marketing_watchdog_original_scope_identity_changed')
        result, scope = scope, None
        return result
    finally:
        if scope is not None:
            os.close(scope)
        os.close(proc)


async def _containers(store, request, root, claim, plan):
    from anvil.marketing_native_engine import _request
    from anvil.marketing_native_stop import _container_binding, _created_binding, _inspect, _stop

    result = {}
    private = _parse_record(store._read(root, 'component-context-intent.json')).get('schema_version') == 'anvil.marketing-component-context-intent.v3'
    for role in ('environment', 'tests'):
        try:
            store._read(root, role + '-container.json')
            created_only = False
        except FileNotFoundError:
            try:
                store._read(root, role + '-created-container.json')
                created_only = True
            except FileNotFoundError:
                try:
                    store._read(root, role + '-physical-start-intent.json')
                except FileNotFoundError:
                    result[role] = {'state': 'no_source_start_intent_observed', 'native_qualified': False}
                else:
                    result[role] = {'state': 'start_unknown_no_owned_id_NO_BROAD_CLEANUP', 'native_qualified': False}
                continue
        try:
            try:
                store._read(root, role + '-container-stop-intent.json')
            except FileNotFoundError:
                result[role] = await _stop(store, request, role, created_only=created_only, opening=True, private=private)
            else:
                # No second mutation after a previous stop intent. An actual
                # retained success can be inspected read-only; absent success
                # remains Unknown even if a container now happens to be stopped.
                prior = _parse_record(store._read(root, role + '-container-stop-observed.json'))
                binding = (_created_binding if created_only else _container_binding)(store, root, claim, plan, role)
                if (prior.get('schema_version') != 'anvil.marketing-container-stop-observed.v2'
                        or prior.get('container_id') != binding['container_id']
                        or prior.get('binding_sha256') != hashlib.sha256(_bounded_canonical(binding, 1048576)).hexdigest()
                        or prior.get('container_stopped_observed') is not True):
                    raise ValueError('marketing_original_container_stop_readback_changed')
                context = _parse_record(store._read(root, 'component-context.json'))
                actual = await _request('inspect', binding['container_id'], deadline=context['deadline_monotonic'], private=private)
                _inspect(actual, binding, stopped=True, allow_created=created_only)
                result[role] = {'state': 'original_stop_revalidated_readonly',
                                'original_stop_sha256': hashlib.sha256(_bounded_canonical(prior, 1048576)).hexdigest(),
                                'current_inspect_sha256': hashlib.sha256(_bounded_canonical(actual, 1048576)).hexdigest(),
                                'late_start_effects_unqualified': created_only, 'native_qualified': False}
        except BaseException as error:
            # One role failure cannot suppress the other independently owned
            # container observation. No repeated stop or broad label cleanup.
            result[role] = {'state': 'container_cleanup_unknown_no_retry', 'failure_type': type(error).__name__,
                            'native_qualified': False}
    return result


def supervise(raw, command_fd, result_fd, parent_pidfd, ready_fd):
    request, binding, reserve = _original(raw)
    deadline = binding['original_deadline_monotonic']
    work_end = deadline - reserve
    with MarketingAttemptStore() as store:
        root, claim, plan = _opening_context(store, request)
        try:
            context = _parse_record(store._read(root, 'component-context.json'))
            if (binding['plan_sha256'] != claim['plan_sha256'] or binding['operation_nonce'] != context['operation_nonce']
                    or deadline != context['deadline_monotonic'] or reserve != plan['bounds']['cleanup_seconds']
                    or store._read(root, 'actor-scope-binding.json') != _bounded_canonical(binding, 65536)):
                raise ValueError('marketing_watchdog_original_operation_changed')
            _write_at(root, 'outer-watchdog-started.json', _bounded_canonical({
                'schema_version': 'anvil.marketing-outside-watchdog-started.v1',
                'pid': os.getpid(), 'binding_sha256': hashlib.sha256(_bounded_canonical(binding, 65536)).hexdigest(),
                'original_deadline_monotonic': deadline, 'cleanup_starts_monotonic': work_end,
                'native_qualified': False,
            }, 4096))
            original_group = _scope(binding)
            os.close(original_group)
            if os.write(ready_fd, b'R') != 1:
                raise RuntimeError('marketing_original_watchdog_ready_unknown')
            os.close(ready_fd)
            trigger = 'original_cleanup_reserve'
            while monotonic() < work_end:
                ready, _, _ = select.select([command_fd, parent_pidfd], [], [], max(0, work_end - monotonic()))
                if parent_pidfd in ready:
                    trigger = 'original_control_parent_exited'
                    break
                if command_fd in ready:
                    command = os.read(command_fd, 2)
                    if command == b'D':
                        # Disarm only after THIS process observes the original
                        # complete kernel scope empty, never a parent's Boolean.
                        try:
                            observed = _observe(_bounded_canonical(binding, 65536), deadline=deadline, byte_limit=16384)
                        except Exception:
                            trigger = 'disarm_denied_scope_not_independently_empty'
                            break
                        packet = {'schema_version': 'anvil.marketing-outside-watchdog-return.v1',
                                  'state': 'operation_empty_observed_unqualified',
                                  'observation_sha256': hashlib.sha256(observed).hexdigest(),
                                  'native_qualified': False}
                        encoded = _bounded_canonical(packet, 2048)
                        if os.write(result_fd, encoded) != len(encoded):
                            raise RuntimeError('marketing_watchdog_reply_unknown')
                        return
                    trigger = 'explicit_original_cleanup' if command == b'C' else 'control_pipe_closed_or_unknown'
                    break
            group = _scope(binding)
            try:
                _write_at(root, 'outer-watchdog-kill-intent.json', _bounded_canonical({
                    'schema_version': 'anvil.marketing-outside-watchdog-kill-intent.v1',
                    'trigger': trigger, 'original_deadline_monotonic': deadline,
                    'native_qualified': False, 'replay_permitted': False,
                }, 4096))
                _write_control(group, 'cgroup.freeze', b'1', deadline)
                _write_control(group, 'cgroup.kill', b'1', deadline)
            finally:
                os.close(group)
            containers = asyncio.run(_containers(store, request, root, claim, plan))
            observed = _observe(_bounded_canonical(binding, 65536), deadline=deadline, byte_limit=16384)
            record = {'schema_version': 'anvil.marketing-outside-watchdog-observation.v1',
                      'trigger': trigger, 'kernel': _parse_record(observed), 'containers': containers,
                      'whole_actor_stopped': False, 'capture_ready': False, 'native_qualified': False}
            retained = _bounded_canonical(record, 65536)
            _write_at(root, 'outer-watchdog-observation.json', retained)
            encoded = _bounded_canonical({'schema_version': 'anvil.marketing-outside-watchdog-return.v1',
                                         'state': 'cleanup_observations_retained_unqualified',
                                         'observation_sha256': hashlib.sha256(retained).hexdigest(),
                                         'native_qualified': False}, 2048)
            if os.write(result_fd, encoded) != len(encoded):
                raise RuntimeError('marketing_watchdog_reply_unknown')
        finally:
            os.close(root)


def main():
    marketing_native_gate()
    if (len(sys.argv) != 6 or sys.version_info[:2] != (3, 12) or sys.platform != 'linux'
            or os.geteuid() != 0 or os.uname().nodename != 'anvil-qa-v1'):
        return 42
    try:
        from anvil.marketing_native_actor_hardening import harden_watchdog

        harden_watchdog()
        initial, command, result, parent, ready = (int(value) for value in sys.argv[1:])
        with os.fdopen(initial, 'rb') as stream:
            raw = stream.read(INPUT_CAP + 1)
        if not 0 < len(raw) <= INPUT_CAP:
            return 42
        supervise(raw, command, result, parent, ready)
        return 0
    except BaseException:
        return 42  # No private request, traceback, job or credentials in output.


if __name__ == '__main__':
    raise SystemExit(main())
