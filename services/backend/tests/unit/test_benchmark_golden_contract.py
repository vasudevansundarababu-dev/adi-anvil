from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from anvil.benchmark_golden import historical_binding


def test_historical_task_identity_must_match_even_for_drafts():
    with (
        patch(
            "anvil.benchmark_dashboard.resolve_anchor",
            return_value={"kind": "historical_control", "current_authority": False},
        ),
        patch(
            "anvil.benchmark_dashboard_traces.metadata",
            return_value={"metadata": {"task_id": "FX-002"}},
        ),
    ):
        with pytest.raises(HTTPException) as error:
            historical_binding(object(), uuid4(), "FX-001")
        assert error.value.status_code == 409


def test_historical_reference_never_establishes_current_authority():
    with patch(
        "anvil.benchmark_dashboard.resolve_anchor",
        return_value={"kind": "comparison_cell", "current_authority": True},
    ):
        with pytest.raises(HTTPException) as error:
            historical_binding(object(), uuid4(), "FX-001")
        assert error.value.status_code == 409
