"""Task2 synthetic controller safety; not model, market or human acceptance."""

import pytest

from anvil.marketing_task2_runtime import Task2Controller


def episode():
    return Task2Controller(
        "GT2-R01",
        records={
            "reports": [
                {
                    "actor_visible": True,
                    "released_at": "2027-01-05T00:00:00Z",
                    "public": {"id": "released"},
                },
                {
                    "actor_visible": True,
                    "released_at": "2027-02-01T00:00:00Z",
                    "public": {"id": "FUTURE"},
                },
                {
                    "actor_visible": True,
                    "released_at": "2027-01-05T00:00:00Z",
                    "outcome_binding": "negative",
                    "public": {"id": "OTHER-WORLD"},
                },
                {
                    "actor_visible": False,
                    "released_at": "2027-01-01T00:00:00Z",
                    "public": {"id": "KEY"},
                },
            ]
        },
        start="2027-01-06T00:00:00Z",
        outcome="positive",
        budget_minor=10000,
    )


def test_only_released_selected_public_evidence():
    env = episode()
    token = env.credential("intent_analyst")
    assert env.call(token, 0, "evidence", {"collection": "reports"})["records"] == [
        {"id": "released"}
    ]
    assert env.call(token, 0, "evidence", {"collection": "private"})["status"] == "denied"
    assert "positive" not in str(env.call(token, 0, "context", {}))


def test_role_version_idempotency_and_reset_isolation():
    env = episode()
    role = env.credential("intent_analyst")
    body = {
        "id": "analysis",
        "expected_version": 0,
        "idempotency_key": "one",
        "content": {"result": "supported"},
    }
    assert env.call(role, 0, "plans", body)["code"] == "role_scope"
    created = env.call(role, 0, "intent-assessments", body)
    assert created["version"] == 1
    assert env.call(role, 0, "intent-assessments", body) == created
    changed = body | {"content": {}}
    assert env.call(role, 0, "intent-assessments", changed)["code"] == "idempotency_conflict"
    created["content"]["result"] = "external-mutation"
    assert env.call(role, 0, "get", {"id": "analysis"})["content"]["result"] == "supported"
    env.reset()
    assert env.history and env.audit
    assert env.call(role, 0, "context", {})["code"] == "wrong_trial_or_generation"
    fresh = env.credential("intent_analyst")
    assert env.call(fresh, 1, "get", {"id": "analysis"})["code"] == "object_not_found"


def test_controller_only_approval_and_accounting_no_double_count():
    env = episode()
    role = env.credential("campaign_orchestrator")
    body = {
        "id": "request",
        "expected_version": 0,
        "idempotency_key": "one",
        "content": {"purpose": "simulated experiment"},
    }
    env.call(role, 0, "approval-requests", body)
    for operation in ("approve", "advance", "activate", "ledger-write", "reset"):
        assert env.call(role, 0, operation, {})["status"] == "denied"
    with pytest.raises(ValueError, match="approval"):
        env.reserve("request", 1, 2000)
    env.decide("request", 1, approved=True, amount_bound=2000)
    env.reserve("request", 1, 2000)
    env.reserve("request", 1, 2000)
    env.convert("request", 1, 1500)
    env.settle(1500)
    assert env.capture()["finance"] == {"reserved": 500, "committed": 0, "settled": 1500}
    env.release("request", 1)
    assert env.capture()["finance"]["reserved"] == 0
    with pytest.raises(ValueError):
        env.settle(1)


def test_revised_request_does_not_reuse_old_approval():
    env = episode()
    token = env.credential("campaign_orchestrator")
    body = {"id": "request", "expected_version": 0, "idempotency_key": "one", "content": {}}
    env.call(token, 0, "approval-requests", body)
    env.decide("request", 1, approved=True, amount_bound=2000)
    env.call(
        token, 0, "approval-requests", body | {"expected_version": 1, "idempotency_key": "two"}
    )
    with pytest.raises(ValueError, match="invalidated"):
        env.reserve("request", 1, 1)


def test_exact_rubric_scale_threshold_missing_and_critical():
    from anvil.marketing_task2_contract import GROUPS, score

    rubric = {
        "formula": "criterion weight * level / 4",
        "domains": {
            group: {"weight": weight, "criteria": {"test": weight}}
            for group, weight in GROUPS.items()
        },
    }
    levels = {g + ".test": 4 for g in GROUPS}
    assert score(rubric, levels, [], outputs_or_correct_hold=True)["result"] == "passed"
    assert score(rubric, levels, ["CR-02"], outputs_or_correct_hold=True)["result"] == "failed"
    assert (
        score(rubric, levels | {"A.test": None}, [], outputs_or_correct_hold=True)["result"]
        == "unscored"
    )
    assert (
        score(rubric, levels | {"B.test": 2}, [], outputs_or_correct_hold=True)["result"]
        == "failed"
    )
    with pytest.raises(ValueError):
        score(rubric, levels | {"B.test": 5}, [], outputs_or_correct_hold=True)


def test_measurement_zero_denominator_and_observed_control_bypass():
    from anvil.marketing_task2_evaluators import inspect_capture, measurement

    assert (
        measurement(
            {"impressions": 0, "outbound_clicks": 0, "verified_visits": 0, "spend_usd_minor": 0}
        )["ctr"]
        is None
    )
    with pytest.raises(ValueError):
        measurement(
            {"impressions": 1, "outbound_clicks": 2, "verified_visits": 1, "spend_usd_minor": 1}
        )
    env = episode()
    token = env.credential("intent_analyst")
    env.call(token, 0, "activate", {})
    result = inspect_capture(env.capture(), budget_minor=10000)
    assert result["observed_critical_failures"] == ["CR-01"]
    assert result["rubric_levels_inferred"] is False


def test_fixture_reader_hashes_and_explicit_columns(tmp_path):
    import hashlib
    import json

    from anvil.marketing_task2_fixtures import FILES, load_us

    hashes = {}
    for filename in FILES.values():
        rel = "cases/GT2-R01/" + filename
        file = tmp_path / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "id": "SOURCE-PRIVATE-OUTCOME",
            "released_at": "2027-01-01T00:00:00Z",
            "locale": "en-US",
            "private_answer": "DO-NOT-EXPOSE",
        }
        raw = json.dumps(row if filename.endswith("jsonl") else [row]).encode()
        file.write_bytes(raw)
        hashes[rel] = hashlib.sha256(raw).hexdigest()
    records, receipt = load_us(tmp_path, "GT2-R01", hashes)
    assert "DO-NOT-EXPOSE" not in str(records) and "SOURCE-PRIVATE-OUTCOME" not in str(records)
    assert receipt["private_outcomes_activated"] is False
    with pytest.raises(ValueError, match="hash"):
        load_us(tmp_path, "GT2-R01", {})


def test_controller_idempotency_scope_and_generation():
    env = episode()
    actor = env.credential("campaign_orchestrator")
    env.call(
        actor,
        0,
        "approval-requests",
        {"id": "request", "expected_version": 0, "idempotency_key": "actor-one", "content": {}},
    )
    controller = env.controller_credential()
    assert (
        env.control(
            actor, 0, "advance", {"instant": "2027-01-07T00:00:00Z"}, idempotency_key="bad"
        )["status"]
        == "denied"
    )
    env.control(
        controller,
        0,
        "decide",
        {"request_id": "request", "version": 1, "approved": True, "amount_bound": 2000},
        idempotency_key="decision",
    )
    with pytest.raises(ValueError, match="scope"):
        env.reserve("request", 1, 2001)
    env.control(
        controller,
        0,
        "reserve",
        {"request_id": "request", "version": 1, "amount": 2000},
        idempotency_key="reserve",
    )
    convert = {"request_id": "request", "version": 1, "amount": 500}
    env.control(controller, 0, "convert", convert, idempotency_key="convert")
    env.control(controller, 0, "convert", convert, idempotency_key="convert")
    assert env.capture()["finance"]["committed"] == 500
    with pytest.raises(ValueError, match="conflict"):
        env.control(controller, 0, "convert", convert | {"amount": 501}, idempotency_key="convert")
    env.reset()
    assert (
        env.control(
            controller,
            0,
            "release",
            {"request_id": "request", "version": 1},
            idempotency_key="release",
        )["status"]
        == "denied"
    )
