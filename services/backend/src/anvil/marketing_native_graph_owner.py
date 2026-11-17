"""Closed candidate in-process ownership of one original attached world.

Not a child launcher, resolver, durable finish or physical stop.
The separate opening actor owner selects this candidate; ordinary entry remains
unchanged. Its trusted caller must keep this object AND the store alive through
graph execution and independent cleanup, including exceptions/cancellation.
"""

import hashlib
import json
import os
from time import monotonic
from uuid import UUID

from anvil.marketing_native_attempt import _write_at
from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    MarketingCampaignRequestV1,
    _bounded_canonical,
    _verify_attached_world_identity,
    encode_graph_result,
    marketing_native_gate,
    prepare_marketing_request,
    validate_prepared_graph_binding,
)
from anvil.marketing_native_mounts import _context_version
from anvil.marketing_native_reconcile import _context_status_version
from anvil.marketing_native_records import MarketingRecordBytesV1, _parse_record
from anvil.marketing_native_world_binding import (
    validate_candidate_prepared_world_binding,
    validate_candidate_world_binding,
    validate_opening_prepared_world_binding,
    validate_opening_world_binding,
    validate_private_prepared_world_binding,
    validate_private_world_binding,
)


class _OriginalWorldOwner:
    __slots__ = ('_store', '_root', '_request', '_claim', '_plan', '_deadline',
                 '_state', '_world', '_runner', '_prepared_sha256', '_world_record', '_lease_sha256',
                 '_phases', '_stop_scope', '_opening', '_private')

    def __init__(self, store, request, job, prepared_raw, records, *, deadline, opening=False, private=False):
        if type(private) is not bool or private and not opening:
            raise ValueError('marketing_explicit_private_world_owner_required')
        if type(request) is not MarketingCampaignRequestV1:
            raise ValueError('marketing_exact_owner_request_required')
        prepare_marketing_request(request.canonical_bytes)
        value = json.loads(request.canonical_bytes)
        if (type(records) is not MarketingRecordBytesV1
                or records.request_sha256 != hashlib.sha256(request.canonical_bytes).hexdigest()
                or type(job) is not dict or any(str(job[field]) != value[key] for key, field in (
                    ('job_id', 'id'), ('project_id', 'project_id'),
                    ('plan_id', 'plan_id'), ('actor_id', 'actor_id'),
                ))):
            raise ValueError('marketing_exact_original_job_and_records_required')
        lease = str(job['lease_token'])
        if str(UUID(lease)) != lease:
            raise ValueError('marketing_exact_original_job_lease_required')
        prepared = _parse_record(prepared_raw)
        if validate_prepared_graph_binding(request, prepared) != prepared_raw:
            raise ValueError('marketing_exact_once_prepared_canonical_bytes_required')
        world_record = dict(records.records)['world']
        _, stop_scope_raw = (validate_private_prepared_world_binding if private else
                             validate_opening_prepared_world_binding if opening else
                             validate_candidate_prepared_world_binding)(request, prepared, world_record)
        if _parse_record(stop_scope_raw)['lease_sha256'] != hashlib.sha256(lease.encode()).hexdigest():
            raise ValueError('marketing_independent_original_stop_lease_required')
        prepared_sha256 = hashlib.sha256(prepared_raw).hexdigest()
        root, claim, plan = _context_version(store, request, opening=opening)
        self._root = None
        try:
            retained = _context_status_version(store, root, claim, plan, opening=opening)
            context = _parse_record(store._read(root, 'component-context.json'))
            if (retained['same_boot_observed'] is not True
                    or retained['deadline_elapsed_observed'] is not False
                    or deadline != context['deadline_monotonic']):
                raise ValueError('marketing_current_original_owner_context_required')
            cleanup = plan['bounds']['cleanup_seconds']
            actor = plan['bounds']['actor_seconds']
            if (type(cleanup) is not int or not 1 <= cleanup <= 600
                    or type(actor) is not int or not 1 <= actor <= 600):
                raise ValueError('marketing_existing_lifecycle_partitions_required')
            now = monotonic()
            # Reserve API time from graph work, preserving the ENTIRE existing
            # physical-cleanup interval. No added allowance or world rebinding.
            api_reserve = min(value['request_timeout_seconds'], cleanup)
            api_deadline = deadline - cleanup
            graph_deadline = min(api_deadline - api_reserve, now + actor)
            if graph_deadline - now < 1:
                raise TimeoutError('marketing_original_graph_work_interval_exhausted')
            phases = {
                'graph_deadline_monotonic': graph_deadline,
                'api_stop_deadline_monotonic': api_deadline,
                'original_deadline_monotonic': deadline,
                'existing_cleanup_seconds': cleanup,
                'api_reserved_from_graph_seconds': api_reserve,
            }
            if opening:
                from anvil.marketing_native_actor_timing import opening_phases

                actor_intent = _parse_record(store._read(root, 'opening-actor-control-intent.json'))
                phases = opening_phases(plan['bounds'], deadline=deadline,
                                        started=actor_intent['actor_started_monotonic'], now=now,
                                        request_timeout=value['request_timeout_seconds'], private=private)
            # This is a once-only custody claim BEFORE the future caller may
            # attach/run. Existing/partial intent cannot be repaired or reclaimed.
            _write_at(root, 'original-world-owner-intent.json', _bounded_canonical({
                'schema_version': ('anvil.marketing-original-world-owner-intent.v2' if private else
                                   'anvil.marketing-original-world-owner-intent.v1'),
                **{k: claim[k] for k in ('job_id', 'request_sha256', 'plan_sha256', 'scope')},
                'once_prepared_sha256': prepared_sha256,
                'lease_sha256': hashlib.sha256(lease.encode()).hexdigest(),
                'independent_stop_scope_sha256': hashlib.sha256(stop_scope_raw).hexdigest(),
                'original_world_scope': {
                    key: prepared['world_attachment'][key] for key in (
                        'project_id', 'actor_id', 'job_id', 'plan_id', 'world_binding_id',
                        'world_binding_sha256', 'episode_id', 'generation', 'execution_sha256',
                    )
                },
                'original_deadline_monotonic': deadline,
                'phase_bounds': phases,
                'native_qualified': False,
            }, DOCUMENT_CAP))
            self._store, self._root = store, root
            self._request, self._claim, self._plan = request, claim, plan
            self._deadline, self._prepared_sha256 = deadline, prepared_sha256
            self._world_record = world_record
            self._stop_scope = stop_scope_raw
            self._lease_sha256 = hashlib.sha256(lease.encode()).hexdigest()
            self._phases = tuple(phases.items())
            self._opening = opening
            self._private = private
            self._state, self._world, self._runner = 'claimed_no_world', None, None
        except BaseException:
            os.close(root)
            raise

    def __reduce__(self):
        raise TypeError('original world owner cannot be serialized or resumed')

    def phase_bounds(self):
        self._current()
        return dict(self._phases)

    def stop_scope(self):
        self._current()
        return _parse_record(self._stop_scope)

    def _current(self):
        if self._root is None:
            raise ValueError('marketing_world_owner_closed')
        retained = _context_status_version(self._store, self._root, self._claim, self._plan, opening=self._opening)
        if (retained['same_boot_observed'] is not True
                or retained['deadline_elapsed_observed'] is not False):
            raise ValueError('marketing_world_owner_context_expired_or_foreign_boot')

    def bind_original(self, world, prepared_raw):
        """Only the trusted attach-once caller may supply its actual result."""
        from anvil.marketing_paid_world import QualifiedWorld

        if (self._state != 'attach_unknown_no_replay' or self._world is not None
                or type(world) is not QualifiedWorld):
            raise ValueError('marketing_original_attach_result_once_required')
        # Preserve the actual returned object BEFORE validation or an elapsed
        # context check can fail. A late/foreign return remains private Unknown;
        # retaining it never grants permission to use or stop that world.
        self._world, self._state = world, 'attached_identity_unknown_no_replay'
        self._current()
        if (type(prepared_raw) is not bytes
                or hashlib.sha256(prepared_raw).hexdigest() != self._prepared_sha256
                or world._deadline != self._deadline):
            raise ValueError('marketing_original_attach_result_once_required')
        _verify_attached_world_identity(self._request, world)
        (validate_private_world_binding if self._private else
         validate_opening_world_binding if self._opening else validate_candidate_world_binding)(
            self._request, world.binding_projection, self._world_record)
        if hashlib.sha256(str(world._job['lease_token']).encode()).hexdigest() != self._lease_sha256:
            raise ValueError('marketing_original_attached_lease_changed')
        self._state = 'attached_no_run'

    def begin_attach(self):
        self._current()
        if dict(self._phases)['graph_deadline_monotonic'] - monotonic() < 1:
            raise TimeoutError('marketing_original_attach_phase_exhausted')
        if self._state != 'claimed_no_world':
            raise ValueError('marketing_original_attach_once_required')
        self._state = 'attach_unknown_no_replay'
        _write_at(self._root, 'original-world-attach-intent.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-original-world-attach-intent.v1',
            'request_sha256': self._claim['request_sha256'],
            'once_prepared_sha256': self._prepared_sha256,
            'lease_sha256': self._lease_sha256,
            'original_deadline_monotonic': self._deadline,
        }, DOCUMENT_CAP))

    def begin_graph(self):
        self._current()
        if dict(self._phases)['graph_deadline_monotonic'] - monotonic() < 1:
            raise TimeoutError('marketing_original_graph_phase_exhausted')
        if self._state != 'attached_no_run':
            raise ValueError('marketing_original_graph_once_required')
        self._state = 'graph_unknown_no_replay'
        _write_at(self._root, 'original-world-graph-intent.json', _bounded_canonical({
            'schema_version': 'anvil.marketing-original-world-graph-intent.v1',
            'request_sha256': self._claim['request_sha256'],
            'once_prepared_sha256': self._prepared_sha256,
            'original_deadline_monotonic': self._deadline,
            'native_qualified': False,
        }, DOCUMENT_CAP))

    def retain_graph_return(self, result):
        from anvil.marketing_graph_result import validate_graph_result

        self._current()
        if (self._state != 'graph_unknown_no_replay' or self._runner is None or type(result) is not tuple
                or len(result) != 2):
            raise ValueError('marketing_original_graph_return_required')
        self._state = 'graph_return_unknown_no_replay'
        if dict(self._phases)['graph_deadline_monotonic'] - monotonic() <= 0:
            raise TimeoutError('marketing_graph_return_phase_exhausted')
        validate_graph_result(result, job=self._runner.job, prepared=self._runner.prepared,
                              world=self._world)
        output, receipt = encode_graph_result(
            *result, output_limit=self._plan['bounds']['output_bytes'],
            receipt_limit=self._plan['bounds']['receipt_bytes'],
        )
        # Private graph return bytes only. These filenames cannot satisfy the
        # collector's captured-*/actor-stop contracts or a component stop ack.
        for name, raw in (('graph-returned-output.json', output),
                          ('graph-returned-receipt.json', receipt)):
            _write_at(self._root, name, raw)
            if self._store._read(self._root, name) != raw:
                raise ValueError('marketing_original_graph_return_bytes_changed')
        self._current()
        if dict(self._phases)['graph_deadline_monotonic'] - monotonic() <= 0:
            raise TimeoutError('marketing_graph_retention_phase_exhausted')
        self._state = 'graph_returned_NOT_finished_or_captured'

    def bind_runner(self, runner):
        """Retain the fixed caller's actual constructor result, never a factory."""
        from anvil.marketing_paid_graph import GraphRunner

        self._current()
        value = json.loads(self._request.canonical_bytes)
        if (self._state != 'graph_unknown_no_replay' or self._runner is not None
                or type(runner) is not GraphRunner or runner.world is not self._world
                or hashlib.sha256(_bounded_canonical(runner.prepared, DOCUMENT_CAP)).hexdigest()
                != self._prepared_sha256
                or any(str(runner.job[field]) != value[key] for key, field in (
                    ('job_id', 'id'), ('project_id', 'project_id'),
                    ('plan_id', 'plan_id'), ('actor_id', 'actor_id'),
                ))
                or hashlib.sha256(str(runner.job['lease_token']).encode()).hexdigest()
                != self._lease_sha256
                or runner.roles.deadline != dict(self._phases)['graph_deadline_monotonic']):
            raise ValueError('marketing_exact_original_graph_runner_required')
        self._runner = runner

    def original_for_cleanup(self):
        self._current()
        if self._world is None or self._state not in {
            'attached_no_run', 'graph_unknown_no_replay', 'graph_return_unknown_no_replay',
            'graph_returned_NOT_finished_or_captured',
        }:
            raise ValueError('marketing_no_original_world_cleanup_remains_unknown')
        return self._world

    def close(self):
        # Closing this FD is NOT graph/process/container shutdown. Never clear
        # intents, serialize the world, reattach or infer any finished state.
        if self._root is not None:
            os.close(self._root)
            self._root = None


def claim_original_world_owner(store, request, job, prepared_raw, *, deadline):
    marketing_native_gate()
    from anvil.marketing_native_records import resolve_marketing_candidate_records

    records = resolve_marketing_candidate_records(request)
    return _OriginalWorldOwner(store, request, job, prepared_raw, records, deadline=deadline)
