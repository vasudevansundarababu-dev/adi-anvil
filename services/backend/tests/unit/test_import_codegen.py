import hashlib
import io
import json
import zipfile

import pytest

from anvil.config import ROOT
from anvil.import_codegen import (
    generation_prompt,
    inspect_code,
    notebook,
    notebook_code,
    package,
    score,
    validate_bundle,
)
from anvil.praxis_executable import parse


def fixture_bundle(task):
    cases = task.evaluation_private.fixtures
    generated_cases = []
    for case in cases:
        value = case.model_dump()
        actions = list(value["observed_calls"])
        if case.output is not None:
            index = next(
                (
                    i
                    for i, a in enumerate(actions)
                    if any(a["tool"] in c.prohibited_tools for c in task.constraints)
                ),
                len(actions),
            )
            actions.insert(index, {"tool": "save_result", "arguments": {"output": case.output}})
        assertions = []
        for index, action in enumerate(actions):
            checks = {
                c.id: action["tool"] not in c.prohibited_tools
                for c in task.constraints
                if c.phase in ("runtime", "both")
            }
            if task.domain == "marketing" and action["tool"] == "save_result":
                data = json.loads(task.inputs[0].content)
                alloc = action["arguments"]["output"]["allocation_cents"]
                checks["M-SPEND-LIMIT"] = sum(alloc.values()) <= data["budget_cents"] and all(
                    v * 100 <= data["budget_cents"] * data["max_channel_percent"]
                    for v in alloc.values()
                )
            assertions.append({"action_index": index, "expected_checks": checks})
        value.update(observed_calls=actions, guard_assertions=assertions)
        generated_cases.append(value)
    return {
        "schema_version": "anvil.generated.python.v1",
        "code": (
            ROOT / ("fixtures/executable-import/generated_" + task.domain + ".py")
        ).read_text(),
        "rules": [
            {
                "source_id": rule.id,
                "interpretation": rule.description,
                "check_type": "deterministic_python",
                "evidence": "output.json and observable tools",
                "tests": [f.id for f in cases if rule.id in f.covers],
            }
            for rule in [*task.criteria, *task.constraints]
        ],
        "fixtures": generated_cases,
        "probe_mappings": {
            t.id: t.probe.expected_description for s in task.mcp_servers for t in s.tools if t.probe
        },
        "assumptions": ["Authored mock provider response; software tests only"],
        "unresolved": [],
    }


@pytest.mark.parametrize("path", sorted((ROOT / "contracts/praxis/golden-v3").glob("*.task.json")))
def test_generated_contract_and_notebook_private_projection(path):
    task = parse(path.read_bytes())
    bundle = validate_bundle(task, fixture_bundle(task))
    prompt = generation_prompt(task)
    assert task.evaluation_private.canary not in prompt
    assert "evaluation_private" not in prompt
    assert "expected_reward_bps" in prompt  # Schema field only, not supplied answers.
    book = notebook(bundle, "revision", "source-sha")
    serialized = json.dumps(book)
    assert task.evaluation_private.canary not in serialized
    assert all(f.id not in serialized for f in task.evaluation_private.fixtures)
    assert notebook_code(book, "revision", "source-sha") == bundle.code
    with pytest.raises(ValueError, match="base version"):
        notebook_code(book, "other", "source-sha")
    manifest, archive = package(task, bundle, {}, "revision")
    assert manifest["binding"] == "mcp-tool-agent-v1" and archive[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(archive)) as files:
        assert files.read("evaluation/verifiers/rules.py").decode() == bundle.code
        assert b"expected_reward_bps" not in files.read("instruction.md")
        assert "tests/emit_grade.py" in files.namelist()


@pytest.mark.parametrize(
    "payload",
    [
        "import os\ndef evaluate(a,b,c): return {}\ndef guard(a,b,c,d): return {}",
        "def evaluate(a,b,c): return open('secret').read()\ndef guard(a,b,c,d): return {}",
        "def evaluate(a,b,c): return a.__class__\ndef guard(a,b,c,d): return {}",
        "def evaluate(a,b,c): return getattr(a, 'secret')\ndef guard(a,b,c,d): return {}",
        "x=1\ndef evaluate(a,b,c): return {}\ndef guard(a,b,c,d): return {}",
        "@print('leak')\ndef evaluate(a,b,c): return {}\ndef guard(a,b,c,d): return {}",
    ],
)
def test_generated_host_operations_are_rejected(payload):
    with pytest.raises((ValueError, SyntaxError)):
        inspect_code(payload)


def test_missing_rule_semantics_and_coverage_do_not_pass():
    task = parse((ROOT / "contracts/praxis/golden-v3/01-marketing.task.json").read_bytes())
    value = fixture_bundle(task)
    value["unresolved"] = ["No evidence for required accounting rule"]
    with pytest.raises(ValueError, match="Needs clarification"):
        validate_bundle(task, value)


def test_private_input_values_are_not_sent_to_generator_or_notebook():
    value = json.loads((ROOT / "contracts/praxis/golden-v3/01-marketing.task.json").read_text())
    hidden = '{"expected":"PRIVATE-REFERENCE-NEVER-EXPORT"}'
    value["inputs"].append(
        {
            "id": "PRIVATE-INPUT",
            "path": "reference.json",
            "visibility": "evaluation_private",
            "media_type": "application/json",
            "content": hidden,
            "sha256": hashlib.sha256(hidden.encode()).hexdigest(),
        }
    )
    task = parse(json.dumps(value).encode())
    assert "PRIVATE-REFERENCE-NEVER-EXPORT" not in generation_prompt(task)
    from anvil.import_sandbox import input_values

    assert "reference.json" not in input_values(task)
    assert (
        input_values(task, private=True)["reference.json"]["expected"]
        == "PRIVATE-REFERENCE-NEVER-EXPORT"
    )
    value = fixture_bundle(task)
    value["rules"] = value["rules"][:-1]
    with pytest.raises(ValueError, match="Every source rule"):
        validate_bundle(task, value)


def test_dense_credit_is_capped_and_hard_failure_overrides_accumulated_awards():
    task = parse((ROOT / "contracts/praxis/golden-v3/01-marketing.task.json").read_bytes())
    task.criteria[0].phase = "dense"
    checks = {r.id: False for r in task.criteria} | {r.id: True for r in task.constraints}
    credits = {task.criteria[0].id}
    first = score(task, checks, None, credits)
    second = score(task, checks, None, credits | credits)
    assert first["reward_bps"] == second["reward_bps"] == task.criteria[0].weight_bps
    checks["M-NO-LAUNCH"] = False
    assert score(task, checks, None, credits)["reward_bps"] == 0


def test_run_projection_respects_declared_pass_threshold_without_full_reward():
    from anvil.workspace import metrics

    row = {
        "state": "succeeded",
        "candidate": "reference",
        "result": {"diagnostics": {"reward": 0.9, "pass": True}},
    }
    assert metrics(row, [])["passed"] == 1 and metrics(row, [])["task_failed"] == 0
    row["result"]["diagnostics"]["pass"] = False
    assert metrics(row, [])["passed"] == 0 and metrics(row, [])["task_failed"] == 1


@pytest.mark.parametrize(
    "change", ["metadata", "binding", "cells", "cell_metadata", "source", "source_items"]
)
def test_malformed_notebook_is_an_actionable_validation_error(change):
    task = parse((ROOT / "contracts/praxis/golden-v3/01-marketing.task.json").read_bytes())
    book = notebook(validate_bundle(task, fixture_bundle(task)), "base", "source")
    if change == "metadata":
        book["metadata"] = None
    elif change == "binding":
        book["metadata"]["anvil"] = None
    elif change == "cells":
        book["cells"] = None
    elif change == "cell_metadata":
        book["cells"][1]["metadata"] = None
    elif change == "source":
        book["cells"][1]["source"] = None
    else:
        book["cells"][1]["source"] = [1, 2]
    with pytest.raises(ValueError):
        notebook_code(book, "base", "source")
