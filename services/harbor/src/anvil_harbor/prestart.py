"""Pure/pre-start source guards. No Trial, Docker, callback or provider execution.

Shared guard implementation. Validation alone grants neither runtime
qualification nor dispatch authority.
"""

import hashlib
import inspect
import json
import marshal
import os
import re
import stat
import types
from pathlib import Path

IMAGE = "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/native-fixture-security@sha256:72b8eaacefaa82ffdec3ee632375df24057962d8c14cc327f1990113f7c2b951"


class GuardBlocked(RuntimeError):
    pass


def need(value, code):
    if not value:
        raise GuardBlocked(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validated():
    return {
        "source_guard_validated": True,
        "dispatch_authorized": False,
        "qualification_granted": False,
    }


def validate_operator_config(config_path):
    root = Path(os.environ.get("ANVIL_HARBOR_ATTEMPT_ROOT", ""))
    need(root.is_absolute() and root.resolve() == root, "owned_attempt_root_required")
    info = root.lstat()
    need(
        stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o077,
        "owned_private_attempt_required",
    )
    path = Path(config_path)
    need(
        path == root / "trial.json" and path.resolve() == path, "fixed_owned_trial_config_required"
    )
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read(65537)
        after = os.fstat(stream.fileno())
    need(
        stat.S_ISREG(before.st_mode)
        and before.st_uid == os.geteuid()
        and before.st_nlink == 1
        and not before.st_mode & 0o077
        and len(raw) <= 65536
        and (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        == (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
        "private_trial_config_changed",
    )
    expected = os.environ.get("ANVIL_HARBOR_TRIAL_CONFIG_SHA256", "")
    need(
        re.fullmatch("[a-f0-9]{64}", expected) and hashlib.sha256(raw).hexdigest() == expected,
        "exact_generated_trial_config_digest_required",
    )
    value = json.loads(raw)
    validate_generated_config(value, attempt_root=str(root), trial_name=value.get("trial_name"))
    return value


def validate_service_proof_map(value):
    need(
        isinstance(value, dict)
        and set(value) == {"environment", "tests"}
        and all(isinstance(v, str) and re.fullmatch("[a-f0-9]{64}", v) for v in value.values()),
        "reviewed_both_role_service_projections_required",
    )
    return value


def validate_generated_config(config, *, attempt_root, trial_name):
    root = Path(attempt_root)
    need(
        root.is_absolute() and str(root) == attempt_root and ".." not in root.parts,
        "canonical_attempt_root_required",
    )
    need(
        isinstance(trial_name, str) and re.fullmatch("anvil-bm-[a-f0-9]{20}", trial_name),
        "fixed_trial_name_required",
    )
    expected = {
        "task": {"path": str(root / "task")},
        "trial_name": trial_name,
        "trials_dir": str(root / "trials"),
        "agent": {"import_path": "anvil_harbor.sme:SMEAgent"},
        "environment": {
            "import_path": "anvil_harbor.environment:LocalComponentsDocker",
            "delete": False,
        },
        "verifier": {"import_path": "anvil_harbor.sme:SMEVerifier"},
    }
    need(canonical(config) == canonical(expected), "complete_generated_configuration_required")
    return validated()


def _memory(value):
    need(type(value) in (str, int), "fixed_memory_limit_required")
    need(value in (536870912, "536870912", "512m"), "fixed_memory_limit_required")
    return 536870912


def validate_effective_service(service, *, role, reviewed_service_sha256):
    need(
        role in ("environment", "tests") and isinstance(service, dict),
        "fixed_service_role_required",
    )
    need(
        isinstance(reviewed_service_sha256, str)
        and re.fullmatch("[a-f0-9]{64}", reviewed_service_sha256),
        "independently_reviewed_service_projection_required",
    )
    need(digest(service) == reviewed_service_sha256, "full_effective_service_projection_changed")
    need(
        service.get("image") == IMAGE
        and service.get("pull_policy") == "never"
        and service.get("user") == "10001:10001"
        and service.get("read_only") is True
        and service.get("network_mode") == "none",
        "fixed_image_user_network_root_required",
    )
    need(
        service.get("cap_drop") == ["ALL"]
        and not service.get("cap_add")
        and service.get("security_opt") == ["no-new-privileges:true"],
        "capabilities_or_privilege_policy_changed",
    )
    for key in (
        "build",
        "privileged",
        "ports",
        "devices",
        "pid",
        "ipc",
        "gpus",
        "runtime",
        "userns_mode",
        "volumes_from",
        "links",
        "external_links",
        "credential_spec",
        "secrets",
        "configs",
        "env_file",
        "extra_hosts",
        "dns",
        "dns_search",
        "sysctls",
        "group_add",
        "develop",
        "post_start",
        "pre_stop",
    ):
        need(not service.get(key), "forbidden_effective_service_extension")
    need(
        type(service.get("pids_limit")) is int and service["pids_limit"] == 64,
        "fixed_pid_limit_required",
    )
    cpu = service.get("cpus")
    need(type(cpu) in (int, float, str) and cpu in (1, 1.0, "1", "1.0"), "fixed_cpu_limit_required")
    _memory(service.get("mem_limit"))
    _memory(service.get("memswap_limit"))
    need(
        service.get("working_dir") == ("/workspace" if role == "environment" else "/tmp")
        and service.get("command") == ["sleep", "infinity"]
        and not service.get("entrypoint"),
        "fixed_workdir_and_idle_command_required",
    )
    expected = [
        "/workspace:rw,nosuid,nodev,size=16m,uid=10001,gid=10001",
        "/tmp:rw,nosuid,nodev,noexec,size=16m,uid=10001,gid=10001",
    ]
    if role == "tests":
        expected += ["/logs/artifacts:rw,nosuid,nodev,noexec,size=16m,uid=10001,gid=10001"]
    need(
        isinstance(service.get("tmpfs"), list) and sorted(service["tmpfs"]) == sorted(expected),
        "fixed_tmpfs_policy_required",
    )
    need(
        service.get("environment") == {"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
        "secret_free_effective_environment_required",
    )
    # Full source/target/read-only volume projections, resource/deploy extensions
    # and all other effective fields remain bound by the independent whole-service
    # digest. Existing SMEDocker mount containment checks must also run.
    return validated()


def validate_callback(
    callback, manifest, *, trusted_source_root, request_sha256, reviewed_manifest_sha256
):
    need(
        isinstance(manifest, dict)
        and set(manifest)
        == {
            "schema_version",
            "module",
            "symbol",
            "source_path",
            "source_sha256",
            "code_sha256",
            "request_sha256",
            "execution_profile",
        },
        "callback_manifest_keys_invalid",
    )
    need(
        isinstance(reviewed_manifest_sha256, str)
        and re.fullmatch("[a-f0-9]{64}", reviewed_manifest_sha256)
        and digest(manifest) == reviewed_manifest_sha256,
        "independently_reviewed_callback_manifest_required",
    )
    need(
        manifest["schema_version"] == "anvil.trusted-no-provider-callback.v1"
        and manifest["request_sha256"] == request_sha256
        and isinstance(request_sha256, str)
        and re.fullmatch("[a-f0-9]{64}", request_sha256)
        and manifest["execution_profile"] == "deterministic_no_provider",
        "callback_request_or_profile_changed",
    )
    need(
        type(callback) is types.FunctionType
        and callback.__module__ == manifest["module"]
        and callback.__qualname__ == manifest["symbol"]
        and callback.__name__ == manifest["symbol"]
        and manifest["module"].startswith("anvil.")
        and not callback.__closure__
        and callback.__defaults__ is None
        and not callback.__kwdefaults__
        and callback.__code__.co_argcount == 0
        and callback.__code__.co_kwonlyargcount == 0
        and not callback.__code__.co_flags & (inspect.CO_VARARGS | inspect.CO_VARKEYWORDS),
        "fixed_top_level_callback_required",
    )
    root = Path(trusted_source_root)
    path = Path(manifest["source_path"])
    need(
        root.is_absolute()
        and root.resolve() == root
        and path.is_absolute()
        and path.resolve() == path
        and path.is_relative_to(root)
        and Path(callback.__code__.co_filename) == path,
        "callback_source_custody_invalid",
    )
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        raw = stream.read(1_000_001)
        need(
            stat.S_ISREG(info.st_mode)
            and info.st_uid in (0, os.geteuid())
            and not info.st_mode & 0o022
            and info.st_nlink == 1
            and len(raw) <= 1_000_000,
            "callback_source_custody_invalid",
        )
    need(
        hashlib.sha256(raw).hexdigest() == manifest["source_sha256"]
        and hashlib.sha256(marshal.dumps(callback.__code__)).hexdigest() == manifest["code_sha256"],
        "callback_source_or_runtime_code_changed",
    )
    bindings = inspect.getclosurevars(callback)
    pure_builtins = {
        "dict",
        "list",
        "tuple",
        "str",
        "int",
        "float",
        "bool",
        "len",
        "sum",
        "min",
        "max",
        "range",
        "sorted",
        "enumerate",
        "zip",
        "abs",
        "round",
        "all",
        "any",
    }
    need(
        not bindings.globals
        and not bindings.nonlocals
        and not bindings.unbound
        and set(bindings.builtins) <= pure_builtins,
        "callback_dynamic_or_unreviewed_dependencies",
    )
    # Source/global dependencies and no-provider behavior require independent
    # review and runtime enforcement. A matching source label never proves them.
    return validated()
