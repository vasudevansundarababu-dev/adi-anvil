"""Installed package/source/policy controls; no runtime admission or model calls."""

import hashlib
import importlib
import importlib.metadata as metadata
import json
import os
import runpy
import sys
import tempfile
import warnings
from pathlib import Path
from threading import Event
from time import monotonic

import anvil_harbor
from anvil_harbor import environment as harbor_environment

import anvil
from anvil.golden_kyc_evaluators import OPA_POLICIES, opa_guard
from anvil.golden_kyc_service import run_worker
from anvil.golden_kyc_source import source_hash
from anvil.marketing_native_private_records import (
    OPERATOR_PROOF_SHA256,
    original_operator_repository,
)


def installed_owned_log_control():
    """Actual Harbor constructor/mount writer, no Docker or native admission."""
    from anvil_harbor.prestart import canonical
    from anvil_harbor.sme import IMAGE, SMEDocker
    from harbor.environments.factory import EnvironmentFactory
    from harbor.models.task.config import EnvironmentConfig, NetworkMode, NetworkPolicy, TaskOS
    from harbor.models.trial.config import EnvironmentConfig as TrialEnvironmentConfig
    from harbor.models.trial.paths import TrialPaths
    from harbor.trial.trial import _harbor_log_bind_mount

    from anvil.environment_harbor import layout

    saved = os.environ.copy()
    try:
        with tempfile.TemporaryDirectory(prefix="anvil-installed-log-control-") as temporary:
            root = Path(temporary).resolve()
            layout(root, {"label": "synthetic-installed-log-control"}, actor_seconds=30)
            name = "anvil-bm-" + "a" * 20
            config = {"task": {"path": str(root / "task")}, "trial_name": name,
                      "trials_dir": str(root / "trials"), "agent": {"import_path": "anvil_harbor.sme:SMEAgent"},
                      "environment": {"import_path": "anvil_harbor.environment:LocalComponentsDocker", "delete": False},
                      "verifier": {"import_path": "anvil_harbor.sme:SMEVerifier"}}
            raw = canonical(config)
            (root / "trial.json").write_bytes(raw)
            (root / "trial.json").chmod(0o600)
            os.environ.update(ANVIL_HARBOR_ATTEMPT_ROOT=str(root),
                              ANVIL_HARBOR_TRIAL_CONFIG_SHA256=hashlib.sha256(raw).hexdigest(),
                              ANVIL_HARBOR_SERVICE_SHA256S=json.dumps({"environment": "a" * 64, "tests": "b" * 64}))
            paths = TrialPaths(trial_dir=root / "trials" / name)
            protected = {p: p.stat().st_mode for p in (root, root / "private", root / "sealed")}
            mounts = [_harbor_log_bind_mount(source=str(source), target=target, os=TaskOS.LINUX)
                      for source, target in ((paths.verifier_dir, "/logs/verifier"), (paths.agent_dir, "/logs/agent"),
                                             (paths.host_artifact_path("main", "/logs/artifacts"), "/logs/artifacts"))]
            for role, expected in (("environment", mounts[1:]), ("tests", mounts[:1])):
                instance = EnvironmentFactory.create_environment_from_config(
                                     config=TrialEnvironmentConfig(**config["environment"]),
                                     environment_dir=root / "task" / role, environment_name="synthetic",
                                     session_id=name + ("__env" if role == "environment" else "__verifier__trial"),
                                     trial_paths=paths, task_env_config=EnvironmentConfig(docker_image=IMAGE,
                                         network_mode=NetworkMode.NO_NETWORK, cpus=1, memory_mb=512),
                                     network_policy=NetworkPolicy(network_mode=NetworkMode.NO_NETWORK),
                                     auto_mounts=mounts if role == "environment" else mounts[:1])
                assert instance.auto_mounting is False
                assert isinstance(instance, SMEDocker)
                assert instance._host_mounts == expected and instance._mounts == expected
                rendered = json.loads(instance._write_mounts_compose_file().read_bytes())
                assert rendered == {"services": {"main": {"volumes": expected}}}
                instance._cleanup_mounts_compose_file()
                assert root.stat().st_mode & 0o777 == 0o700
                assert paths.trial_dir.stat().st_mode & 0o022 == 0
                assert (root / "sealed").stat().st_mode & 0o022 == 0
                assert all(path.stat().st_mode == mode for path, mode in protected.items())
    finally:
        os.environ.clear()
        os.environ.update(saved)


installed_owned_log_control()

VERSIONS = {
    "harbor": "0.25.0",
    "openenv": "0.12.0",
    "mcp": "1.30.0",
    "langgraph": "1.2.14",
    "langgraph-checkpoint-postgres": "3.1.3",
    "zen-engine": "2.1.3",
}
for name, expected in VERSIONS.items():
    assert metadata.version(name) == expected, name
for name in (
    "harbor",
    "openenv",
    "mcp",
    "langgraph.graph",
    "langgraph.checkpoint.postgres",
    "anvil.golden_kyc_worker",
    "anvil.golden_kyc_grader",
    "anvil.golden_kyc_service",
    "anvil.marketing_paid_execution",
    "anvil.campaign_grader",
    "anvil_harbor.marketing",
):
    importlib.import_module(name)

# Exercise the actual installed -m entry without starting Docker or a Trial.
# The factory imports the canonical module; a duplicate __main__ adapter cannot
# pass its exact type checks. Keep this installed-Harbor control distinct from
# the later physical native Trial qualification.
entry_observed = []
original_main, original_argv = harbor_environment.main, sys.argv


async def entry_control(path):
    entry_observed.append((path, harbor_environment.LocalComponentsDocker.__module__))


try:
    harbor_environment.main = entry_control
    sys.argv = ["anvil_harbor.environment", "synthetic-entry-control.json"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("anvil_harbor.environment", run_name="__main__")
finally:
    harbor_environment.main, sys.argv = original_main, original_argv
assert entry_observed == [("synthetic-entry-control.json", "anvil_harbor.environment")]

matched = 0
for folder, package in (("backend", anvil), ("harbor", anvil_harbor)):
    source = Path("/opt/anvil-runtime-source/services") / folder / "src" / package.__name__
    installed = Path(package.__file__).parent
    for path in source.rglob("*.py"):
        assert path.read_bytes() == (installed / path.relative_to(source)).read_bytes()
        matched += 1
source_sha256 = source_hash()
# The actual SDK import path installs Beartype's global path hook. First-party
# modules loaded afterward must still pass exact raw-source/code verification.
from anvil.golden_kyc_openenv import GoldenEnvironment  # noqa: E402,F401
from anvil.golden_mcp_client import McpEpisode  # noqa: E402,F401
from anvil.golden_phase_checkpoints import execute as phase_execute  # noqa: E402,F401

wrapped_first_party = [name for name, module in tuple(sys.modules.items())
    if name.startswith(("anvil.", "anvil_harbor."))
    and type(getattr(getattr(module, "__spec__", None), "loader", None)).__name__ == "BeartypeSourceFileLoader"]
assert wrapped_first_party, "Installed control must exercise the real SDK import hook"
assert source_hash() == source_sha256
if os.environ.get("EXPECTED_SOURCE_SHA256"):
    assert source_sha256 == os.environ["EXPECTED_SOURCE_SHA256"]
repository = original_operator_repository()
assert repository == Path("/opt/anvil-runtime-source")
assert (
    hashlib.sha256(
        (repository / "services/harbor/src/anvil_harbor/operator_proof.py").read_bytes()
    ).hexdigest()
    == OPERATOR_PROOF_SHA256
)
facts = {name: True for name in OPA_POLICIES}
assert opa_guard(facts)["allow"] is True
assert opa_guard(facts | {"assigned_case": False})["allow"] is False
assert opa_guard({})["allow"] is False
# Execute the actual installed service child entry, without opening a DB.
run_worker(["--help"], deadline=monotonic() + 20, stop=Event())
print(
    json.dumps(
        {
            "scope": "installed_source_packages_and_software_controls_only",
            "source_files_matched": matched,
            "source_sha256": source_sha256,
            "versions": VERSIONS,
            "opa_binary_sha256": hashlib.sha256(Path("/opt/anvil/opa").read_bytes()).hexdigest(),
            "policy_controls": 3,
            "model_calls": 0,
            "native_qualified": False,
            "canonical_module_entry_control": True,
            "actual_sdk_explicit_log_mount_control": True,
            "post_sdk_import_source_validation": True,
        }
    )
)
