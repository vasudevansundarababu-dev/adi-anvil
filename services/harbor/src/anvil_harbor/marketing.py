"""Closed Harbor0.25 components over a fixed root-owned host control protocol.

No stock Docker lifecycle/probes, caller commands, SDK provider clients or
automatic mount chmod. Host handlers/producer authority are still missing.
This source has not been imported or exercised in a native runtime.
"""

import asyncio
import contextlib
import hashlib
import json
import math
import os
import re
import stat
import sys
from contextvars import ContextVar
from importlib.metadata import version
from pathlib import Path
from time import monotonic
from uuid import UUID

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.environments.capabilities import EnvironmentCapabilities
from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import NetworkMode
from harbor.models.task.verifier_mode import (
    VerifierEnvironmentMode,
    resolve_task_verifier_mode,
    resolve_verifier_environment_definition,
)
from harbor.models.trial.config import TrialConfig
from harbor.models.verifier.result import VerifierResult
from harbor.trial.single_step import SingleStepTrial
from harbor.trial.trial import Trial
from harbor.verifier.base import BaseVerifier
from harbor.verifier.factory import VerifierFactory

PREFIX = Path("/var/lib/anvil-qa-v1/runtime-functional/marketing-attempts")
EVENTS = frozenset({"framework_entry", "preflight", "before_start", "start", "stop", "actor", "collect", "artifact_stat", "copy_output", "logs"})
_ACTIVE_OPENING = ContextVar("marketing_explicit_opening_program", default=False)


def component_gate():
    """Unconditional: environment/caller values cannot activate this source."""
    raise RuntimeError("marketing_Harbor_components_and_host_handlers_not_admitted")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("marketing_component_duplicate_field")
        result[key] = value
    return result


def _read_owned(path, cap, *, private=True):
    if path.resolve() != path:
        raise ValueError("marketing_component_canonical_file_required")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_nlink != 1
                or before.st_mode & (0o077 if private else 0o022) or before.st_size > cap):
            raise ValueError("marketing_component_owned_file_required")
        raw = stream.read(cap + 1)
        after = os.fstat(stream.fileno())
    if (not raw or len(raw) > cap or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
        raise ValueError("marketing_component_owned_file_changed")
    return raw


def _remaining(context):
    delta = context["deadline_monotonic"] - monotonic()
    if not math.isfinite(delta) or not 0 < delta <= context["lifecycle_seconds"]:
        raise TimeoutError("marketing_component_aggregate_deadline")
    return delta


def _context():
    """Legacy reader stays strict; never infer a program version from a file."""
    return _context_version(opening=False)


def _opening_context():
    """Explicit source-only opening reader; runtime entry gates stay closed."""
    return _context_version(opening=True)


def _component_context():
    # Selected only by the fixed module entry for this async operation. Neither
    # a context-file version nor an environment variable selects this mode.
    opening = _ACTIVE_OPENING.get()
    if type(opening) is not bool:
        raise ValueError("marketing_component_explicit_program_selection_required")
    return _opening_context() if opening else _context()


def _opening_program(value):
    """Validate the fixed ASCII/integer schedule without backend imports."""
    program = value.get("operator_program")
    fields = {"schema_version", "program_id", "role_ids", "opening_index", "review_indices",
              "observation_indices", "weekly_cycle_backedges", "workflow_graph_sha256"}
    if type(program) is not dict or set(program) != fields:
        raise ValueError("marketing_component_exact_opening_program_required")
    roles = program["role_ids"]
    if (type(roles) is not list or len(roles) != 5 or any(type(role) is not str for role in roles)
            or set(roles) != {"orchestrator", "intent", "performance", "brief", "policy"}
            or program["schema_version"] != "anvil.marketing-operator-schedule.v2"
            or program["program_id"] != "marketing-opening0-and-twelve-reviews-v1"
            or type(program["opening_index"]) is not int or program["opening_index"] != 0
            or type(program["weekly_cycle_backedges"]) is not int or program["weekly_cycle_backedges"] != 12):
        raise ValueError("marketing_component_original_opening_schedule_required")
    for key, expected in (("review_indices", list(range(1, 13))), ("observation_indices", list(range(13)))):
        if (type(program[key]) is not list or any(type(index) is not int for index in program[key])
                or program[key] != expected):
            raise ValueError("marketing_component_original_opening_windows_required")
    if (type(program["workflow_graph_sha256"]) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", program["workflow_graph_sha256"])
            or type(value.get("operator_program_sha256")) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", value["operator_program_sha256"])):
        raise ValueError("marketing_component_original_opening_program_pin_required")
    # Every accepted key/string is fixed ASCII or lowercase hex, and all numbers
    # are small integers. This serialization is JCS-equivalent for this schema.
    raw = json.dumps(program, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if hashlib.sha256(raw).hexdigest() != value["operator_program_sha256"]:
        raise ValueError("marketing_component_opening_program_pin_changed")


def _context_version(*, opening):
    if type(opening) is not bool:
        raise ValueError("marketing_component_explicit_context_version_required")
    if (sys.version_info[:2] != (3, 12) or sys.platform != "linux" or os.uname().machine != "x86_64"
            or os.geteuid() != 0 or os.uname().nodename != "anvil-qa-v1" or version("harbor") != "0.25.0"):
        raise ValueError("marketing_exact_QA_root_Harbor025_required")
    root = Path(os.environ["ANVIL_MARKETING_ATTEMPT_ROOT"])
    if (root.parent != PREFIX or root.resolve() != root or not re.fullmatch(r"anvil-marketing-[a-f0-9]{20}", root.name)):
        raise ValueError("marketing_component_fixed_attempt_required")
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError("marketing_component_private_attempt_required")
    raw = _read_owned(root / "component-context.json", 65536)
    if hashlib.sha256(raw).hexdigest() != os.environ["ANVIL_MARKETING_CONTEXT_SHA256"]:
        raise ValueError("marketing_component_context_pin_changed")
    value = json.loads(raw, object_pairs_hook=_pairs)
    fields = {"schema_version", "purpose", "request_sha256", "plan_sha256", "job_id", "operation_nonce",
              "trial_name", "attempt_root", "image_digest", "expected_files", "expected_effective_services",
              "trial_config_sha256", "deadline_monotonic", "lifecycle_seconds", "output_bytes",
              "control_socket", "control_token", "boot_id"}
    if opening:
        fields |= {"operator_program", "operator_program_sha256"}
    if (type(value) is not dict or set(value) != fields
            or value["schema_version"] != ("anvil.marketing-component-context.v2" if opening
                                           else "anvil.marketing-component-context.v1")
            or value["purpose"] != "marketing_campaign_graph_v1"
            or value["attempt_root"] != str(root) or value["trial_name"] != root.name
            or type(value["lifecycle_seconds"]) is not int or not 1 <= value["lifecycle_seconds"] <= 600
            or type(value["output_bytes"]) is not int or not 1 <= value["output_bytes"] <= 1048576
            or type(value["deadline_monotonic"]) not in (int, float)
            or not math.isfinite(value["deadline_monotonic"])):
        raise ValueError("marketing_exact_component_context_required")
    if opening:
        _opening_program(value)
    for key in ("request_sha256", "plan_sha256", "operation_nonce", "trial_config_sha256", "control_token"):
        if type(value[key]) is not str or not re.fullmatch(r"[a-f0-9]{64}", value[key]):
            raise ValueError("marketing_component_fixed_pin_required")
    files = {"environment/actor/context.json", "environment/actor/binding.json", "environment/docker-compose.yaml",
             "tests/docker-compose.yaml", "instruction.md", "tests/test.sh", "task.toml"}
    if (type(value["expected_files"]) is not dict or set(value["expected_files"]) != files
            or type(value["expected_effective_services"]) is not dict
            or set(value["expected_effective_services"]) != {"environment", "tests"}
            or any(type(pin) is not str or not re.fullmatch(r"[a-f0-9]{64}", pin)
                   for pin in [*value["expected_files"].values(), *value["expected_effective_services"].values()])
            or type(value["image_digest"]) is not str
            or not re.fullmatch(r"us-west1-docker\.pkg\.dev/adi-anvil-mvp-2026/[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)+@sha256:[a-f0-9]{64}", value["image_digest"])):
        raise ValueError("marketing_component_exact_file_image_profile_pins_required")
    if str(UUID(value["job_id"])) != value["job_id"]:
        raise ValueError("marketing_component_job_UUID_required")
    if (type(value["control_socket"]) is not str
            or value["control_socket"] != "/run/anvil-marketing/" + value["operation_nonce"][:20] + "/control.sock"):
        raise ValueError("marketing_component_fixed_short_socket_required")
    socket_path = Path(value["control_socket"])
    if socket_path.resolve() != socket_path:
        raise ValueError("marketing_component_socket_custody_required")
    parent, socket_info = socket_path.parent.stat(), socket_path.lstat()
    if (parent.st_uid != 0 or parent.st_mode & 0o077 or not stat.S_ISDIR(parent.st_mode)
            or socket_info.st_uid != 0 or socket_info.st_mode & 0o077 or not stat.S_ISSOCK(socket_info.st_mode)):
        raise ValueError("marketing_component_socket_custody_required")
    with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as stream:
        boot = stream.read(64).strip()
    if value["boot_id"] != boot or str(UUID(boot)) != boot:
        raise ValueError("marketing_component_same_boot_clock_required")
    _remaining(value)
    return value


async def _event(event, environment):
    component_gate()
    if event not in EVENTS or type(environment) is not MarketingEnvironment:
        raise ValueError("marketing_fixed_component_event_required")
    context = environment._context
    frame = str(environment.context_id)
    if str(UUID(frame)) != frame:
        raise ValueError("marketing_actual_framework_UUID_required")
    payload = {"schema_version": "anvil.marketing-component-event.v1", "event": event,
               "job_id": context["job_id"],
               "request_sha256": context["request_sha256"], "plan_sha256": context["plan_sha256"],
               "operation_nonce": context["operation_nonce"], "framework_trial_id": frame,
               "session_id": environment.session_id, "role": environment.role}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > 4096:
        raise ValueError("marketing_component_event_capacity")

    async def exchange():
        reader, writer = await asyncio.open_unix_connection(context["control_socket"], limit=8192)
        try:
            header = ("POST /marketing/component/" + event + " HTTP/1.1\r\nHost: localhost\r\n"
                      "Authorization: Bearer " + context["control_token"] + "\r\n"
                      "Content-Type: application/json\r\nConnection: close\r\nContent-Length: " + str(len(raw)) + "\r\n\r\n").encode("ascii")
            writer.write(header + raw)
            await writer.drain()
            header = await reader.readuntil(b"\r\n\r\n")
            if len(header) > 8192:
                raise ValueError("marketing_component_reply_header_capacity")
            lines = header.split(b"\r\n")
            if lines[0] != b"HTTP/1.1 200 OK":
                raise RuntimeError("marketing_component_event_denied")
            headers = {}
            for line in lines[1:-2]:
                key, val = line.split(b":", 1)
                key = key.lower()
                if key in headers:
                    raise ValueError("marketing_component_duplicate_HTTP_header")
                headers[key] = val.strip()
            if b"transfer-encoding" in headers or not re.fullmatch(rb"[0-9]{1,5}", headers.get(b"content-length", b"")):
                raise ValueError("marketing_component_fixed_HTTP_framing_required")
            size = int(headers[b"content-length"])
            if not 0 < size <= 16384:
                raise ValueError("marketing_component_reply_capacity")
            data = await reader.readexactly(size)
            return json.loads(data, object_pairs_hook=_pairs)
        finally:
            writer.close()  # No unbounded wait_closed or implicit retry.

    try:
        reply = await asyncio.wait_for(exchange(), timeout=_remaining(context))
        _remaining(context)
        extras = {"diagnostic_reward", "collection_sha256", "model_performance_validated"} if event == "collect" else {"artifact_sha256"} if event == "copy_output" else {"artifact_kind"} if event == "artifact_stat" else {"stopped", "stop_receipt_sha256"} if event == "stop" else set()
        if (type(reply) is not dict or set(reply) != set(payload) | {"status"} | extras
                or any(reply[key] != value for key, value in payload.items()) or reply["status"] != "recorded"):
            raise ValueError("marketing_component_bound_reply_required")
        if event == "collect":
            if (type(reply["diagnostic_reward"]) not in (int, float) or reply["diagnostic_reward"] not in (0, 1)
                    or reply["model_performance_validated"] is not False
                    or not re.fullmatch(r"[a-f0-9]{64}", reply["collection_sha256"])):
                raise ValueError("marketing_component_diagnostic_custody_reply_required")
        if event == "copy_output" and not re.fullmatch(r"[a-f0-9]{64}", reply["artifact_sha256"]):
            raise ValueError("marketing_component_artifact_pin_required")
        if event == "artifact_stat" and reply["artifact_kind"] != "file":
            raise ValueError("marketing_component_actual_file_kind_required")
        if event == "stop" and (reply["stopped"] is not True or not re.fullmatch(r"[a-f0-9]{64}", reply["stop_receipt_sha256"])):
            raise ValueError("marketing_actual_stop_acknowledgment_required")
        return reply
    except Exception:
        raise RuntimeError("marketing_component_outcome_unknown_no_retry") from None


class MarketingEnvironment(BaseEnvironment):
    def __init__(self, *args, environment_dir, session_id, trial_paths, task_env_config, auto_mounts=None, **kwargs):
        component_gate()
        self._context = _component_context()
        self._marketing_stop_state = "not_requested"
        self.role = Path(environment_dir).name
        context = self._context
        if (args or self.role not in {"environment", "tests"}
                or session_id != context["trial_name"] + ("__env" if self.role == "environment" else "__verifier__trial")
                or Path(environment_dir) != Path(context["attempt_root"]) / "task" / self.role
                or trial_paths.trial_dir != Path(context["attempt_root"]) / "trials" / context["trial_name"]):
            raise ValueError("marketing_exact_component_role_paths_required")
        if (any(kwargs.get(key) for key in ("stream", "persistent_env", "mounts", "extra_docker_compose", "auto_mounting"))
                or any(kwargs.get(key) is not None for key in ("override_cpus", "override_memory_mb", "override_storage_mb", "override_gpus", "override_tpu"))
                or task_env_config.env or task_env_config.healthcheck is not None):
            raise ValueError("marketing_component_runtime_extensions_denied")
        kwargs["auto_mounting"] = False
        kwargs["enable_environment_dir_upload"] = False
        kwargs["mounts"] = []
        # Do not inherit SDK automatic mounts or chmod_dir()/artifact-chain777.
        super().__init__(environment_dir=environment_dir, session_id=session_id, trial_paths=trial_paths,
                         task_env_config=task_env_config, auto_mounts=[], **kwargs)
        if (self.auto_mounting is not False or self.network_policy.network_mode != NetworkMode.NO_NETWORK
                or self.network_policy.allowed_hosts
                or any(policy.network_mode != NetworkMode.NO_NETWORK or policy.allowed_hosts
                       for policy in self._phase_network_policies)):
            raise ValueError("marketing_static_no_network_manual_mounts_required")
        self._host_mounts = self._declared["volumes"]
        self._mounts = self._host_mounts

    @staticmethod
    def type():
        return "anvil-marketing-native-v1"

    @property
    def capabilities(self):
        return EnvironmentCapabilities(disable_internet=True, mounted=True, docker_compose=True)

    def _validate_definition(self):
        component_gate()
        context = self._context
        if self.task_env_config.docker_image != context["image_digest"] or self.task_env_config.network_mode != NetworkMode.NO_NETWORK:
            raise ValueError("marketing_fixed_role_image_network_required")
        path = self.environment_dir / "docker-compose.yaml"
        raw = _read_owned(path, 1048576, private=False)
        if hashlib.sha256(raw).hexdigest() != context["expected_files"][self.role + "/docker-compose.yaml"]:
            raise ValueError("marketing_role_declaration_changed")
        doc = json.loads(raw, object_pairs_hook=_pairs)
        if set(doc) != {"services"} or set(doc["services"]) != {"main"}:
            raise ValueError("marketing_single_declared_service_required")
        self._declared = doc["services"]["main"]
        if self._declared["image"] != context["image_digest"]:
            raise ValueError("marketing_role_image_changed")

    async def preflight_projection(self):
        component_gate()
        return await _event("preflight", self)

    async def start(self, force_build):
        component_gate()
        if force_build:
            raise ValueError("marketing_build_forbidden")
        await _event("before_start", self)
        await _event("start", self)

    async def stop(self, delete):
        component_gate()
        if delete:
            raise ValueError("marketing_delete_forbidden")
        if self._marketing_stop_state == "acknowledged":
            return
        if self._marketing_stop_state != "not_requested":
            raise RuntimeError("marketing_stop_unknown_independent_reconciliation_required")
        self._marketing_stop_state = "unknown"  # Set BEFORE dispatch; no replay after cancellation/error.
        reply = await _event("stop", self)
        self._marketing_stop_receipt = reply["stop_receipt_sha256"]
        self._marketing_stop_state = "acknowledged"

    async def prepare_logs_for_host(self):
        component_gate()
        await _event("logs", self)  # No SDK recursive log chown.

    async def upload_file(self, source_path, target_path):
        raise ValueError("marketing_component_upload_forbidden")

    async def upload_dir(self, source_dir, target_dir):
        raise ValueError("marketing_component_upload_forbidden")

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        raise ValueError("marketing_component_arbitrary_exec_forbidden")

    async def reset_dirs(self, **kwargs):
        raise ValueError("marketing_component_directory_reset_forbidden")

    async def empty_dirs(self, dirs, *, chmod=True):
        raise ValueError("marketing_component_directory_clear_forbidden")

    async def ensure_dirs(self, dirs, *, chmod=True):
        raise ValueError("marketing_component_arbitrary_directory_create_forbidden")

    async def is_dir(self, path, user=None):
        component_gate()
        if self.role != "environment" or path != "/workspace/output.json" or user not in (None, "root", "10001:10001", 10001):
            raise ValueError("marketing_fixed_output_stat_only")
        await _event("artifact_stat", self)
        return False  # Exact host-attested output file, not a shell path probe.

    async def download_dir(self, source_dir, target_dir):
        raise ValueError("marketing_component_unmounted_directory_copy_forbidden")

    async def download_file(self, source_path, target_path):
        component_gate()
        target = Path(target_path)
        if (self.role != "environment" or source_path != "/workspace/output.json"
                or target != self.trial_paths.artifacts_dir / "agent-output.json"
                or target.resolve() != target or target.exists() or target.is_symlink()):
            raise ValueError("marketing_fixed_fresh_artifact_target_required")
        reply = await _event("copy_output", self)
        raw = _read_owned(target, self._context["output_bytes"], private=False)
        if hashlib.sha256(raw).hexdigest() != reply["artifact_sha256"]:
            raise ValueError("marketing_actual_copied_artifact_changed")


class MarketingAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        component_gate()
        super().__init__(*args, **kwargs)

    @staticmethod
    def name():
        return "anvil-marketing-fixed-host-v1"

    def version(self):
        return "1.0.0"

    async def setup(self, environment):
        component_gate()
        if type(environment) is not MarketingEnvironment or environment.role != "environment":
            raise ValueError("marketing_exact_actor_component_required")

    async def run(self, instruction, environment, context):
        component_gate()
        if type(environment) is not MarketingEnvironment or environment.role != "environment":
            raise ValueError("marketing_exact_actor_component_required")
        await _event("actor", environment)  # Fixed host graph; no supplied callback/model.


class MarketingVerifier(BaseVerifier):
    def __init__(self, *args, **kwargs):
        component_gate()
        super().__init__(*args, **kwargs)

    async def verify(self):
        component_gate()
        if type(self.environment) is not MarketingEnvironment or self.environment.role != "tests":
            raise ValueError("marketing_exact_verifier_component_required")
        reply = await _event("collect", self.environment)
        return VerifierResult(rewards={"collection_custody": float(reply["diagnostic_reward"])})


def _expected_trial(context):
    root = Path(context["attempt_root"])
    return {"task": {"path": str(root / "task")}, "trial_name": context["trial_name"],
            "job_id": context["job_id"], "trials_dir": str(root / "trials"),
            "agent": {"import_path": "anvil_harbor.marketing:MarketingAgent"},
            "environment": {"import_path": "anvil_harbor.marketing:MarketingEnvironment", "delete": False,
                            "kwargs": {"auto_mounting": False}},
            "verifier": {"import_path": "anvil_harbor.marketing:MarketingVerifier"}}


def _task_pins(context):
    root = Path(context["attempt_root"])
    for relative, pin in context["expected_files"].items():
        if hashlib.sha256(_read_owned(root / "task" / relative, 1048576, private=False)).hexdigest() != pin:
            raise ValueError("marketing_task_snapshot_changed_before_Trial")


class MarketingTrial(SingleStepTrial):
    """One framework trial for the full graph, with sealed separate verification.

    Stock Trial.create returns SingleStepTrial directly, so this factory must
    explicitly instantiate this fixed subclass; no caller-selected trial factory.
    """

    def __init__(self, config, *, _task=None, _task_download_result):
        component_gate()
        if type(self) is not MarketingTrial or _task is None or _task.has_steps:
            raise ValueError("marketing_single_framework_trial_required")
        super().__init__(config, _task=_task, _task_download_result=_task_download_result)
        self._marketing_verifier_stopped = False

    @classmethod
    async def create(cls, config):
        component_gate()
        context = _component_context()
        if (cls is not MarketingTrial or type(config) is not TrialConfig
                or config.model_dump(mode="json") != TrialConfig.model_validate(_expected_trial(context)).model_dump(mode="json")):
            raise ValueError("marketing_fixed_trial_factory_config_required")
        _task_pins(context)
        # Exact local task path only. The pinned loader takes LocalTaskId and
        # produces its ordinary local TaskDownloadResult, not remote download.
        task, downloaded = await Trial._load_task(config)
        root = Path(context["attempt_root"]) / "task"
        if (downloaded.path != root or task.task_dir != root or task.has_steps
                or resolve_task_verifier_mode(task.config) != VerifierEnvironmentMode.SEPARATE):
            raise ValueError("marketing_local_single_separate_task_required")
        return cls(config, _task=task, _task_download_result=downloaded)

    async def _upload_injected_skills(self):
        component_gate()
        if self._injected_skills:
            raise ValueError("marketing_skill_upload_forbidden")

    async def _stop_agent_environment(self):
        component_gate()
        # No stock shield/swallow/mark-stopped-on-error. Finalization may call
        # again, but the component refuses a second dispatch after unknown stop.
        await self.agent_environment.stop(delete=False)
        if self.agent_environment._marketing_stop_state != "acknowledged":
            raise RuntimeError("marketing_actor_stop_not_acknowledged")
        self._is_agent_environment_stopped = True

    @contextlib.asynccontextmanager
    async def _separate_verifier_env(self, definition, *, key, plan):
        component_gate()
        if key != "trial" or not definition.bundled_tests or plan.verifier_env_baseline is None:
            raise ValueError("marketing_fixed_verifier_lifecycle_required")
        target = EnvironmentFactory.create_environment_from_config(
            config=self.config.environment.model_copy(update={"extra_docker_compose": []}), stream=False,
            environment_dir=definition.directory, enable_environment_dir_upload=False,
            environment_name=self.task.short_name, session_id=self._separate_verifier_session_id(key),
            trial_paths=self.paths, task_env_config=definition.config, logger=self.logger,
            auto_mounts=[], network_policy=plan.verifier_env_baseline, phase_network_policies=[plan.verifier_phase],
        )
        if type(target) is not MarketingEnvironment or target.role != "tests":
            raise ValueError("marketing_exact_verifier_lifecycle_component_required")
        target.context_id = self._id
        self._validate_separate_verifier_env_policies(target, plan=plan)
        try:
            async with asyncio.timeout(min(self._environment_build_timeout_sec, _remaining(target._context))):
                await target.start(force_build=False)
            yield target
        finally:
            # Propagate cancellation/unknown stop; never let a successful verify
            # escape this context before its identity-bound stop acknowledgment.
            await target.stop(delete=False)
            if target._marketing_stop_state != "acknowledged":
                raise RuntimeError("marketing_verifier_stop_not_acknowledged")
            self._marketing_verifier_stopped = True

    async def _reset_shared_step_verifier_dirs(self):
        raise ValueError("marketing_shared_or_step_reset_forbidden")

    async def _run_shared_verifier(self, *, timeout_sec, user, **kwargs):
        raise ValueError("marketing_shared_verification_forbidden")

    async def _upload_role_logs(self, *, source_dir, target_dir):
        component_gate()
        if (self.user_agent is not None or source_dir != self.paths.agent_dir
                or str(target_dir) != "/logs/agent"
                or not self.agent_environment.is_path_mounted(target_dir, source_dir)):
            raise ValueError("marketing_exact_already_mounted_actor_logs_required")
        # The exact bound host directory is already present; do not copy/clear it.

    async def _run(self):
        component_gate()
        if resolve_task_verifier_mode(self.task.config) != VerifierEnvironmentMode.SEPARATE:
            raise ValueError("marketing_separate_verification_required")
        await self._run_agent()
        if self.result.exception_info is not None:
            raise RuntimeError("marketing_actor_outcome_unknown_no_continuation")
        await self._upload_agent_logs()
        # Host stop is one-way/identity-bound; parent must reject or reconcile any
        # ambiguous stop. Collector serves retained bounded capture, never replay.
        await self._stop_agent_environment()
        await self._collect_artifacts(stop_main_before_sidecars=False)
        await self._run_verifier()

    async def _recover_outputs(self):
        component_gate()
        # No stock re-collection/copy/replay after an ambiguous graph operation.
        raise RuntimeError("marketing_independent_readonly_recovery_required_no_replay")

    async def _run_separate_verifier(
        self, *, key, timeout_sec, artifacts_dir, artifacts=None, step_cfg=None, user, env=None
    ):
        component_gate()
        if (key != "trial" or artifacts_dir != self.paths.artifacts_dir or artifacts
                or step_cfg is not None or env or user not in (None, "10001:10001", 10001)):
            raise ValueError("marketing_fixed_sealed_verifier_scope_required")
        definition = resolve_verifier_environment_definition(self.task.config, self.task.paths, None)
        if definition is None or not definition.bundled_tests:
            raise ValueError("marketing_owned_bundled_verifier_definition_required")
        plan = self._network_plan(None, env_config=definition.config)
        if plan.verifier_env_baseline is None:
            raise ValueError("marketing_separate_verifier_baseline_required")
        # The role already mounts the bounded immutable /sealed projection.
        # Deliberately no empty_dirs, ensure_dirs, upload_artifacts or tar copy.
        async with self._separate_verifier_env(definition, key="trial", plan=plan) as target:
            if type(target) is not MarketingEnvironment or target.role != "tests":
                raise ValueError("marketing_exact_sealed_verifier_component_required")
            verifier = VerifierFactory.create_verifier_from_config(
                self.config.verifier, task=self.task, trial_paths=self.paths, environment=target,
                override_env=None, logger=self.logger, verifier_env=None, step_name=None, skip_tests_upload=True,
            )
            if type(verifier) is not MarketingVerifier:
                raise ValueError("marketing_exact_collection_verifier_required")
            remaining = _remaining(target._context)
            if timeout_sec is not None:
                if type(timeout_sec) not in (int, float) or not math.isfinite(timeout_sec) or timeout_sec <= 0:
                    raise ValueError("marketing_bounded_verifier_timeout_required")
                remaining = min(remaining, timeout_sec)
            with target.with_default_user(user):
                async with self._phase_network_policy(target, baseline_policy=plan.verifier_env_baseline,
                                                      phase_policy=plan.verifier_phase):
                    with self._log_context("verification", target, None):
                        return await self._verify_with_timeout(verifier, remaining)


async def _run(path):
    component_gate()
    context = _component_context()
    root = Path(context["attempt_root"])
    if Path(path) != root / "trial.json":
        raise ValueError("marketing_fixed_trial_config_required")
    raw = _read_owned(root / "trial.json", 65536)
    if hashlib.sha256(raw).hexdigest() != context["trial_config_sha256"]:
        raise ValueError("marketing_trial_config_changed")
    expected = _expected_trial(context)
    if (json.dumps(json.loads(raw, object_pairs_hook=_pairs), sort_keys=True, separators=(",", ":"), allow_nan=False)
            != json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False)):
        raise ValueError("marketing_exact_trial_components_required")
    _task_pins(context)
    config = TrialConfig.model_validate(expected)
    trial = await MarketingTrial.create(config)
    await _event("framework_entry", trial.agent_environment)
    await trial.agent_environment.preflight_projection()
    definition = resolve_verifier_environment_definition(trial.task.config, trial.task.paths, None)
    if definition is None:
        raise ValueError("marketing_actual_separate_verifier_definition_required")
    plan = trial._network_plan(None, env_config=definition.config)
    if plan.verifier_env_baseline is None:
        raise ValueError("marketing_actual_verifier_network_baseline_required")
    verifier = EnvironmentFactory.create_environment_from_config(
        config=config.environment.model_copy(update={"extra_docker_compose": []}), stream=False,
        environment_dir=definition.directory, enable_environment_dir_upload=False,
        environment_name=trial.task.short_name, session_id=trial._separate_verifier_session_id("trial"),
        trial_paths=trial.paths, task_env_config=definition.config, logger=trial.logger,
        auto_mounts=[], network_policy=plan.verifier_env_baseline, phase_network_policies=[plan.verifier_phase],
    )
    if type(verifier) is not MarketingEnvironment or verifier.role != "tests":
        raise ValueError("marketing_exact_paired_components_required")
    verifier.context_id = trial.id
    trial._validate_separate_verifier_env_policies(verifier, plan=plan)
    await verifier.preflight_projection()
    result = await trial.run()
    if (result.id != trial.id or result.exception_info or result.verifier_result is None
            or trial.agent_environment._marketing_stop_state != "acknowledged"
            or not trial._marketing_verifier_stopped):
        raise RuntimeError("marketing_framework_result_incomplete")
    manifest = json.loads(_read_owned(trial.paths.artifacts_manifest_path, 1048576, private=False), object_pairs_hook=_pairs)
    if (type(manifest) is not list or not manifest
            or any(type(row) is not dict or row.get("status") not in {"ok", "empty"}
                   or row.get("service") not in {None, "main"} or row.get("source") not in {"/workspace/output.json", "/logs/artifacts"}
                   for row in manifest)
            or not any(row.get("source") == "/workspace/output.json" and row.get("status") == "ok" for row in manifest)):
        raise RuntimeError("marketing_actual_artifact_manifest_incomplete")
    print(json.dumps({"framework_trial_id": str(result.id), "diagnostic_rewards": result.verifier_result.rewards,
                      "model_performance_validated": False, "native_qualification_granted": False}))


async def _run_mode(path, *, opening):
    component_gate()
    if type(opening) is not bool:
        raise ValueError("marketing_component_explicit_program_selection_required")
    token = _ACTIVE_OPENING.set(opening)
    try:
        return await _run(path)
    finally:
        _ACTIVE_OPENING.reset(token)


async def main(path):
    component_gate()
    return await _run_mode(path, opening=False)


async def opening_main(path):
    component_gate()
    return await _run_mode(path, opening=True)


if __name__ == "__main__":
    component_gate()
    asyncio.run(main(sys.argv[1]))
