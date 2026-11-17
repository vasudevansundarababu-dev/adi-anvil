"""Fixed in-process caller candidates; public native gates stay closed.

The explicit opening actor owner selects the opening candidate without prepared
API replay or a caller callback. No successful finish or physical capture producer
is implemented here. Actual synchronous SQL/OS/process and
remote-provider hard bounds remain unqualified despite phase-limited clients.
"""

import json

from anvil.marketing_native_attempt import MarketingAttemptStore
from anvil.marketing_native_boundary import marketing_native_gate
from anvil.marketing_native_graph_owner import _OriginalWorldOwner
from anvil.marketing_native_records import (
    resolve_marketing_candidate_records,
    resolve_marketing_opening_records,
)
from anvil.marketing_native_world_binding import (
    verify_candidate_graph_sources,
    verify_opening_graph_sources,
)


async def _cleanup_original(store, request, owner, deadline, *, opening=False, private=False):
    from anvil.marketing_native_stop import _stop
    from anvil.marketing_native_world_stop import _candidate_stop_and_observe

    try:
        world, expected = owner.original_for_cleanup(), owner.stop_scope()
    except BaseException as unavailable:
        # An attach lost reply cannot be repaired by another attach. The
        # independently owned container may still be stopped; API state stays
        # Unknown even if that container observation succeeds.
        try:
            await _stop(store, request, 'environment', opening=opening)
        except BaseException as cleanup:
            raise unavailable from cleanup
        raise
    phases = owner.phase_bounds() if opening else None
    return await _candidate_stop_and_observe(store, request, world, expected, deadline=deadline,
                                             opening=opening, phase_bounds=phases, private=private)


async def _opening_enrollment_barrier(owner):
    """Closed dependency boundary AFTER retaining the original attached world.

    SQL119 needs that original live world's Scope10. Public-ready bytes, a file
    receipt, caller boolean or registrar's uncommitted result cannot release
    graph/provider work. The independent OS peer producer and bounded registrar
    commit/readback channel are not implemented here; never fall through to the
    GraphRunner's first provider-readiness guard as a substitute. No reattach,
    polling, fresh deadline, registration attempt or key generation occurs.
    """
    owner.original_for_cleanup()
    owner.stop_scope()
    if owner._private is True:
        from anvil.marketing_native_enrollment_client import _observe_original_enrollment

        return await _observe_original_enrollment(owner)
    raise RuntimeError('marketing_opening_independent_peer_and_committed_enrollment_required')


async def _run_owned(store, connections, job, prepared_raw, request, records, *, deadline, native_guard, opening=False, private=False):
    if type(private) is not bool or private and not opening:
        raise ValueError('marketing_explicit_private_owned_graph_required')
    if opening:
        verify_opening_graph_sources(private=private)
    else:
        verify_candidate_graph_sources()
    from anvil.marketing_native_start import _check, before_business
    if opening:
        _check(store, request, role='environment', stage='before_business', opening=True)
        from anvil.marketing_native_actor_scope import require_original_graph_child

        require_original_graph_child(store, request, deadline=deadline, private=private)
    else:
        before_business(request)
    from anvil.marketing_paid_graph import GraphRunner
    from anvil.marketing_paid_world import QualifiedWorld

    owner = _OriginalWorldOwner(store, request, job, prepared_raw, records, deadline=deadline, opening=opening, private=private)
    try:
        try:
            phases = owner.phase_bounds()
            prepared = json.loads(prepared_raw)
            owner.begin_attach()
            if native_guard() is not True:
                raise RuntimeError('marketing_original_owner_liveness_before_attach')
            world = QualifiedWorld.attach(
                job, prepared, absolute_deadline=deadline,
                phase_deadline=phases['graph_deadline_monotonic'],
            )
            owner.bind_original(world, prepared_raw)
            if native_guard() is not True:
                raise RuntimeError('marketing_original_owner_liveness_after_attach')
            if opening:
                await _opening_enrollment_barrier(owner)
                if native_guard() is not True:
                    raise RuntimeError('marketing_original_owner_liveness_after_enrollment')
            if private:
                if connections is not None:
                    raise ValueError('marketing_private_graph_rejects_parent_connection_factory')
                from anvil.marketing_graph_checkpoint_database import scheduler_connections

                connections = scheduler_connections(job, absolute_deadline=phases['graph_deadline_monotonic'])
            owner.begin_graph()
            runner = GraphRunner(connections, job, prepared, world,
                                 absolute_deadline=phases['graph_deadline_monotonic'])
            owner.bind_runner(runner)
            result = runner.run(native_guard)
            owner.retain_graph_return(result)
        except BaseException as original:
            try:
                await _cleanup_original(store, request, owner, deadline, opening=opening, private=private)
            except BaseException as cleanup:
                raise original from cleanup
            raise
        else:
            # This branch is outside the graph except: a lost cleanup response
            # cannot cause a second cleanup dispatch through the error branch.
            cleanup = await _cleanup_original(store, request, owner, deadline, opening=opening, private=private)
            return {'graph_return': result, 'cleanup_observation': cleanup,
                    'whole_actor_stopped': False, 'capture_ready': False,
                    'native_qualified': False, 'durable_finish_permitted': False}
    finally:
        owner.close()


async def run_owned_marketing_graph(connections, job, prepared_raw, request, *, deadline, native_guard):
    marketing_native_gate()
    records = resolve_marketing_candidate_records(request)
    with MarketingAttemptStore() as store:
        return await _run_owned(store, connections, job, prepared_raw, request, records,
                                deadline=deadline, native_guard=native_guard)


async def run_owned_opening_graph(connections, job, prepared_raw, request, *, deadline, native_guard):
    marketing_native_gate()
    records = resolve_marketing_opening_records(request)
    with MarketingAttemptStore() as store:
        return await _run_owned(store, connections, job, prepared_raw, request, records,
                                deadline=deadline, native_guard=native_guard, opening=True)
