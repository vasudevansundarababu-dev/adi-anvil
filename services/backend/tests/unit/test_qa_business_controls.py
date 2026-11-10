import json

import pytest

from anvil import benchmark_business_fixture as fixture
from anvil import benchmark_project_import as imports
from anvil.praxis_contract import grade


def test_zero_control_is_actually_graded_zero_under_each_original_rubric(monkeypatch):
    monkeypatch.setenv("ANVIL_QA_ACCEPTANCE_CONTROLS_ENABLED", "true")
    group, _ = imports.parse(fixture.bundle())
    for task in group["tasks"]:
        source = imports.parse_task(json.dumps(task["source"]))
        for environment in group["environments"]:
            simulator = fixture.BusinessEnvironment(environment)
            output = fixture.candidate("fictional-zero-control-v1", task["actor"], simulator, attack=False)
            facts = {"status": output["status"], "citation_count": len(output["citations"]),
                     "policy_ok": not any(e.get("prohibited") for e in simulator.events)}
            result = grade(source, facts)
            assert all(not c["passed"] for c in result["criteria"].values())
            assert any(e.get("prohibited") for e in simulator.events)
            assert not facts["policy_ok"]  # Containment cannot turn a prohibited attempt into Pass.


def test_failure_control_raises_before_output_or_grade(monkeypatch):
    monkeypatch.setenv("ANVIL_QA_ACCEPTANCE_CONTROLS_ENABLED", "true")
    group, _ = imports.parse(fixture.bundle())
    simulator = fixture.BusinessEnvironment(group["environments"][0])
    with pytest.raises(RuntimeError, match="Intentional QA"):
        fixture.candidate("fictional-error-control-v1", group["tasks"][0]["actor"], simulator, attack=False)
    assert not simulator.events


def test_qa_controls_refuse_default_runtime(monkeypatch):
    monkeypatch.delenv("ANVIL_QA_ACCEPTANCE_CONTROLS_ENABLED", raising=False)
    group, _ = imports.parse(fixture.bundle())
    simulator = fixture.BusinessEnvironment(group["environments"][0])
    with pytest.raises(ValueError, match="disabled"):
        fixture.candidate("fictional-zero-control-v1", group["tasks"][0]["actor"], simulator, attack=False)
