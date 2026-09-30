from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from anvil.factory import FIELDS, Confirm, Selection, rank


def profile():
    dims = {k: ["common"] for k in FIELDS}
    dims["capabilities"] = ["grounding", "constraints"]
    return {"dimensions": dims, "task_revision_ids": ["task-1"]}


def benchmark(rid="a"):
    return {
        "revision_id": rid,
        "title": rid,
        "dimensions": deepcopy(profile()["dimensions"]),
        "task_revision_ids": ["task-1"],
        "blockers": [],
    }


def test_weights_exact_and_reordering_deterministic():
    a, b = benchmark("a"), benchmark("b")
    b["dimensions"]["domain"] = ["other"]
    b["dimensions"]["capabilities"] = ["grounding"]
    result = rank(profile(), [b, a], 75)
    assert result == rank(profile(), [a, b], 75)
    assert result["ranked"][0]["total_score"] == 100
    assert result["ranked"][1]["total_score"] == 72.5
    assert result["ranked"][1]["uncovered_requirements"]["capabilities"] == ["constraints"]
    assert result["ranked"][0]["cost_usd_range"] is None
    assert result["strategy"] == "direct_use"


@pytest.mark.parametrize(
    "key", ["modality", "environment", "output_artifact", "agent_type", "language_locale"]
)
def test_hard_filters_are_visible(key):
    b = benchmark()
    b["dimensions"][key] = ["incompatible"]
    result = rank(profile(), [b], 75)
    assert not result["ranked"]
    assert result["excluded"][0]["reasons"] == ["incompatible_" + key]
    assert result["strategy"] == "create_from_gaps"


def test_rights_filter_and_composition():
    a, b, blocked = benchmark("a"), benchmark("b"), benchmark("blocked")
    a["dimensions"]["capabilities"] = ["grounding"]
    b["dimensions"]["capabilities"] = ["constraints"]
    blocked["blockers"] = ["rights_not_approved_for_local_fixture"]
    result = rank(profile(), [a, b, blocked], 99)
    assert result["composition"] == ["a", "b"]
    assert result["composition_uncovered_capabilities"] == []
    assert result["below_threshold"]
    assert len(result["excluded"]) == 1
    b["dimensions"]["evaluation_target"] = ["different"]
    assert rank(profile(), [a, b], 99)["composition_uncovered_capabilities"] == ["constraints"]


def test_confirm_required_dimensions_no_duplicates_or_unconfirmed():
    body = {
        "title": "Confirmed profile",
        "objective_revision_id": str(uuid4()),
        "task_revision_ids": [str(uuid4())],
        "dimensions": profile()["dimensions"],
    }
    assert Confirm.model_validate(body).dimensions == {
        k: sorted(v) for k, v in profile()["dimensions"].items()
    }
    for dims in [
        {},
        {**profile()["dimensions"], "domain": ["unconfirmed"]},
        {**profile()["dimensions"], "risk": []},
    ]:
        with pytest.raises(ValidationError):
            Confirm.model_validate({**body, "dimensions": dims})
    with pytest.raises(ValidationError):
        Selection.model_validate(
            {
                **{k: body[k] for k in ("objective_revision_id", "task_revision_ids")},
                "task_revision_ids": body["task_revision_ids"] * 2,
            }
        )
