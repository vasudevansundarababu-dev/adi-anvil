"""Opt-in actual native/SDK/evaluator path; skipped never means qualified."""

import io
import os

import pytest
from test_benchmark_qualification import signed_native_fixture as native_fixture

from anvil.benchmark_compiler import compile_task, fixture_binding
from anvil.benchmark_conversation import Binding, Limits
from anvil.benchmark_offline_actor import driver
from anvil.benchmark_qualification import native_trial
from anvil.config import ROOT
from anvil.providers import PROVIDERS

signed_native_fixture = native_fixture


@pytest.mark.parametrize("provider", ("openai", "anthropic", "gemini"))
@pytest.mark.parametrize("task_id,maximum", [("FX-001", 24), ("FX-002", 6), ("FX-003", 51)])
def test_real_native_offline_sdk_and_separate_evaluator(
    signed_native_fixture, tmp_path, provider, task_id, maximum
):
    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Exact dedicated Linux native operator required; not native pass evidence")
    raw, parsed, signers, now = signed_native_fixture
    package = tmp_path / "actor.zip"
    compiled = compile_task(
        io.BytesIO(raw), parsed, task_id, fixture_binding(), package, signers=signers, now=now
    )
    task = next(t for t in parsed.parsed.manifest.tasks if t.id == task_id)
    folder = tmp_path / "native-trial"
    folder.mkdir(mode=0o700)
    binding = Binding(
        provider=provider, model_id="fictional-software-only", destination=PROVIDERS[provider][2]
    )
    result = native_trial(
        package,
        compiled,
        task,
        ROOT / "fixtures/benchmark-bundle/fictional-points-v1/eval_pack" / task_id,
        folder,
        mode="offline_conversation",
        actor_driver=driver(binding, Limits(), dispatch_check=lambda: None),
    )
    assert result["points"] == maximum and len(result["criteria"]) == maximum
    assert sum(result["criteria"].values()) == maximum
    assert result["candidate_stopped_before_evaluation"]
    assert result["candidate_container"] != result["evaluator_container"]
    assert result["conversation"]["measured_model_performance"] is False
    assert result["provider_calls"] > 0 and result["duration_ms"] >= 0
