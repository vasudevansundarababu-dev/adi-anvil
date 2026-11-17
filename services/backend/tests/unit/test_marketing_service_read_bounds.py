"""Fresh read-bound controls; manufactured records, no SDK/API/SQL/native work."""

from test_marketing_world_readiness import save, setup

from anvil.marketing_task2_tools import execute


def test_large_released_read_is_explicitly_unavailable_without_truncation_or_unknown_write():
    controller, execution, *_ = setup()
    controller._initial["documents"] = [
        {"actor_visible": True, "outcome_binding": None, "released_at": "2027-01-01T00:00:00Z",
         "public": {"id": "read-bound-" + str(i), "version": 1, "text": "x" * 30000}}
        for i in range(2)]
    result = execute(controller, "policy", "source_documents.read", {}, execution)
    assert result["status"] == "unavailable"
    assert result["result"]["records_silently_truncated"] is False
    narrower = execute(controller, "policy", "source_documents.read", {"resource_ref": "read-bound-0"}, execution)
    assert narrower["status"] == "completed"
    assert len(narrower["result"]["records"]) == 1


def test_large_assigned_handoff_has_explicit_narrow_query_recovery():
    controller, execution, *_ = setup()
    for index in range(3):
        ref = save(controller, "orchestrator", "readiness-requests", "bound-action-" + str(index), {"text": "x" * 19000})
        execute(controller, "orchestrator", "handoffs.assign", {"id": "bound-handoff-" + str(index), "expected_version": 0,
                "idempotency_key": "bound-handoff-" + str(index), "content": {"recipient_role": "policy", "artifact_refs": [ref]}}, execution)
    result = execute(controller, "policy", "handoffs.assigned.read", {}, execution)
    assert result["status"] == "unavailable"
    assert result["result"]["records_silently_truncated"] is False
    narrower = execute(controller, "policy", "handoffs.assigned.read", {"resource_ref": "bound-action-0"}, execution)
    assert narrower["status"] == "completed"
    assert len(narrower["result"]["assigned_artifacts"]) == 1
