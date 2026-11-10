import json

import httpx
import pytest

from anvil import evaluator_http as api
from anvil.policy_rules import Rule, coverage, evaluate, evaluate_zen


@pytest.mark.parametrize("engine", [evaluate, evaluate_zen])
@pytest.mark.parametrize(
    "kind,value,pass_fact,fail_fact",
    [
        ("number_max", 100, 100, 100.01),
        ("number_min", 100, 100, 99.99),
        ("equals", "done", "done", "unfinished"),
        ("allowlist", ["approved.example"], "approved.example", "evil.example"),
    ],
)
def test_real_deterministic_engine_cases(engine, kind, value, pass_fact, fail_fact):
    rule = Rule(kind=kind, field="fact", value=value)
    assert engine(rule, {"fact": pass_fact})["outcome"] == "pass"
    assert engine(rule, {"fact": fail_fact})["outcome"] == "fail"
    assert engine(rule, {})["outcome"] == "unknown"


@pytest.mark.parametrize("value", [True, "100", float("inf"), float("nan"), None])
def test_numeric_evidence_not_coerced(value):
    for engine in (evaluate, evaluate_zen):
        assert (
            engine(Rule(kind="number_max", field="x", value=100), {"x": value})["outcome"]
            == "unknown"
        )


def test_coverage_never_passes_unknown():
    result = coverage(["pass"] * 8 + ["fail", "unknown"])
    assert result["percent"] == pytest.approx(88.888889)
    assert (result["decided"], result["planned"]) == (9, 10)
    assert coverage(["unknown", "error"])["percent"] is None


@pytest.mark.parametrize("value,fact", [(True, 1), (1, True), (1, "1"), ("1", 1)])
def test_zen_preserves_strict_equality_types(value, fact):
    assert (
        evaluate_zen(Rule(kind="equals", field="x", value=value), {"x": fact})["outcome"] == "fail"
    )


def test_numeric_precision_boundaries_fail_closed_across_engines():
    with pytest.raises(ValueError, match="safe range"):
        Rule(kind="number_max", field="x", value=9007199254740993)
    for engine in (evaluate, evaluate_zen):
        assert (
            engine(Rule(kind="number_max", field="x", value=100), {"x": 9007199254740993})[
                "outcome"
            ]
            == "unknown"
        )


def test_required_field_includes_actual_false_and_zero():
    rule = Rule(kind="required", field="x")
    for value in (False, 0, ""):
        assert evaluate_zen(rule, {"x": value})["outcome"] == "pass"


def test_actual_pinned_opa_templates_when_explicitly_provisioned():
    import os

    from anvil.policy_rules import evaluate_opa

    binary, sha256 = (
        os.environ.get("ANVIL_TEST_OPA_BINARY"),
        os.environ.get("ANVIL_TEST_OPA_SHA256"),
    )
    if not binary or not sha256:
        pytest.skip("Actual OPA binary is not explicitly provisioned for this test")
    for kind, value, yes, no in [
        ("number_max", 100, 100, 101),
        ("number_min", 100, 100, 99),
        ("equals", "yes", "yes", "no"),
        ("allowlist", ["approved"], "approved", "forbidden"),
    ]:
        rule = Rule(kind=kind, field="fact", value=value)
        for fact, expected in [(yes, "pass"), (no, "fail")]:
            assert (
                evaluate_opa(rule, {"fact": fact}, binary, expected_sha256=sha256)["outcome"]
                == expected
            )
        assert evaluate_opa(rule, {}, binary, expected_sha256=sha256)["outcome"] == "unknown"


ORIGIN = "https://engine.example"
TASK = "10000000-0000-4000-8000-000000000001"
RULE = "10000000-0000-4000-8000-000000000002"
INFERENCE = "10000000-0000-4000-8000-000000000003"


def arthur(transport):
    return api.arthur_prompt(
        ORIGIN,
        TASK,
        "fictional public input",
        "test-key",
        allowed_origins=frozenset({ORIGIN}),
        transport=transport,
    )


def test_arthur_exact_wire_contract_and_mixed_capability():
    def handler(request):
        assert str(request.url) == ORIGIN + f"/api/v2/tasks/{TASK}/validate_prompt"
        assert request.headers["authorization"] == "Bearer test-key"
        assert json.loads(request.content) == {"prompt": "fictional public input"}
        return httpx.Response(
            200,
            json={
                "inference_id": INFERENCE,
                "rule_results": [
                    {"id": RULE, "rule_type": "KeywordRule", "result": "Fail"},
                    {"id": TASK, "rule_type": "PromptInjectionRule", "result": "Pass"},
                ],
            },
        )

    result = arthur(httpx.MockTransport(handler))
    assert result["results"][0]["deterministic"] is True
    assert result["results"][1]["deterministic"] is False


@pytest.mark.parametrize("status", [301, 302, 401, 403, 429, 500, 503])
def test_no_retry_redirect_or_error_body_disclosure(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, text="SENSITIVE UPSTREAM BODY", headers={"Location": "https://evil.test"}
        )

    with pytest.raises(api.EvaluatorError) as error:
        arthur(httpx.MockTransport(handler))
    assert len(calls) == 1
    assert "SENSITIVE" not in str(error.value)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"inference_id": INFERENCE, "rule_results": []},
        {"inference_id": INFERENCE, "rule_results": [{"result": "Pass"}]},
    ],
)
def test_arthur_not_ready_on_empty_or_malformed(body):
    with pytest.raises(api.EvaluatorError):
        arthur(httpx.MockTransport(lambda request: httpx.Response(200, json=body)))


def test_openlayer_exact_window_is_queued_not_pass():
    def handler(request):
        assert str(request.url) == "https://api.openlayer.com/v1/tests/test1/evaluate"
        assert json.loads(request.content) == {
            "inference_pipeline_id": "pipe1",
            "start_timestamp": 100,
            "end_timestamp": 200,
            "overwrite_results": False,
        }
        return httpx.Response(
            200,
            json={
                "pipelineCount": 1,
                "requestedStartTimestamp": 100,
                "requestedEndTimestamp": 200,
                "tasks": [
                    {
                        "pipelineId": "pipe1",
                        "taskResultId": "task1",
                        "taskResultUrl": "https://evil.test/never-follow",
                    }
                ],
            },
        )

    result = api.openlayer_evaluate(
        "test1", "pipe1", 100, 200, "test-key", transport=httpx.MockTransport(handler)
    )
    assert result["state"] == "queued"
    assert result["outcome"] == "not_evaluated"


@pytest.mark.parametrize("result,outcome", [(True, "pass"), (False, "fail"), (None, "unknown")])
def test_opa_contract(result, outcome):
    def handler(request):
        assert request.url.path == "/v1/data/anvil/allow"
        assert json.loads(request.content) == {"input": {"amount": 100}}
        return httpx.Response(200, json={} if result is None else {"result": result})

    value = api.opa_decision(
        ORIGIN,
        "anvil/allow",
        {"amount": 100},
        "test-key",
        allowed_origins=frozenset({ORIGIN}),
        transport=httpx.MockTransport(handler),
    )
    assert value["outcome"] == outcome


@pytest.mark.parametrize(
    "origin",
    [
        "http://engine.example",
        "https://u:p@engine.example",
        "https://engine.example/",
        "https://engine.example?q=secret",
        "http://169.254.169.254",
        "https://other.example",
    ],
)
def test_endpoint_denied_before_dispatch(origin):
    with pytest.raises(api.EvaluatorError):
        api.endpoint(origin, frozenset({ORIGIN}))


def test_timeout_and_oversize_are_errors_not_model_failures():
    def timeout(request):
        raise httpx.ReadTimeout("sensitive transport detail", request=request)

    with pytest.raises(api.EvaluatorError, match="upstream_transport_or_schema_error"):
        arthur(httpx.MockTransport(timeout))
    with pytest.raises(api.EvaluatorError, match="response_too_large"):
        arthur(
            httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"x" * (api.MAX_BYTES + 1))
            )
        )


def test_duplicate_upstream_json_does_not_turn_failure_into_pass():
    body = (
        '{"inference_id":"' + INFERENCE + '","rule_results":['
        '{"id":"' + RULE + '","rule_type":"KeywordRule","result":"Fail","result":"Pass"}]}'
    )
    with pytest.raises(api.EvaluatorError, match="schema_error"):
        arthur(httpx.MockTransport(lambda request: httpx.Response(200, content=body)))
