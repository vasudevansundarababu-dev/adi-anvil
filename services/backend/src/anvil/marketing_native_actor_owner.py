"""Process-local opening actor custody; no whole-actor/stop acknowledgement.

Only the fixed gated root launcher constructs this owner from the ORIGINAL
prepared worker invocation. Socket events supply none of those inputs. Actual
containment, root attester isolation, loaded origin and hard bounds are unqualified.
"""

import hashlib
import json
import os
from copy import deepcopy
from time import monotonic

from anvil.marketing_native_attempt import _write_at
from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    MarketingCampaignRequestV1,
    _bounded_canonical,
    validate_prepared_graph_binding,
)
from anvil.marketing_native_mounts import _opening_context
from anvil.marketing_native_reconcile import _opening_context_status
from anvil.marketing_native_records import MarketingRecordBytesV1, _parse_record
from anvil.marketing_native_world_binding import (
    validate_opening_prepared_world_binding,
    validate_private_prepared_world_binding,
    verify_opening_graph_sources,
)


class _OpeningActorOwner:
    __slots__ = ('_store', '_root', '_request', '_records', '_claim', '_plan', '_context',
                 '_connections', '_job', '_prepared', '_state', '_pid', '_ticks', '_result', '_scope', '_graph',
                 '_actor_started', '_watchdog', '_stop_states', '_private')

    def __init__(self, store, connections, job, prepared_raw, request, records, *, private=False):
        if type(private) is not bool:
            raise ValueError('marketing_explicit_private_actor_variant_required')
        if private and connections is not None:
            raise ValueError('marketing_private_graph_factory_must_be_constructed_only_in_child')
        self._private = private
        if type(request) is not MarketingCampaignRequestV1 or type(records) is not MarketingRecordBytesV1:
            raise ValueError('marketing_original_opening_actor_inputs_required')
        value = json.loads(request.canonical_bytes)
        if (records.request_sha256 != hashlib.sha256(request.canonical_bytes).hexdigest()
                or type(job) is not dict or any(str(job[field]) != value[key] for key, field in (
                    ('job_id', 'id'), ('project_id', 'project_id'), ('plan_id', 'plan_id'), ('actor_id', 'actor_id')))):
            raise ValueError('marketing_original_opening_actor_job_required')
        prepared = _parse_record(prepared_raw)
        if validate_prepared_graph_binding(request, prepared) != prepared_raw:
            raise ValueError('marketing_original_opening_actor_prepared_required')
        _, scope_raw = (validate_private_prepared_world_binding if private else validate_opening_prepared_world_binding)(
            request, prepared, dict(records.records)['world'])
        if _parse_record(scope_raw)['lease_sha256'] != hashlib.sha256(str(job['lease_token']).encode()).hexdigest():
            raise ValueError('marketing_original_opening_actor_lease_changed')
        verify_opening_graph_sources(private=private)
        root, claim, plan = _opening_context(store, request)
        self._root = None
        self._scope = self._graph = None
        self._watchdog = None
        self._actor_started = None
        self._stop_states = {'environment': 'not_requested', 'tests': 'not_requested'}
        try:
            status = _opening_context_status(store, root, claim, plan)
            if status['same_boot_observed'] is not True or status['deadline_elapsed_observed'] is not False:
                raise ValueError('marketing_current_opening_actor_context_required')
            context = _parse_record(store._read(root, 'component-context.json'))
            control_identity = {}
            if private:
                from anvil.marketing_native_actor_scope import _pid_identity
                from anvil.marketing_native_private_control import require_private_control_custody
                from anvil.marketing_native_verifier_renderer import (
                    private_context_assets,
                    validate_private_program,
                )

                require_private_control_custody(records, context)
                proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
                try:
                    control_identity = {'control_pid': os.getpid(), 'control_start_ticks': _pid_identity(
                        proc, os.getpid(), context['deadline_monotonic'])[1]}
                finally:
                    os.close(proc)
                _, program = private_context_assets(records)
                program_raw = validate_private_program(program)
                if (store._read(root, 'private-verifier-program.json') != program_raw
                        or _bounded_canonical(program['scope'], DOCUMENT_CAP) != scope_raw
                        or _parse_record(dict(records.records)['runtime'])['payload']['launcher']['schema_version']
                        != 'anvil.marketing-launcher-assets.v3'):
                    raise ValueError('marketing_original_private_actor_program_and_runtime_required')
            _write_at(root, 'opening-actor-owner-intent.json', _bounded_canonical({
                'schema_version': ('anvil.marketing-opening-actor-owner-intent.v2' if private else
                                   'anvil.marketing-opening-actor-owner-intent.v1'),
                **{key: claim[key] for key in ('job_id', 'request_sha256', 'plan_sha256', 'scope', 'operator_program_sha256')},
                'once_prepared_sha256': hashlib.sha256(prepared_raw).hexdigest(),
                'context_sha256': status['context_sha256'],
                'original_deadline_monotonic': context['deadline_monotonic'],
                **control_identity,
                'native_qualified': False, 'replay_permitted': False,
            }, DOCUMENT_CAP))
            self._store, self._root, self._request, self._records = store, root, request, records
            self._claim, self._plan, self._context = claim, plan, context
            self._connections, self._job, self._prepared = connections, deepcopy(job), prepared_raw
            self._state, self._pid, self._ticks, self._result = 'claimed_no_framework', None, None, None
            from anvil.marketing_native_actor_scope import _ActorKernelScope

            self._scope = _ActorKernelScope(store, root, claim, plan, context, records, private=private)
        except BaseException:
            os.close(root)
            raise

    def __reduce__(self):
        raise TypeError('opening actor owner cannot be serialized or resumed')

    def bind_framework(self, pid, ticks):
        from anvil.marketing_native_launcher import _process_identity

        if self._watchdog is None:
            raise ValueError('marketing_original_outside_watchdog_required_before_release')
        self._watchdog.require_live()
        if (self._root is None or self._state != 'claimed_no_framework'
                or type(pid) is not int or pid <= 1 or type(ticks) is not int or ticks <= 0
                or _process_identity(pid) != ticks):
            raise ValueError('marketing_original_actor_framework_identity_required')
        binding = _parse_record(self._store._read(self._root, 'host-control-binding.json'))
        if (binding.get('framework_pid') != pid or binding.get('framework_start_ticks') != ticks
                or binding.get('schema_version') != 'anvil.marketing-host-control-binding.v2'
                or binding.get('operator_program_sha256') != self._claim['operator_program_sha256']
                or binding.get('context_sha256') != hashlib.sha256(
                    self._store._read(self._root, 'component-context.json')).hexdigest()):
            raise ValueError('marketing_original_actor_framework_binding_changed')
        self._pid, self._ticks, self._state = pid, ticks, 'framework_bound_no_actor'
        self._scope.enroll('framework', pid, ticks)
        from anvil.marketing_native_graph_process import _ForkedGraphProcess

        # Retain the process owner BEFORE spawn or membership can fail.
        self._graph = _ForkedGraphProcess.__new__(_ForkedGraphProcess)
        _ForkedGraphProcess.__init__(self._graph, self)
        self._scope.require_pair()

    async def start_watchdog(self, interpreter):
        from anvil.marketing_native_watchdog import _OuterWatchdog

        if self._watchdog is not None:
            raise ValueError('marketing_original_watchdog_once_required')
        self._watchdog = _OuterWatchdog(self)
        await self._watchdog.start(interpreter)

    async def watch_framework(self, framework):
        if self._watchdog is None:
            raise ValueError('marketing_original_outside_watchdog_required')
        return await self._watchdog.guard_framework(framework)

    def _live(self):
        from anvil.marketing_native_launcher import _process_identity

        if self._root is None or self._pid is None or _process_identity(self._pid) != self._ticks:
            raise ValueError('marketing_original_actor_framework_lost')
        status = _opening_context_status(self._store, self._root, self._claim, self._plan)
        if status['same_boot_observed'] is not True or status['deadline_elapsed_observed'] is not False:
            raise ValueError('marketing_original_actor_deadline_or_boot_changed')
        return True  # Liveness observation only, never containment/qualification.

    async def execute(self, request, raw):
        from anvil.marketing_native_collector import EVENT_FIELDS

        if (self._root is None or self._state != 'framework_bound_no_actor'
                or type(request) is not MarketingCampaignRequestV1
                or request.canonical_bytes != self._request.canonical_bytes):
            raise ValueError('marketing_original_actor_once_only_required')
        store = self._store
        event = _parse_record(raw)
        entry = _parse_record(store._read(self._root, 'framework-entry.json'))
        if (set(event) != EVENT_FIELDS or event.get('schema_version') != 'anvil.marketing-component-event.v1'
                or event.get('event') != 'actor' or event.get('role') != 'environment'
                or any(event.get(key) != self._claim[key] for key in ('job_id', 'request_sha256', 'plan_sha256'))
                or event.get('operation_nonce') != self._context['operation_nonce']
                or event.get('framework_trial_id') != entry['framework_trial_id']
                or event.get('session_id') != self._claim['trial_name'] + '__env'):
            raise ValueError('marketing_original_actor_bound_event_required')
        # State is consumed BEFORE custody writes or graph execution. Unknown,
        # cancellation and lost replies can never redispatch this owner.
        self._state = 'actor_unknown_no_replay'
        self._actor_started = monotonic()
        self._live()
        _write_at(self._root, 'opening-actor-control-intent.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-opening-actor-control-intent.v1',
            'event_sha256': hashlib.sha256(raw).hexdigest(),
            'framework_pid': self._pid, 'framework_start_ticks': self._ticks,
            'original_deadline_monotonic': self._context['deadline_monotonic'],
            'actor_started_monotonic': self._actor_started,
            'native_qualified': False, 'replay_permitted': False,
        }, DOCUMENT_CAP))
        if self._graph is None:
            raise ValueError('marketing_original_enrolled_graph_process_required')
        self._result = await self._graph.run()
        self._live()
        self._state = 'graph_returned_NOT_whole_actor_or_sealed'
        # Exact component ACK only; private graph results stay with this owner
        # and root-held files. This is never a stop/capture/finish ACK.
        return {**event, 'status': 'recorded'}

    async def stop(self, request, raw):
        from anvil.marketing_native_actor_capture import produce_actor_capture
        from anvil.marketing_native_actor_timing import opening_phases
        from anvil.marketing_native_collector import EVENT_FIELDS
        from anvil.marketing_native_stop import _stop

        if (self._root is None or type(request) is not MarketingCampaignRequestV1
                or request.canonical_bytes != self._request.canonical_bytes):
            raise ValueError('marketing_original_stop_owner_required')
        event = _parse_record(raw)
        entry = _parse_record(self._store._read(self._root, 'framework-entry.json'))
        role = event.get('role')
        if (set(event) != EVENT_FIELDS or event.get('schema_version') != 'anvil.marketing-component-event.v1'
                or event.get('event') != 'stop' or role not in self._stop_states
                or any(event.get(key) != self._claim[key] for key in ('job_id', 'request_sha256', 'plan_sha256'))
                or any(event.get(key) != entry[key] for key in ('operation_nonce', 'framework_trial_id'))
                or event.get('session_id') != self._claim['trial_name'] + ('__env' if role == 'environment' else '__verifier__trial')
                or self._stop_states[role] != 'not_requested'
                or self._state != 'graph_returned_NOT_whole_actor_or_sealed'
                or role == 'tests' and self._stop_states['environment'] != 'acknowledged_actor_scope_ONLY'):
            raise ValueError('marketing_original_bound_stop_once_required')
        self._stop_states[role] = 'unknown_no_replay'
        _write_at(self._root, role + '-stop-control-intent.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-role-stop-control-intent.v1',
            'event_sha256': hashlib.sha256(raw).hexdigest(), 'role': role,
            'original_deadline_monotonic': self._context['deadline_monotonic'],
            'native_qualified': False, 'replay_permitted': False,
        }, 4096))
        self._live()
        self._watchdog.require_live()
        if role == 'environment':
            observed = await produce_actor_capture(self)
            receipt_sha = observed['native_stop_receipt_sha256']
            if self._private:
                from anvil.marketing_native_enrollment_client import request_original_private_input

                # Only metadata returns; the independently isolated worker
                # obtains and seals all private facts before this SDK ACK.
                await request_original_private_input(self)
        else:
            value = _parse_record(self._request.canonical_bytes)
            phases = opening_phases(self._plan['bounds'], deadline=self._context['deadline_monotonic'],
                                    started=self._actor_started, now=self._actor_started,
                                    request_timeout=value['request_timeout_seconds'], private=self._private)
            observed = await _stop(self._store, request, 'tests', opening=True,
                                   phase_deadline=phases['verifier_work_deadline_monotonic'], private=self._private)
            receipt_sha = hashlib.sha256(_bounded_canonical(observed, DOCUMENT_CAP)).hexdigest()
        self._live()
        self._stop_states[role] = 'acknowledged_actor_scope_ONLY'
        # The SDK asks about a role. This never acknowledges the still-running
        # framework/whole operation, attester seal, upload or successful finish.
        return {**event, 'status': 'recorded', 'stopped': True, 'stop_receipt_sha256': receipt_sha}

    async def shutdown(self):
        failure = None
        try:
            if self._graph is not None:
                await self._graph.cleanup()
        except BaseException as error:
            failure = error
        if self._watchdog is not None:
            try:
                complete = False
                if failure is None and all(value == 'acknowledged_actor_scope_ONLY' for value in self._stop_states.values()):
                    exited = _parse_record(self._store._read(self._root, 'framework-exit-observed.json'))
                    complete = (type(exited.get('returncode')) is int and exited['returncode'] == 0
                                and exited.get('pid') == self._pid and exited.get('start_ticks') == self._ticks)
                await self._watchdog.finish(disarm=complete)
            except BaseException as watchdog_error:
                if failure is not None:
                    raise failure from watchdog_error
                raise
        if failure is not None:
            raise failure
        if self._scope is not None:
            observed = self._scope.observe_operation_empty()
            _write_at(self._root, 'operation-kernel-empty.json', observed)
            return _parse_record(observed)  # Kernel observation only, no acceptance.

    def close(self):
        if self._root is not None:
            root, self._root = self._root, None
            self._state = 'closed_NOT_stop_proof'
            self._connections = self._job = self._prepared = self._result = None
            try:
                if self._graph is not None:
                    self._graph.close()
            finally:
                try:
                    if self._watchdog is not None:
                        self._watchdog.close()
                    if self._scope is not None:
                        self._scope.close()
                finally:
                    os.close(root)
