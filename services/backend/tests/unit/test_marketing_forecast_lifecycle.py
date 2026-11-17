import json
from pathlib import Path

import pytest

from anvil.db import digest
from anvil.marketing_task2_persistence import freeze, restore
from anvil.marketing_task2_runtime import Task2Controller
from anvil.marketing_task2_tools import execute


def setup():
    controller = Task2Controller(
        "GT2-R01",
        records={"forecasts": []},
        start="2027-01-06T00:00:00Z",
        outcome="positive",
        budget_minor=20000000,
    )
    execution = json.loads(
        (Path(__file__).parents[1] / "fixtures/veyra-template-execution-v3.json").read_text()
    )
    body = {
        "id": "forecast-1",
        "expected_version": 0,
        "idempotency_key": "forecast-key",
        "content": {"window": 1, "scenario": "bounded-software-control"},
    }
    return controller, execution, body


def test_request_persists_and_reloads_pending_instead_of_empty_success():
    controller, execution, body = setup()
    result = execute(controller, "performance", "forecasts.request", body, execution)
    assert result["status"] == "pending" and result["result"]["completion_not_observed"]
    assert controller._objects[body["id"]]["kind"] == "forecast-requests"
    state, fingerprint = freeze(controller)
    restored = restore(state, fingerprint)
    status = execute(
        restored, "performance", "operations.status.read", {"resource_ref": body["id"]}, execution
    )
    assert status["status"] == "pending" and status["result"]["records"][0]["completion"] is None
    assert (
        execute(restored, "performance", "forecasts.request", body, execution)["result"]["record"]
        == result["result"]["record"]
    )
    assert len(restored._objects) == 1


def test_exact_released_completion_and_revision_invalidation():
    controller, execution, body = setup()
    execute(controller, "performance", "forecasts.request", body, execution)
    request = controller._objects[body["id"]]
    with pytest.raises(ValueError, match="Released forecast fixture"):
        controller.complete_forecast(body["id"], 1, "fixture-1")
    controller._initial["forecasts"].append(
        {
            "actor_visible": True,
            "released_at": "2027-01-05T00:00:00Z",
            "public": {
                "id": "fixture-1",
                "request_sha256": digest(request),
                "forecast": {"origin": "manufactured_software_control", "outcome": None},
            },
        }
    )
    controller.control(
        controller.controller_credential(),
        0,
        "complete_forecast",
        {"request_id": body["id"], "version": 1, "source_ref": "fixture-1"},
        idempotency_key="host-completion",
    )
    status = execute(
        controller, "performance", "operations.status.read", {"resource_ref": body["id"]}, execution
    )
    assert status["status"] == "completed"
    assert status["result"]["records"][0]["completion"]["request_sha256"] == digest(request)
    revised = body | {
        "expected_version": 1,
        "idempotency_key": "revision",
        "content": {"window": 2},
    }
    assert (
        execute(controller, "performance", "forecasts.request", revised, execution)["status"]
        == "pending"
    )
    assert (
        execute(
            controller,
            "performance",
            "operations.status.read",
            {"resource_ref": body["id"]},
            execution,
        )["status"]
        == "pending"
    )
    with pytest.raises(ValueError, match="current forecast request"):
        controller.complete_forecast(body["id"], 1, "fixture-1")


def test_future_fixture_wrong_request_and_foreign_role_cannot_complete_forecast():
    controller, execution, body = setup()
    assert execute(controller, "intent", "forecasts.request", body, execution)["status"] == "denied"
    execute(controller, "performance", "forecasts.request", body, execution)
    controller._initial["forecasts"] = [
        {
            "actor_visible": True,
            "released_at": "2027-03-01T00:00:00Z",
            "public": {
                "id": "future",
                "request_sha256": digest(controller._objects[body["id"]]),
                "forecast": {},
            },
        }
    ]
    with pytest.raises(ValueError, match="Released forecast fixture"):
        controller.complete_forecast(body["id"], 1, "future")
    controller._initial["forecasts"][0].update(released_at="2027-01-01T00:00:00Z")
    controller._initial["forecasts"][0]["public"]["request_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="Released forecast fixture"):
        controller.complete_forecast(body["id"], 1, "future")
    foreign = execute(
        controller, "intent", "operations.status.read", {"resource_ref": body["id"]}, execution
    )
    assert foreign["status"] == "unavailable"
