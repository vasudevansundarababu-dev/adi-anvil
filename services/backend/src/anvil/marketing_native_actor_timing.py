"""Pure original opening-phase partitions; no new deadline or work authority."""

import math


def opening_phases(bounds, *, deadline, started, now, request_timeout, private=False):
    if type(private) is not bool:
        raise ValueError('marketing_explicit_private_phase_variant_required')
    if (any(type(value) not in (int, float) or not math.isfinite(value) for value in (deadline, started, now))
            or not started <= now < deadline or deadline - started > 600
            or any(type(bounds[key]) is not int or not 1 <= bounds[key] <= 600
                   for key in ('actor_seconds', 'verifier_seconds', 'cleanup_seconds'))
            or type(request_timeout) is not int or not 1 <= request_timeout <= 600):
        raise ValueError('marketing_original_opening_phase_bounds_required')
    cleanup, verifier = bounds['cleanup_seconds'], bounds['verifier_seconds']
    actor_end = min(started + bounds['actor_seconds'], deadline - cleanup - verifier)
    container_end = actor_end - 1
    api_end = container_end - cleanup
    api_reserve = min(request_timeout, cleanup)
    graph_end = api_end - api_reserve
    if graph_end - now < 1:
        raise TimeoutError('marketing_original_opening_work_partitions_exhausted')
    phases = {
        'graph_deadline_monotonic': graph_end, 'api_stop_deadline_monotonic': api_end,
        'actor_container_stop_deadline_monotonic': container_end,
        'actor_join_deadline_monotonic': actor_end,
        'verifier_work_deadline_monotonic': deadline - cleanup,
        'original_deadline_monotonic': deadline, 'existing_cleanup_seconds': cleanup,
        'api_reserved_from_graph_seconds': api_reserve, 'verifier_reserved_seconds': verifier,
        'graph_join_reserved_seconds': 1,
    }
    if private:
        # Eight seconds are SUBTRACTED from the existing verifier allocation.
        # No new wall clock, cleanup grace or increased total is introduced.
        if verifier < 20:
            raise ValueError('marketing_existing_verifier_budget_cannot_fit_private_grade_and_attester')
        phases['verifier_work_deadline_monotonic'] -= 8
        phases['attester_finalization_deadline_monotonic'] = deadline - cleanup
        phases['attester_reserved_from_verifier_seconds'] = 8
    return phases
