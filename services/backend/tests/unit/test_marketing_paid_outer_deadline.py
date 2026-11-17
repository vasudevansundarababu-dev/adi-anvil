"""A prepared role cannot restart the host's one aggregate elapsed timer."""

import math

import pytest

from anvil.marketing_paid_roles import RoleAdapter


def adapter(clock, deadline):
    return RoleAdapter(
        None,
        {},
        "episode",
        1,
        {},
        None,
        None,
        episode_timeout_seconds=600,
        clock=clock,
        absolute_deadline=deadline,
    )


def test_late_role_construction_keeps_the_original_absolute_deadline():
    now = [100.0]
    first = adapter(lambda: now[0], 130.0)
    assert first.remaining() == 30
    now[0] = 120.0
    second = adapter(lambda: now[0], first.deadline)
    assert second.remaining() == 10
    assert second.deadline == first.deadline == 130.0
    now[0] = 130.0
    with pytest.raises(TimeoutError):
        second.remaining()


@pytest.mark.parametrize("deadline", [True, "120", math.inf, math.nan, 100.0, 99.0, 701.0])
def test_outer_deadline_cannot_be_expired_infinite_coerced_or_extended(deadline):
    with pytest.raises(ValueError, match="cannot be extended"):
        adapter(lambda: 100.0, deadline)
