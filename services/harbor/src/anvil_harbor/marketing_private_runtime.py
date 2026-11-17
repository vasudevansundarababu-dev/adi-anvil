"""Explicit private opening trial successor; source only, all admission held.

Reuses the exact legacy Environment and safe lifecycle methods. It does not
monkeypatch factories/gates, rewrite the base context or supply input authority.
Late private binding comes only from the independently qualified host sealer.
"""

import asyncio
import contextlib
import hashlib
import json
import math
import stat
import sys
from pathlib import Path

from harbor.environments.factory import EnvironmentFactory
from harbor.models.trial.config import TrialConfig
from harbor.models.task.verifier_mode import (
    VerifierEnvironmentMode, resolve_task_verifier_mode, resolve_verifier_environment_definition,
)
from harbor.trial.single_step import SingleStepTrial
from harbor.trial.trial import Trial
from harbor.verifier.factory import VerifierFactory

from anvil_harbor.marketing import (
    MarketingEnvironment, MarketingTrial, _ACTIVE_OPENING, _event, _expected_trial,
    _opening_context, _pairs, _read_owned, _remaining, _task_pins, component_gate,
)
from anvil_harbor.marketing_private_sdk import MarketingPrivateVerifier
from anvil_harbor.marketing_private_verifier import (
    CRITERION_WEIGHTS, SCORING_CONTRACT, SCORING_SOURCE_PINS, _exact, _identity, _parse, _pin, _scope,
)


def _program(context, expected_pin):
    _pin(expected_pin)
    raw = _immutable(Path(context["attempt_root"]) / "private-verifier-program.json")
    if hashlib.sha256(raw).hexdigest() != expected_pin:
        raise ValueError("marketing_private_original_program_pin_changed")
    value = _parse(raw)
    _exact(value, {"schema_version", "scope", "source_sha256", "evaluation_profile_sha256",
                   "rubric_id", "rubric_version", "scoring_contract", "scoring_source_pins",
                   "criterion_weights", "qualification_sha256"})
    _scope(value["scope"])
    if (value["schema_version"] != "anvil.marketing-private-verifier-program.v1"
            or value["scope"]["job_id"] != context["job_id"]
            or value["scoring_contract"] != SCORING_CONTRACT
            or value["scoring_source_pins"] != SCORING_SOURCE_PINS
            or value["criterion_weights"] != CRITERION_WEIGHTS
            or any(type(value[k]) is not str or not 1 <= len(value[k]) <= 200
                   for k in ("rubric_id", "rubric_version"))):
        raise ValueError("marketing_private_exact_original_program_required")
    for key in ("source_sha256", "evaluation_profile_sha256", "qualification_sha256"):
        _pin(value[key])
    for weight in value["criterion_weights"].values():
        if type(weight) is not int:
            raise ValueError("marketing_private_original_integer_weights_required")
    return raw, value


def _immutable(path):
    raw = _read_owned(path, 65536)
    if stat.S_IMODE(path.lstat().st_mode) != 0o400:
        raise ValueError("marketing_private_root_only_readonly_program_or_binding_required")
    return raw


def _late_binding(context, program, frame):
    raw = _immutable(Path(context["attempt_root"]) / "private-verifier-binding.json")
    value = _parse(raw)
    _exact(value, {"schema_version", "scoring_contract", "scoring_source_pins", "identity", "scope",
                   "source_sha256", "input_sha256", "input_files", "rubric_id", "rubric_version", "criterion_weights"})
    _identity(value["identity"])
    _scope(value["scope"])
    if (value["schema_version"] != "anvil.marketing-private-sdk-binding.v1"
            or value["identity"]["framework_trial_id"] != str(frame)
            or any(value["identity"][k] != context[k]
                   for k in ("job_id", "request_sha256", "plan_sha256", "operation_nonce"))
            or any(value[k] != program[k] for k in ("scope", "source_sha256", "rubric_id", "rubric_version",
                                                   "scoring_contract", "scoring_source_pins", "criterion_weights"))):
        raise ValueError("marketing_private_late_binding_original_identity_changed")
    _exact(value["input_files"], {"actor-output.json", "private-evidence.json", "evaluation-profile.json"})
    if value["input_files"]["evaluation-profile.json"] != program["evaluation_profile_sha256"]:
        raise ValueError("marketing_private_original_profile_changed")
    _pin(value["input_sha256"])
    for pin in value["input_files"].values():
        _pin(pin)
    for weight in value["criterion_weights"].values():
        if type(weight) is not int:
            raise ValueError("marketing_private_late_integer_weights_required")
    return raw, value


def _configuration(context):
    expected = _expected_trial(context)
    expected["verifier"] = {"import_path": "anvil_harbor.marketing_private_sdk:MarketingPrivateVerifier"}
    return expected


class MarketingPrivateTrial(SingleStepTrial):
    # These fixed methods retain the one-way stop, no replay, no upload and
    # actor/separate-verifier ordering of the reviewed legacy lifecycle source.
    _upload_injected_skills = MarketingTrial._upload_injected_skills
    _stop_agent_environment = MarketingTrial._stop_agent_environment
    _reset_shared_step_verifier_dirs = MarketingTrial._reset_shared_step_verifier_dirs
    _run_shared_verifier = MarketingTrial._run_shared_verifier
    _upload_role_logs = MarketingTrial._upload_role_logs
    _run = MarketingTrial._run
    _recover_outputs = MarketingTrial._recover_outputs

    def __init__(self, config, *, _task, _task_download_result, program_pin):
        component_gate()
        if type(self) is not MarketingPrivateTrial or _task is None or _task.has_steps:
            raise ValueError("marketing_private_exact_single_trial_required")
        self._base_context = _opening_context()
        self._program_pin = _pin(program_pin)
        self._program_raw, self._program = _program(self._base_context, program_pin)
        super().__init__(config, _task=_task, _task_download_result=_task_download_result)
        self._marketing_verifier_stopped = False
        self._private_result_raw = None

    @classmethod
    async def create(cls, config, program_pin):
        component_gate()
        context = _opening_context()
        _program(context, program_pin)
        if (cls is not MarketingPrivateTrial or type(config) is not TrialConfig
                or config.model_dump(mode="json") != TrialConfig.model_validate(_configuration(context)).model_dump(mode="json")):
            raise ValueError("marketing_private_fixed_factory_config_required")
        _task_pins(context)
        task, downloaded = await Trial._load_task(config)
        root = Path(context["attempt_root"]) / "task"
        if (downloaded.path != root or task.task_dir != root or task.has_steps
                or resolve_task_verifier_mode(task.config) != VerifierEnvironmentMode.SEPARATE):
            raise ValueError("marketing_private_local_separate_task_required")
        return cls(config, _task=task, _task_download_result=downloaded, program_pin=program_pin)

    @contextlib.asynccontextmanager
    async def _private_environment(self, definition, plan):
        component_gate()
        if (not definition.bundled_tests or plan.verifier_env_baseline is None
                or self.agent_environment._marketing_stop_state != "acknowledged"):
            raise ValueError("marketing_private_stopped_actor_and_separate_baseline_required")
        if _program(self._base_context, self._program_pin)[0] != self._program_raw:
            raise ValueError("marketing_private_program_changed_during_trial")
        binding_raw, binding = _late_binding(self._base_context, self._program, self.id)
        target = EnvironmentFactory.create_environment_from_config(
            config=self.config.environment.model_copy(update={"extra_docker_compose": []}), stream=False,
            environment_dir=definition.directory, enable_environment_dir_upload=False,
            environment_name=self.task.short_name, session_id=self._separate_verifier_session_id("trial"),
            trial_paths=self.paths, task_env_config=definition.config, logger=self.logger,
            auto_mounts=[], network_policy=plan.verifier_env_baseline, phase_network_policies=[plan.verifier_phase],
        )
        if type(target) is not MarketingEnvironment or target.role != "tests":
            raise ValueError("marketing_private_exact_legacy_environment_required")
        target.context_id = self.id
        # Instance-only augmentation after validating the immutable base. Keep
        # exactly its clock, deadline, token, socket and original file/profile pins.
        target._context = {**target._context, "private_verifier": binding}
        self._validate_separate_verifier_env_policies(target, plan=plan)
        try:
            async with asyncio.timeout(min(self._environment_build_timeout_sec, _remaining(target._context))):
                await target.preflight_projection()
                await target.start(force_build=False)
            yield target
            if _late_binding(self._base_context, self._program, self.id)[0] != binding_raw:
                raise ValueError("marketing_private_late_binding_changed_during_verification")
        finally:
            await target.stop(delete=False)
            if target._marketing_stop_state != "acknowledged":
                raise RuntimeError("marketing_private_verifier_stop_not_acknowledged")
            self._marketing_verifier_stopped = True

    async def _run_separate_verifier(self, *, key, timeout_sec, artifacts_dir, artifacts=None,
                                     step_cfg=None, user, env=None):
        component_gate()
        if (key != "trial" or artifacts_dir != self.paths.artifacts_dir or artifacts or step_cfg is not None
                or env or user not in (None, "10001:10001", 10001)):
            raise ValueError("marketing_private_fixed_verifier_scope_required")
        definition = resolve_verifier_environment_definition(self.task.config, self.task.paths, None)
        if definition is None or not definition.bundled_tests:
            raise ValueError("marketing_private_bundled_definition_required")
        plan = self._network_plan(None, env_config=definition.config)
        async with self._private_environment(definition, plan) as target:
            verifier = VerifierFactory.create_verifier_from_config(
                self.config.verifier, task=self.task, trial_paths=self.paths, environment=target,
                override_env=None, logger=self.logger, verifier_env=None, step_name=None, skip_tests_upload=True,
            )
            if type(verifier) is not MarketingPrivateVerifier:
                raise ValueError("marketing_private_exact_verifier_factory_required")
            remaining = _remaining(target._context)
            if timeout_sec is not None:
                if type(timeout_sec) not in (int, float) or not math.isfinite(timeout_sec) or timeout_sec <= 0:
                    raise ValueError("marketing_private_finite_verifier_budget_required")
                remaining = min(remaining, timeout_sec)
            with target.with_default_user(user):
                async with self._phase_network_policy(target, baseline_policy=plan.verifier_env_baseline,
                                                      phase_policy=plan.verifier_phase):
                    with self._log_context("verification", target, None):
                        result = await self._verify_with_timeout(verifier, remaining)
            self._private_result_raw = verifier.private_result_raw
            return result


async def main(path, private_program_sha256):
    component_gate()
    token = _ACTIVE_OPENING.set(True)
    try:
        context = _opening_context()
        root = Path(context["attempt_root"])
        if Path(path) != root / "trial.json":
            raise ValueError("marketing_private_fixed_trial_path_required")
        raw = _read_owned(root / "trial.json", 65536)
        if (hashlib.sha256(raw).hexdigest() != context["trial_config_sha256"]
                or json.loads(raw, object_pairs_hook=_pairs) != _configuration(context)):
            raise ValueError("marketing_private_original_trial_config_changed")
        trial = await MarketingPrivateTrial.create(TrialConfig.model_validate(_configuration(context)), private_program_sha256)
        await _event("framework_entry", trial.agent_environment)
        await trial.agent_environment.preflight_projection()
        result = await trial.run()
        if (result.id != trial.id or result.exception_info or result.verifier_result is None
                or trial.agent_environment._marketing_stop_state != "acknowledged"
                or not trial._marketing_verifier_stopped or trial._private_result_raw is None):
            raise RuntimeError("marketing_private_framework_result_incomplete")
        manifest = json.loads(_read_owned(trial.paths.artifacts_manifest_path, 1048576, private=False),
                              object_pairs_hook=_pairs)
        if (type(manifest) is not list or not manifest
                or any(type(row) is not dict or row.get("status") not in {"ok", "empty"}
                       or row.get("service") not in {None, "main"}
                       or row.get("source") not in {"/workspace/output.json", "/logs/artifacts"} for row in manifest)
                or not any(row.get("source") == "/workspace/output.json" and row.get("status") == "ok"
                           for row in manifest)):
            raise RuntimeError("marketing_private_actual_artifact_manifest_incomplete")
        # Only a private-result reference leaves this SDK process, no private
        # evaluator facts, rationale or partial denominator presented as score.
        print(json.dumps({"framework_trial_id": str(result.id),
                          "private_result_sha256": hashlib.sha256(trial._private_result_raw).hexdigest(),
                          "model_performance_validated": False, "native_qualification_granted": False}))
    finally:
        _ACTIVE_OPENING.reset(token)


if __name__ == "__main__":
    component_gate()
    if len(sys.argv) != 3:
        raise ValueError("marketing_private_exact_trial_and_program_pin_arguments_required")
    asyncio.run(main(sys.argv[1], sys.argv[2]))
