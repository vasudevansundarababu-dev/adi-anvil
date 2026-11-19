"""Root-owned proof binding only; a cutover admission is not task authority."""

import hashlib
import importlib.metadata
import json
import os
import re
import stat
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

ROOT = Path("/var/lib/anvil-qa-v1/runtime-functional/harbor-proof")
STOP = datetime(2026, 12, 11, 5, 48, 4, tzinfo=timezone.utc)
MAX_BYTES = 1048576
CHECKS = {
    "image_source_locks",
    "role_isolation",
    "native_mcp_reset_checkpoint",
    "scoring_safety_report",
    "code_schema_rollback_compatibility",
    "private_mounts_metadata",
    "no_model_calls",
}
REQUIRED_DEPENDENCIES = {
    "services/backend/src/anvil/golden_native_peer.py",
    "services/backend/src/anvil/golden_kyc_probe.py",
    "services/backend/src/anvil/golden_kyc_probe_prepare.py",
    "services/harbor/src/anvil_harbor/environment.py",
    "services/harbor/src/anvil_harbor/sme.py",
    "services/backend/src/anvil/golden_kyc_harbor.py",
    "services/backend/src/anvil/golden_kyc_identity.py",
    "services/backend/src/anvil/golden_kyc_fixed_process.py",
    "services/backend/src/anvil/owned_process_group.py",
    "services/backend/src/anvil/golden_kyc_runtime.py",
    "services/backend/src/anvil/golden_kyc_data.py",
    "services/backend/src/anvil/golden_kyc_engine.py",
    "services/backend/src/anvil/golden_kyc_evaluators.py",
    "services/backend/src/anvil/golden_kyc_policy.py",
    "services/backend/src/anvil/golden_kyc_state_checks.py",
    "services/backend/src/anvil/task_safety_runtime.py",
    "services/backend/src/anvil/db.py",
    "services/backend/src/anvil/environment_harbor.py",
    "services/harbor/src/anvil_harbor/prestart.py",
    "services/harbor/requirements.lock",
    "services/backend/uv.lock",
}


class ProofBlocked(RuntimeError):
    pass


def need(value, code):
    if not value:
        raise ProofBlocked(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def hash_value(value):
    return isinstance(value, str) and re.fullmatch("[a-f0-9]{64}", value) is not None


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "duplicate_operator_proof_key")
            result[key] = value
        return result

    def invalid(_):
        raise ProofBlocked("nonfinite_operator_proof")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def validate_business_context(context):
    need(
        isinstance(context, dict) and context.get("paid_calls") is False,
        "no_paid_business_context_required",
    )
    common = {"kind", "project_id", "user_id", "paid_calls"}
    if context.get("kind") == "golden_kyc_software_v1":
        extra = {
            "pack_id",
            "application_id",
            "environment_version",
            "snapshot_sha256",
            "script_sha256",
        }
        hashes = ("snapshot_sha256", "script_sha256")
        for key in ("pack_id", "application_id", "environment_version"):
            need(
                isinstance(context.get(key), str) and 1 <= len(context[key]) <= 160,
                "bounded_KYC_context_required",
            )
    else:
        need(
            context.get("kind") == "configured_environment_script_v1",
            "fixed_business_context_kind_required",
        )
        extra = {
            "run_id",
            "binding_id",
            "environment_id",
            "environment_manifest_sha256",
            "pack_sha256",
            "task_payload_sha256",
            "actions_sha256",
            "candidate",
            "repetition",
        }
        hashes = (
            "environment_manifest_sha256",
            "pack_sha256",
            "task_payload_sha256",
            "actions_sha256",
        )
        need(
            context.get("candidate") == "configured-tools-v1"
            and type(context.get("repetition")) is int
            and 1 <= context["repetition"] <= 10,
            "deterministic_collection_context_required",
        )
        for key in ("run_id", "binding_id", "environment_id"):
            need(str(UUID(context[key])) == context[key], "canonical_collection_identity_required")
    need(
        set(context) == common | extra and all(hash_value(context.get(key)) for key in hashes),
        "complete_business_context_required",
    )
    for key in ("project_id", "user_id"):
        need(str(UUID(context[key])) == context[key], "canonical_business_identity_required")


class OperatorProofStore:
    def __init__(self, repository_root):
        need(
            os.geteuid() == 0 and os.uname().nodename == "anvil-qa-v1",
            "existing_QA_root_operator_required",
        )
        self._initialize(ROOT, repository_root, 0, "root_owned_prestart_binding_only")

    @classmethod
    def for_owned_local_test(cls, root, repository_root, *, clock=None):
        instance = object.__new__(cls)
        instance._initialize(Path(root), repository_root, os.geteuid(), "owned_test_NOT_QA")
        if clock is not None:
            instance._clock = clock
        return instance

    def _initialize(self, root, repository_root, owner, scope):
        need(
            root.is_absolute() and root.resolve() == root, "canonical_operator_proof_root_required"
        )
        self.root = root
        self.repository = Path(repository_root)
        need(
            self.repository.is_absolute() and self.repository.resolve() == self.repository,
            "canonical_source_root_required",
        )
        self.owner, self.scope = owner, scope
        self._clock = lambda: datetime.now(timezone.utc)
        self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self._private(os.fstat(self.fd), directory=True)
        except Exception:
            os.close(self.fd)
            raise

    def _private(self, info, *, directory=False):
        need(
            (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            and info.st_uid == self.owner
            and not info.st_mode & 0o077
            and (directory or info.st_nlink == 1),
            "private_operator_owned_proof_required",
        )

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _directory(self, name):
        need(
            name
            in {
                "admissions",
                "qualifications",
                "bindings",
                "operations",
                "operation-preflights",
                "operation-assets",
                "operation-bindings",
                "operation-intents",
                "operation-outcomes",
            },
            "fixed_operator_directory_required",
        )
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            self._private(os.fstat(fd), directory=True)
        except Exception:
            os.close(fd)
            raise
        return fd

    def _read(self, directory, filename):
        need(re.fullmatch(r"[a-f0-9-]+\.json", filename), "fixed_operator_filename_required")
        folder = self._directory(directory)
        try:
            fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                self._private(before)
                raw = stream.read(MAX_BYTES + 1)
                after = os.fstat(stream.fileno())
                need(
                    len(raw) <= MAX_BYTES
                    and (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    == (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                    "operator_proof_changed_or_oversized",
                )
                return raw
        finally:
            os.close(folder)

    def _dependencies(self, values):
        need(
            isinstance(values, dict) and REQUIRED_DEPENDENCIES <= set(values),
            "reviewed_business_dependencies_missing",
        )
        need(len(values) <= 128, "business_dependency_bound")
        for relative, expected in values.items():
            path = self.repository / relative
            need(
                isinstance(relative, str)
                and (
                    relative.startswith(("services/backend/src/", "services/harbor/"))
                    or relative == "services/backend/uv.lock"
                )
                and ".." not in Path(relative).parts
                and path.resolve() == path
                and path.is_relative_to(self.repository)
                and hash_value(expected),
                "business_dependency_path_invalid",
            )
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                need(
                    stat.S_ISREG(info.st_mode)
                    and info.st_uid in (0, self.owner)
                    and not info.st_mode & 0o022
                    and info.st_nlink == 1
                    and info.st_size <= MAX_BYTES,
                    "business_dependency_custody_invalid",
                )
                raw = stream.read(MAX_BYTES + 1)
            need(
                len(raw) <= MAX_BYTES and sha(raw) == expected, "business_dependency_source_changed"
            )

    def derive(self, job_id, actor):
        need(str(UUID(job_id)) == job_id, "canonical_operator_job_required")
        raw = self._read("admissions", job_id + ".json")
        envelope = parse(raw)
        need(
            set(envelope) == {"job_id", "admission"} and envelope["job_id"] == job_id,
            "operator_job_admission_binding_invalid",
        )
        admission = envelope["admission"]
        need(
            admission.get("origin") == "independent_qa"
            and admission.get("deployment_id") == "anvil-qa-v1"
            and admission.get("host_id") == "8748412716380175314"
            and admission.get("role") == admission.get("service") == "golden-native-coordinator"
            and set(admission.get("checks", {})) == CHECKS
            and all(hash_value(v) for v in admission["checks"].values()),
            "exact_role_admission_required",
        )
        need(
            admission.get("model_calls") == 0
            and type(admission["model_calls"]) is int
            and admission.get("schema_changes") is False
            and admission.get("new_services") is False
            and admission.get("build_limit") == 31
            and admission.get("infrastructure_usd_month") == 550
            and admission.get("qa_pilot_usd") == 100
            and admission.get("qa_aggregate_run_usd") == 2,
            "original_no_paid_pilot_limits_required",
        )
        expires = datetime.fromisoformat(admission["expires_at"])
        stop = datetime.fromisoformat(admission["stop_at"])
        clock = self._clock()
        need(
            expires.tzinfo is not None
            and stop == STOP
            and clock.tzinfo is not None
            and clock < min(expires, STOP),
            "operator_admission_or_original_pilot_expired",
        )
        qualification_hash = admission.get("qualification_sha256")
        need(hash_value(qualification_hash), "qualification_pin_required")
        qualification_raw = self._read("qualifications", qualification_hash + ".json")
        need(
            sha(qualification_raw) == qualification_hash, "independent_qualification_digest_changed"
        )
        qualification = parse(qualification_raw)
        need(
            qualification.get("schema_version") == "anvil.runtime-role-qualification.v1"
            and qualification.get("origin") == "independent_qa",
            "independent_role_qualification_required",
        )
        for key in (
            "role",
            "source_commit",
            "image_digest",
            "lock_digest",
            "operator_spec_sha256",
            "checks",
        ):
            need(
                key in admission and qualification.get(key) == admission[key],
                "qualification_admission_pin_mismatch",
            )
        actor_hash = sha(canonical(actor))
        row = qualification.get("harbor_prestart_bindings", {}).get(actor_hash)
        need(
            isinstance(row, dict)
            and set(row)
            == {
                "request_capsule",
                "callback_manifest",
                "service_projection_sha256s",
                "dependency_source_sha256s",
            },
            "reviewed_request_specific_binding_missing",
        )
        capsule = row["request_capsule"]
        need(
            isinstance(capsule, dict)
            and set(capsule) == {"schema_version", "actor", "business_context"}
            and capsule["schema_version"] == "anvil.harbor-business-request.v1"
            and canonical(capsule["actor"]) == canonical(actor),
            "reviewed_actor_projection_changed",
        )
        validate_business_context(capsule["business_context"])
        request_hash = sha(canonical(capsule))
        callback = row["callback_manifest"]
        need(
            isinstance(callback, dict) and callback.get("request_sha256") == request_hash,
            "callback_not_bound_to_full_operator_request",
        )
        profiles = row["service_projection_sha256s"]
        need(
            isinstance(profiles, dict)
            and set(profiles) == {"environment", "tests"}
            and all(hash_value(v) for v in profiles.values()),
            "reviewed_both_role_profiles_required",
        )
        self._dependencies(row["dependency_source_sha256s"])
        return {
            "schema_version": "anvil.operator-Harbor-proof-binding.v1",
            "custody_scope": self.scope,
            "job_id": job_id,
            "actor_sha256": actor_hash,
            "admission_file_sha256": sha(raw),
            "qualification_sha256": qualification_hash,
            "request_sha256": request_hash,
            "callback_manifest": callback,
            "callback_manifest_sha256": sha(canonical(callback)),
            "service_projection_sha256s": profiles,
            "request_capsule": capsule,
            "proof_binding_only": True,
            "business_operation_authorized": False,
        }

    def produce(self, job_id, actor):
        binding = self.derive(job_id, actor)
        raw = canonical(binding) + b"\n"
        need(len(raw) <= MAX_BYTES, "operator_binding_size_limit")
        folder = self._directory("bindings")
        try:
            fd = os.open(
                binding["actor_sha256"] + ".json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=folder,
            )
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(folder)
        finally:
            os.close(folder)
        return binding

    def load(self, actor):
        actor_hash = sha(canonical(actor))
        stored = parse(self._read("bindings", actor_hash + ".json"))
        current = self.derive(stored["job_id"], actor)
        need(canonical(stored) == canonical(current), "operator_binding_changed_or_foreign")
        return current

    def _write_once(self, directory, filename, value):
        raw = canonical(value) + b"\n"
        need(len(raw) <= MAX_BYTES, "operation_record_size_limit")
        need(re.fullmatch(r"[a-f0-9-]+\.json", filename), "fixed_operator_filename_required")
        folder = self._directory(directory)
        try:
            fd = os.open(
                filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder
            )
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(folder)
        finally:
            os.close(folder)
        return sha(raw)

    def derive_operation(self, job_id, actor, business_context):
        """Derive a separate source-only admission; never upgrade role proof.

        Inputs must already exist under independent operator custody. This
        producer does not create approvals, runtime asset proof or directories.
        """
        role = self.derive(job_id, actor)
        validate_business_context(business_context)
        need(business_context["kind"] == "golden_kyc_software_v1", "fixed_KYC_operation_required")
        need(
            canonical(role["request_capsule"]["business_context"]) == canonical(business_context),
            "operation_business_context_changed",
        )
        raw = self._read("operations", job_id + ".json")
        operation = parse(raw)
        need(
            isinstance(operation, dict)
            and set(operation)
            == {
                "schema_version",
                "origin",
                "job_id",
                "operation",
                "operation_nonce",
                "role_binding_sha256",
                "request_sha256",
                "expires_at",
                "stop_at",
                "dependency_source_sha256s",
                "preflight_sha256",
                "limits",
            },
            "exact_operation_admission_required",
        )
        need(
            operation["schema_version"] == "anvil.fixed-KYC-operation-admission.v1"
            and operation["origin"] == "independent_operator"
            and operation["operation"] == "golden_kyc_two_read_software_v1"
            and operation["job_id"] == job_id
            and operation["role_binding_sha256"] == sha(canonical(role))
            and operation["request_sha256"] == role["request_sha256"]
            and hash_value(operation["operation_nonce"]),
            "operation_admission_binding_changed",
        )
        expires = datetime.fromisoformat(operation["expires_at"])
        need(
            expires.tzinfo is not None
            and self._clock() < min(expires, STOP)
            and datetime.fromisoformat(operation["stop_at"]) == STOP,
            "operation_admission_expired",
        )
        limits = operation["limits"]
        need(
            isinstance(limits, dict)
            and limits
            == {
                "callback_invocations": 1,
                "actions": 2,
                "resets": 1,
                "wall_seconds": 30,
                "connection_seconds": 2,
                "statement_ms": 1500,
                "lock_ms": 500,
            }
            and all(type(v) is int for v in limits.values()),
            "fixed_operation_limits_required",
        )
        self._dependencies(operation["dependency_source_sha256s"])
        preflight_hash = operation["preflight_sha256"]
        need(hash_value(preflight_hash), "operation_preflight_pin_required")
        preflight_raw = self._read("operation-preflights", preflight_hash + ".json")
        need(sha(preflight_raw) == preflight_hash, "operation_preflight_changed")
        preflight = parse(preflight_raw)
        need(
            isinstance(preflight, dict)
            and set(preflight)
            == {
                "schema_version",
                "request_sha256",
                "operation_nonce",
                "role_binding_sha256",
                "service_projection_sha256s",
                "assets",
            }
            and preflight["schema_version"] == "anvil.fixed-KYC-operation-preflight.v1"
            and all(
                preflight[k] == operation[k]
                for k in ("request_sha256", "operation_nonce", "role_binding_sha256")
            )
            and preflight["service_projection_sha256s"] == role["service_projection_sha256s"],
            "operation_preflight_binding_changed",
        )
        assets = preflight["assets"]
        need(
            isinstance(assets, dict)
            and set(assets)
            == {
                "runtime_seal",
                "trial_config",
                "task_package",
                "host_image_custody",
                "recovery_recipe",
                "environment_service",
                "tests_service",
            }
            and all(hash_value(v) for v in assets.values()),
            "complete_operation_assets_required",
        )
        for name, pin in assets.items():
            asset_raw = self._read("operation-assets", pin + ".json")
            need(sha(asset_raw) == pin, "operation_asset_bytes_changed")
            # Hash custody alone is intentionally not native asset qualification.
            need(isinstance(parse(asset_raw), dict), "operation_asset_object_required")
            if name in ("environment_service", "tests_service"):
                role_name = "environment" if name == "environment_service" else "tests"
                need(
                    sha(canonical(parse(asset_raw)))
                    == role["service_projection_sha256s"][role_name],
                    "operation_service_projection_changed",
                )
        return {
            "schema_version": "anvil.fixed-KYC-operation-binding.v1",
            "custody_scope": self.scope,
            "job_id": job_id,
            "actor_sha256": role["actor_sha256"],
            "request_sha256": role["request_sha256"],
            "request_capsule": role["request_capsule"],
            "role_binding_sha256": operation["role_binding_sha256"],
            "operation_admission_sha256": sha(raw),
            "operation_nonce": operation["operation_nonce"],
            "preflight_sha256": preflight_hash,
            "asset_sha256s": assets,
            "service_projection_sha256s": role["service_projection_sha256s"],
            "dependency_source_sha256s": operation["dependency_source_sha256s"],
            "limits": limits,
            "operation_context_derived": True,
            "business_operation_authorized": False,
            "native_trial_qualified": False,
            "dispatch_authorized": False,
        }

    def produce_operation(self, job_id, actor, business_context):
        binding = self.derive_operation(job_id, actor, business_context)
        self._write_once("operation-bindings", binding["actor_sha256"] + ".json", binding)
        return binding

    def operation_assets(self, binding):
        """Reload hash-bound documents; callers must validate their semantics."""
        result = {}
        for name, pin in binding["asset_sha256s"].items():
            raw = self._read("operation-assets", pin + ".json")
            need(sha(raw) == pin, "operation_asset_bytes_changed")
            result[name] = parse(raw)
        return result

    def _sealed_file(self, path, expected):
        path = Path(path)
        need(
            path.is_absolute() and path.resolve() == path and hash_value(expected),
            "canonical_runtime_file_required",
        )
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            need(
                stat.S_ISREG(info.st_mode)
                and info.st_uid in (0, self.owner)
                and not info.st_mode & 0o022
                and info.st_size <= 268435456,
                "runtime_file_custody_invalid",
            )
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1048576), b""):
                digest.update(chunk)
        need(digest.hexdigest() == expected, "runtime_file_bytes_changed")

    def validate_runtime_seal(self, seal):
        """Inspect complete installed RECORD inventories without importing SDKs."""
        need(
            set(seal) == {"schema_version", "components"}
            and seal["schema_version"] in {"anvil.fixed-runtime-seal.v1", "anvil.fixed-runtime-seal.v2"}
            and set(seal["components"]) == {"backend", "harbor"},
            "full_runtime_seal_required",
        )
        checked_common = set()
        for component, record in seal["components"].items():
            need(
                set(record)
                == {
                    "prefix",
                    "site_packages",
                    "interpreter",
                    "interpreter_sha256",
                    "python_version",
                    "venv_config_sha256",
                    "distributions",
                    "source_packages",
                    "source_files_sha256",
                    "stdlib_root",
                    "stdlib_files_sha256",
                },
                "exact_runtime_component_required",
            )
            common = {key: value for key, value in record.items()
                      if key not in {"source_packages", "source_files_sha256"}}
            fingerprint = sha(canonical(common))
            readonly = self._runtime_install_readonly(record)
            if not (readonly and fingerprint in checked_common):
                self._validate_runtime_common(record)
                if readonly:
                    checked_common.add(fingerprint)
            if component == "harbor":
                harbor = record["distributions"].get("harbor")
                need(harbor and harbor["version"] == "0.25.0", "exact_Harbor_distribution_required")
            site = Path(record["site_packages"])
            expected_packages = {"anvil"} if component == "backend" else {"anvil_harbor"}
            need(
                set(record["source_packages"]) == expected_packages, "exact_source_package_required"
            )
            discovered = set()
            for package, folder in record["source_packages"].items():
                folder = Path(folder)
                expected_folder = self.repository / (
                    "services/backend/src/anvil"
                    if component == "backend"
                    else "services/harbor/src/anvil_harbor"
                )
                if seal["schema_version"] == "anvil.fixed-runtime-seal.v2":
                    expected_folder = site / package
                need(
                    folder.is_absolute()
                    and folder.resolve() == folder
                    and folder == expected_folder
                    and not (self.repository / ".env").exists(),
                    "source_package_origin_changed",
                )
                for path in folder.rglob("*"):
                    if not path.is_file():
                        continue
                    need(path.resolve() == path, "source_package_alias_forbidden")
                    discovered.add(str(path))
            source_files = self._runtime_manifest(record["source_files_sha256"])
            need(
                discovered == set(source_files) and discovered,
                "complete_source_package_closure_required",
            )
            for path, expected in source_files.items():
                self._sealed_file(path, expected)
                if seal["schema_version"] == "anvil.fixed-runtime-seal.v2":
                    for package, folder in record["source_packages"].items():
                        if Path(path).is_relative_to(folder):
                            source = self.repository / ("services/backend/src" if component == "backend"
                                                      else "services/harbor/src") / package / Path(path).relative_to(folder)
                            self._sealed_file(source, expected)
        return {"runtime_bytes_validated": True, "dispatch_authorized": False}

    @staticmethod
    def _runtime_install_readonly(record):
        """Inspect every mount traversed by the common closure, not just roots.

        A writable nested directory/file bind mount can live below a readonly
        prefix. The venv interpreter may also resolve outside that prefix.
        Only a per-call optimization depends on this conservative observation.
        """
        try:
            roots = {Path(record[key]) for key in ("prefix", "site_packages", "stdlib_root")}
            paths = {Path(record["interpreter"]).resolve(), Path(record["prefix"]) / "pyvenv.cfg"}
            for root in roots:
                paths.add(root)
                paths.update(root.rglob("*"))
            return all(os.statvfs(path).f_flag & os.ST_RDONLY for path in paths)
        except OSError:
            return False

    def _validate_runtime_common(self, record):
        """Complete interpreter, distribution, site and stdlib validation."""
        prefix, site = Path(record["prefix"]), Path(record["site_packages"])
        need(
            prefix.is_absolute()
            and prefix.resolve() == prefix
            and site.resolve() == site
            and site.is_relative_to(prefix),
            "runtime_distribution_origin_changed",
        )
        launch = Path(record["interpreter"])
        need(
            launch.parent == prefix / "bin"
            and launch.name in ("python", "python3", "python3.12"),
            "exact_venv_interpreter_origin_required",
        )
        self._sealed_file(launch.resolve(), record["interpreter_sha256"])
        need(launch.stat().st_mode & 0o111, "executable_interpreter_required")
        self._sealed_file(prefix / "pyvenv.cfg", record["venv_config_sha256"])
        configuration = dict(
            line.split("=", 1)
            for line in (prefix / "pyvenv.cfg").read_text().splitlines()
            if "=" in line
        )
        configuration = {k.strip(): v.strip() for k, v in configuration.items()}
        need(
            configuration.get("version") == record["python_version"]
            and record["python_version"].startswith("3.12.")
            and configuration.get("include-system-site-packages") == "false",
            "interpreter_version_or_system_site_changed",
        )
        observed = {}
        for dist in importlib.metadata.distributions(path=[str(site)]):
            name = re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower()
            need(name not in observed, "duplicate_runtime_distribution")
            observed[name] = dist
        declared = record["distributions"]
        need(
            set(observed) == set(declared) and 1 <= len(declared) <= 256,
            "full_distribution_inventory_changed",
        )
        installed_paths = set()
        for name, dist in observed.items():
            entry = declared[name]
            need(
                set(entry) == {"version", "files_sha256"}
                and dist.version == entry["version"]
                and dist.files is not None,
                "runtime_distribution_version_or_RECORD_changed",
            )
            entry_files = self._runtime_manifest(entry["files_sha256"])
            files = {str(p) for p in dist.files}
            need(
                files == set(entry_files)
                and any(p.endswith(".dist-info/RECORD") for p in files),
                "complete_distribution_RECORD_required",
            )
            for relative, expected in entry_files.items():
                path = Path(dist.locate_file(relative)).absolute()
                resolved = path.resolve()
                need(resolved.is_relative_to(prefix), "distribution_file_escaped_prefix")
                # RECORD paths may use ../bin, but their resolved origin is sealed.
                need(
                    Path(os.path.normpath(str(path))) == resolved,
                    "distribution_file_alias_forbidden",
                )
                self._sealed_file(resolved, expected)
                if resolved.is_relative_to(site):
                    installed_paths.add(str(resolved))
        actual_site = {str(p) for p in site.rglob("*") if p.is_file()}
        need(actual_site == installed_paths, "unrecorded_site_package_or_startup_hook")
        stdlib = Path(record["stdlib_root"])
        need(
            stdlib.is_absolute() and stdlib.resolve() == stdlib and stdlib.is_dir(),
            "canonical_stdlib_origin_required",
        )
        actual_stdlib = {
            str(p)
            for p in stdlib.rglob("*")
            if p.is_file() and "site-packages" not in p.relative_to(stdlib).parts
        }
        stdlib_files = self._runtime_manifest(record["stdlib_files_sha256"])
        need(
            actual_stdlib == set(stdlib_files) and actual_stdlib,
            "complete_stdlib_closure_required",
        )
        for path, expected in stdlib_files.items():
            self._sealed_file(path, expected)

    def _runtime_manifest(self, pin):
        need(hash_value(pin), "runtime_file_manifest_pin_required")
        raw = self._read("operation-assets", pin + ".json")
        need(sha(raw) == pin, "runtime_file_manifest_changed")
        value = parse(raw)
        need(
            isinstance(value, dict)
            and 1 <= len(value) <= 20000
            and all(isinstance(k, str) and hash_value(v) for k, v in value.items()),
            "bounded_full_runtime_file_manifest_required",
        )
        return value

    def validate_loaded_origins(self, seal, *, component):
        record = seal["components"][component]
        need(
            Path(sys.prefix).resolve() == Path(record["prefix"]),
            "active_interpreter_prefix_changed",
        )
        source_files = self._runtime_manifest(record["source_files_sha256"])
        # Both independently sealed first-party wheels share this interpreter.
        # A mediated Harbor entry imports the backend plan validator; each
        # package must belong to its OWN exact source inventory, not whichever
        # component initiated this check. Never admit an editable fallback.
        sources = {component: source_files}
        for other in ("backend", "harbor"):
            if other != component:
                sources[other] = self._runtime_manifest(seal["components"][other]["source_files_sha256"])
        allowed = set(source_files)
        allowed.update(self._runtime_manifest(record["stdlib_files_sha256"]))
        for entry in record["distributions"].values():
            for relative in self._runtime_manifest(entry["files_sha256"]):
                allowed.add(str((Path(record["site_packages"]) / relative).resolve()))
        for name, loaded in tuple(sys.modules.items()):
            origin = getattr(loaded, "__file__", None)
            if (
                origin is None
                or getattr(getattr(loaded, "__spec__", None), "origin", None) == "frozen"
            ):
                continue
            need(str(Path(origin).resolve()) in allowed, "loaded_module_origin_outside_seal")
            for package, owner in (("anvil", "backend"), ("anvil_harbor", "harbor")):
                if name == package or name.startswith(package + "."):
                    need(str(Path(origin).resolve()) in sources[owner], owner + "_editable_fallback_forbidden")

    def validate_host_recovery(self, binding, host_record, recovery, *, folder, host, python):
        """Bind independently supplied role/image evidence and enforced budgets."""
        role = self.derive(binding["job_id"], binding["request_capsule"]["actor"])
        need(sha(canonical(role)) == binding["role_binding_sha256"], "current_role_binding_changed")
        admission = parse(self._read("admissions", binding["job_id"] + ".json"))["admission"]
        need(
            set(host_record)
            == {
                "schema_version",
                "deployment_id",
                "host_id",
                "role",
                "image_digest",
                "source_commit",
                "lock_digest",
                "qualification_sha256",
                "docker_host",
                "python",
                "folder",
                "operation_nonce",
                "request_sha256",
                "limits",
                "database_provider",
                "binaries",
            },
            "exact_host_image_record_required",
        )
        need(
            host_record["schema_version"] == "anvil.fixed-host-image-custody.v1"
            and all(
                host_record[k] == admission[k]
                for k in (
                    "deployment_id",
                    "host_id",
                    "role",
                    "image_digest",
                    "source_commit",
                    "lock_digest",
                    "qualification_sha256",
                )
            )
            and host_record["docker_host"] == host
            and host_record["folder"] == str(folder)
            and host_record["python"] == str(python)
            and all(host_record[k] == binding[k] for k in ("operation_nonce", "request_sha256")),
            "host_role_image_request_binding_changed",
        )
        limits = host_record["limits"]
        need(
            isinstance(limits, dict)
            and set(limits)
            == {"connect_seconds", "callback_seconds", "lifecycle_seconds", "cleanup_seconds"}
            and all(type(v) is int for v in limits.values())
            and limits["connect_seconds"] == 2
            and limits["callback_seconds"] == 30
            and 30 <= limits["lifecycle_seconds"] <= 120
            and 1 <= limits["cleanup_seconds"] <= 6
            and limits == admission.get("native_execution_limits"),
            "independently_admitted_native_caps_required",
        )
        need(
            set(recovery)
            == {
                "schema_version",
                "job_id",
                "operation_nonce",
                "request_sha256",
                "folder",
                "docker_host",
                "trial_name",
                "limits",
                "mode",
            }
            and recovery["schema_version"] == "anvil.fixed-Trial-recovery.v1"
            and recovery["mode"] == "reconcile_only_no_replay"
            and recovery["job_id"] == binding["job_id"]
            and all(recovery[k] == binding[k] for k in ("operation_nonce", "request_sha256"))
            and recovery["folder"] == str(folder)
            and recovery["docker_host"] == host
            and recovery["limits"] == limits
            and recovery["trial_name"] == "anvil-bm-" + binding["operation_nonce"][:20],
            "recovery_identity_or_caps_changed",
        )
        binaries = host_record["binaries"]
        need(
            set(binaries) == {"docker", "compose", "python", "opa"}
            and binaries["python"]["path"] == str(python),
            "exact_native_binaries_required",
        )
        for name, record in binaries.items():
            need(set(record) == {"path", "sha256"}, "exact_native_binary_pin_required")
            self._sealed_file(
                Path(record["path"]).resolve() if name == "python" else record["path"],
                record["sha256"],
            )
            need(Path(record["path"]).stat().st_mode & 0o111, "executable_native_binary_required")
        provider = host_record["database_provider"]
        need(
            set(provider) == {"path", "sha256", "field", "database", "server_version"}
            and provider["field"] == "env.GOLDEN_SCHEDULER_DATABASE_URL"
            and isinstance(provider["database"], str)
            and 1 <= len(provider["database"]) <= 63
            and isinstance(provider["server_version"], str)
            and 1 <= len(provider["server_version"]) <= 256
            and Path(provider["path"]).is_relative_to(self.root.parent),
            "fixed_scheduler_provider_required",
        )
        self._sealed_file(provider["path"], provider["sha256"])
        fd = os.open(provider["path"], os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            self._private(os.fstat(stream.fileno()))
        return limits

    def scheduler_secret(self, provider):
        """Private return value for the fixed worker only; never evidence output."""
        fd = os.open(provider["path"], os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            self._private(before)
            need(before.st_size <= MAX_BYTES, "bounded_scheduler_configuration_required")
            raw = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
        need(
            len(raw) <= MAX_BYTES
            and sha(raw) == provider["sha256"]
            and (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            "scheduler_configuration_changed",
        )
        value = parse(raw)["env"]["GOLDEN_SCHEDULER_DATABASE_URL"]
        need(type(value) is str and 1 <= len(value) <= 8192, "fixed_scheduler_credential_required")
        return value

    def load_operation(self, actor, business_context):
        actor_hash = sha(canonical(actor))
        stored = parse(self._read("operation-bindings", actor_hash + ".json"))
        current = self.derive_operation(stored["job_id"], actor, business_context)
        need(canonical(stored) == canonical(current), "operation_binding_changed_or_foreign")
        return current

    def enter_operation(self, actor, business_context, *, native_identity=None):
        """Durable one-shot entry, never reachable from a source-only binding."""
        binding = self.load_operation(actor, business_context)
        need(
            binding["business_operation_authorized"] is True
            and binding["dispatch_authorized"] is True
            and binding["custody_scope"] == "root_owned_prestart_binding_only",
            "actual_Trial_operation_admission_unavailable",
        )
        need(
            isinstance(native_identity, dict)
            and set(native_identity)
            == {"job_id", "operation_nonce", "request_sha256", "trial_name", "framework_trial_id"}
            and all(
                native_identity[k] == binding[k]
                for k in ("job_id", "operation_nonce", "request_sha256")
            )
            and native_identity["trial_name"] == "anvil-bm-" + binding["operation_nonce"][:20]
            and str(UUID(native_identity["framework_trial_id"]))
            == native_identity["framework_trial_id"],
            "actual_framework_entry_identity_required",
        )
        self._write_once(
            "operation-intents",
            binding["job_id"] + ".json",
            {
                "schema_version": "anvil.fixed-KYC-entry-intent.v1",
                "job_id": binding["job_id"],
                "operation_nonce": binding["operation_nonce"],
                "request_sha256": binding["request_sha256"],
                "binding_sha256": sha(canonical(binding)),
                "entered_at": self._clock().isoformat(),
                "max_callback_invocations": 1,
                "no_replay": True,
                "native_identity": native_identity,
            },
        )
        return binding

    def finish_operation(self, binding, *, trial_id, output_sha256, state):
        need(
            state in ("completed", "unknown")
            and (output_sha256 is None or hash_value(output_sha256)),
            "bounded_operation_outcome_required",
        )
        if trial_id is not None:
            need(str(UUID(trial_id)) == trial_id, "canonical_operation_trial_required")
        intent = parse(self._read("operation-intents", binding["job_id"] + ".json"))
        need(
            intent["binding_sha256"] == sha(canonical(binding)), "operation_intent_binding_changed"
        )
        self._write_once(
            "operation-outcomes",
            binding["job_id"] + ".json",
            {
                "schema_version": "anvil.fixed-KYC-operation-outcome.v1",
                "state": state,
                "job_id": binding["job_id"],
                "trial_id": trial_id,
                "native_identity": intent["native_identity"],
                "output_sha256": output_sha256,
                "no_replay": True,
            },
        )


class TechnicalProbeStore(OperatorProofStore):
    """Permit only a source-bound diagnostic attempt, never predeclare success.

    These records are deliberately disjoint from role/business admissions and
    qualification files. Only the existing QA root operator can use production
    custody. No upload, API payload or environment flag creates a permit here.
    """

    DIRECTORIES = {
        "technical-probe-plans",
        "technical-probe-intents",
        "technical-probe-outcomes",
        "technical-probe-attempts",
        "technical-probe-launches",
        "technical-probe-worker-intents",
    }
    LIMITS = {
        "actions": 2,
        "callback_invocations": 1,
        "model_calls": 0,
        "wall_seconds": 300,
        "lifecycle_seconds": 420,
        "cleanup_seconds": 6,
    }
    ASSETS = {
        "runtime_seal",
        "trial_config",
        "task_package",
        "host_image_custody",
        "recovery_recipe",
        "environment_service",
        "tests_service",
    }
    SCRIPT = [
        {"action": "application.read", "arguments": {}},
        {"action": "documents.list", "arguments": {}},
    ]

    def _qa_custody(self):
        if not (
            os.geteuid() == 0
            and self.owner == 0
            and self.root == ROOT
            and self.scope == "root_owned_prestart_binding_only"
            and os.uname().nodename == "anvil-qa-v1"
        ):
            return False
        physical, opened = self.root.stat(), os.fstat(self.fd)
        self._private(physical, directory=True)
        return (physical.st_dev, physical.st_ino) == (opened.st_dev, opened.st_ino)

    def _directory(self, name):
        if name not in self.DIRECTORIES:
            return super()._directory(name)
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            self._private(os.fstat(fd), directory=True)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def _domain(self):
        # No hostname-only or caller-provided namespace observation.
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        need(str(UUID(boot)) == boot, "probe_boot_identity_required")
        need(
            int(Path("/proc/self/stat").read_text().split(" ", 1)[0]) == os.getpid(),
            "probe_original_proc_visibility_required",
        )
        return {
            "boot_id": boot,
            "pid_namespace": os.readlink("/proc/self/ns/pid"),
            "user_namespace": os.readlink("/proc/self/ns/user"),
        }

    def load_probe(self, job_id):
        need(str(UUID(job_id)) == job_id, "canonical_probe_job_required")
        raw = self._read("technical-probe-plans", job_id + ".json")
        plan = parse(raw)
        need(
            isinstance(plan, dict)
            and set(plan)
            == {
                "schema_version",
                "job_id",
                "operation_nonce",
                "authorization_scope",
                "request_reference",
                "created_at",
                "expires_at",
                "host_domain",
                "request_capsule",
                "dependency_source_sha256s",
                "asset_sha256s",
                "service_projection_sha256s",
                "limits",
            },
            "exact_technical_probe_plan_required",
        )
        need(
            plan["schema_version"] == "anvil.kyc-technical-probe-plan.v1"
            and plan["job_id"] == job_id
            and hash_value(plan["operation_nonce"])
            and plan["authorization_scope"] == "fixed_two_read_software_control_only"
            and type(plan["request_reference"]) is str
            and 1 <= len(plan["request_reference"]) <= 1000,
            "non_spending_operator_probe_scope_required",
        )
        created, expires = (
            datetime.fromisoformat(plan[key]) for key in ("created_at", "expires_at")
        )
        now = self._clock()
        need(
            created.tzinfo is not None
            and expires.tzinfo is not None
            and now.tzinfo is not None
            and created <= now < expires <= min(created + timedelta(minutes=30), STOP),
            "technical_probe_plan_expired_or_future",
        )
        need(plan["host_domain"] == self._domain(), "technical_probe_host_domain_changed")
        need(
            plan["limits"] == self.LIMITS and all(type(v) is int for v in plan["limits"].values()),
            "fixed_technical_probe_caps_required",
        )
        capsule = plan["request_capsule"]
        need(
            type(capsule) is dict and set(capsule) == {"actor", "business_context"},
            "exact_probe_capsule_required",
        )
        actor, context = capsule["actor"], capsule["business_context"]
        validate_business_context(context)
        need(
            context["kind"] == "golden_kyc_software_v1"
            and type(actor) is dict
            and actor.get("paid_calls") is False
            and len(canonical(capsule)) <= 16384
            and context["script_sha256"] == sha(canonical(self.SCRIPT))
            and all(
                actor.get(key) == context[key]
                for key in (
                    "application_id",
                    "environment_version",
                    "snapshot_sha256",
                    "script_sha256",
                )
            ),
            "exact_two_read_probe_request_required",
        )
        self._dependencies(plan["dependency_source_sha256s"])
        need(
            "services/harbor/src/anvil_harbor/operator_proof.py"
            in plan["dependency_source_sha256s"],
            "probe_permission_reader_source_pin_required",
        )
        pins = plan["asset_sha256s"]
        profiles = plan["service_projection_sha256s"]
        need(
            type(pins) is dict
            and set(pins) == self.ASSETS
            and all(hash_value(v) for v in pins.values())
            and type(profiles) is dict
            and set(profiles) == {"environment", "tests"}
            and all(hash_value(v) for v in profiles.values()),
            "complete_probe_asset_pins_required",
        )
        for name, pin in pins.items():
            asset = self._read("operation-assets", pin + ".json")
            need(sha(asset) == pin and type(parse(asset)) is dict, "probe_asset_changed")
            if name in ("environment_service", "tests_service"):
                role = "environment" if name == "environment_service" else "tests"
                need(
                    sha(canonical(parse(asset))) == profiles[role], "probe_role_projection_changed"
                )
        return {
            "schema_version": "anvil.kyc-technical-probe-permission.v1",
            "job_id": job_id,
            "operation_nonce": plan["operation_nonce"],
            "plan_sha256": sha(raw),
            "request_sha256": sha(canonical(capsule)),
            "request_capsule": capsule,
            "asset_sha256s": pins,
            "service_projection_sha256s": profiles,
            "limits": plan["limits"],
            "custody_scope": self.scope,
            "host_domain": plan["host_domain"],
            "expires_at": plan["expires_at"],
            "technical_probe_authorized": self._qa_custody(),
            "qualification_granted": False,
            "business_operation_authorized": False,
            "dispatch_authorized": False,
            "native_trial_qualified": False,
        }

    def _framework_entry(self, permission):
        """Read owner-produced entry and process receipt, never a caller UUID."""
        nonce = permission["operation_nonce"]
        pin = permission["asset_sha256s"]["host_image_custody"]
        host_raw = self._read("operation-assets", pin + ".json")
        need(sha(host_raw) == pin, "probe_host_asset_changed")
        host = parse(host_raw)
        expected = self.root / "technical-probe-attempts" / nonce
        need(host.get("folder") == str(expected), "fixed_probe_attempt_path_required")
        parent = self._directory("technical-probe-attempts")
        try:
            folder = os.open(nonce, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        finally:
            os.close(parent)
        try:
            self._private(os.fstat(folder), directory=True)
            observed = {}
            for name in ("framework-entry.json", "framework-process.json"):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder)
                with os.fdopen(fd, "rb") as stream:
                    before = os.fstat(stream.fileno())
                    self._private(before)
                    raw = stream.read(8193)
                    after = os.fstat(stream.fileno())
                need(
                    len(raw) <= 8192
                    and (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    == (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                    "probe_framework_receipt_changed",
                )
                value = parse(raw)
                need(
                    type(value) is dict and canonical(value) == raw,
                    "canonical_probe_framework_receipt_required",
                )
                observed[name] = (value, sha(raw))
        finally:
            os.close(folder)
        process = observed["framework-process.json"][0]
        timed = host.get("schema_version") in {"anvil.kyc-probe-host.v1", "anvil.kyc-probe-host.v2"}
        need(
            set(process) == ({"pid", "identity", "host_domain", "started_monotonic_ns", "deadline_monotonic_ns"}
                             if timed else {"pid", "identity", "host_domain"})
            and type(process["pid"]) is int
            and process["pid"] > 1
            and process["host_domain"] == permission["host_domain"] == self._domain(),
            "probe_framework_process_domain_changed",
        )
        if timed:
            need(type(process["started_monotonic_ns"]) is int and type(process["deadline_monotonic_ns"]) is int
                 and 0 < process["started_monotonic_ns"] <= time.monotonic_ns() < process["deadline_monotonic_ns"]
                 <= process["started_monotonic_ns"] + host["limits"]["lifecycle_seconds"] * 1000000000,
                 "original_probe_framework_deadline_required")
        proc = Path("/proc") / str(process["pid"])

        def identity():
            need(
                os.readlink(proc / "ns/pid") == permission["host_domain"]["pid_namespace"]
                and os.readlink(proc / "ns/user") == permission["host_domain"]["user_namespace"],
                "probe_framework_kernel_namespace_changed",
            )
            fields = (proc / "stat").read_text().rpartition(") ")[2].split()
            need(
                len(fields) >= 20 and fields[0] != "Z" and proc.stat().st_uid == self.owner,
                "probe_framework_process_not_live",
            )
            return (
                "linux:"
                + permission["host_domain"]["boot_id"]
                + ":"
                + str(process["pid"])
                + ":"
                + fields[19]
            )

        need(identity() == process["identity"], "probe_framework_process_identity_changed")
        python = host["binaries"]["python"]
        need(
            set(python) == {"path", "sha256"}
            and python["path"] == host["python"]
            and (proc / "exe").resolve() == Path(host["python"]).resolve(),
            "probe_framework_interpreter_changed",
        )
        self._sealed_file((proc / "exe").resolve(), python["sha256"])
        with (proc / "cmdline").open("rb") as stream:
            command = stream.read(16385)
        need(
            command
            == b"\0".join(
                str(v).encode()
                for v in (host["python"], *(["-I", "-B"] if host.get("schema_version") in {"anvil.kyc-probe-host.v1", "anvil.kyc-probe-host.v2"} else []),
                          "-m", "anvil_harbor.environment", expected / "trial.json")
            )
            + b"\0",
            "fixed_probe_framework_command_required",
        )
        need(identity() == process["identity"], "probe_framework_process_identity_changed")
        return observed["framework-entry.json"][0], {
            "entry_sha256": observed["framework-entry.json"][1],
            "process_receipt_sha256": observed["framework-process.json"][1],
            "process_identity": process["identity"],
            "host_domain": process["host_domain"],
        }

    def enter_probe(self, job_id):
        """Reserve exactly once before effects; Trial identity must be owner-observed.

        Read the actual persisted entry and physical process observation. This
        ledger alone never starts a Trial or callback.
        """
        permission = self.load_probe(job_id)
        need(
            permission["technical_probe_authorized"] is True,
            "actual_QA_operator_probe_custody_required",
        )
        framework_identity, observed = self._framework_entry(permission)
        need(
            type(framework_identity) is dict
            and set(framework_identity)
            == {"job_id", "operation_nonce", "request_sha256", "trial_name", "framework_trial_id"}
            and all(
                framework_identity[key] == permission[key]
                for key in ("job_id", "operation_nonce", "request_sha256")
            )
            and framework_identity["trial_name"] == "anvil-bm-" + permission["operation_nonce"][:20]
            and str(UUID(framework_identity["framework_trial_id"]))
            == framework_identity["framework_trial_id"],
            "actual_probe_framework_identity_required",
        )
        identity = {
            key: permission[key]
            for key in ("job_id", "operation_nonce", "plan_sha256", "request_sha256")
        }
        need(
            self._clock() < datetime.fromisoformat(permission["expires_at"]),
            "technical_probe_expired_before_entry",
        )
        return self._write_once(
            "technical-probe-intents",
            job_id + ".json",
            identity
            | {
                "schema_version": "anvil.kyc-technical-probe-intent.v1",
                "entered_at": self._clock().isoformat(),
                "framework_identity": framework_identity,
                "framework_observation": observed,
                "custody_scope": self.scope,
                "no_replay": True,
                "model_calls_authorized": 0,
                "qualification_granted": False,
            },
        )

    def reserve_probe_launch(self, job_id):
        permission = self.load_probe(job_id)
        need(permission["technical_probe_authorized"], "actual_QA_operator_probe_custody_required")
        return self._write_once("technical-probe-launches", job_id + ".json", {
            "job_id": job_id, "plan_sha256": permission["plan_sha256"],
            "operation_nonce": permission["operation_nonce"], "no_replay": True,
            "qualification_granted": False,
        })

    def enter_probe_worker(self, job_id):
        permission = self.load_probe(job_id)
        need(permission["technical_probe_authorized"], "actual_QA_operator_probe_custody_required")
        self._framework_entry(permission)
        launch = parse(self._read("technical-probe-launches", job_id + ".json"))
        intent_raw = self._read("technical-probe-intents", job_id + ".json")
        intent = parse(intent_raw)
        need(all(launch.get(key) == permission[key] == intent.get(key)
                 for key in ("job_id", "plan_sha256", "operation_nonce")), "probe_worker_intent_changed")
        return self._write_once("technical-probe-worker-intents", job_id + ".json", {
            "job_id": job_id, "plan_sha256": permission["plan_sha256"],
            "effect_intent_sha256": sha(intent_raw), "no_replay": True,
            "qualification_granted": False,
        })

    def finish_probe(self, job_id, intent_sha256, *, state, evidence_sha256):
        need(
            str(UUID(job_id)) == job_id
            and hash_value(intent_sha256)
            and state in ("observed", "unknown")
            and hash_value(evidence_sha256),
            "bounded_probe_outcome_required",
        )
        intent_raw = self._read("technical-probe-intents", job_id + ".json")
        need(sha(intent_raw) == intent_sha256, "probe_intent_changed")
        intent = parse(intent_raw)
        need(
            set(intent)
            == {
                "schema_version",
                "job_id",
                "operation_nonce",
                "plan_sha256",
                "request_sha256",
                "entered_at",
                "framework_identity",
                "framework_observation",
                "custody_scope",
                "no_replay",
                "model_calls_authorized",
                "qualification_granted",
            }
            and intent["schema_version"] == "anvil.kyc-technical-probe-intent.v1"
            and intent["job_id"] == job_id
            and intent["no_replay"] is True
            and intent["qualification_granted"] is False
            and type(intent["model_calls_authorized"]) is int
            and intent["model_calls_authorized"] == 0,
            "probe_intent_scope_changed",
        )
        # Recording an unknown result remains possible after permit expiry. It
        # cannot grant replacement time, replay the attempt or declare success.
        return self._write_once(
            "technical-probe-outcomes",
            job_id + ".json",
            {
                "schema_version": "anvil.kyc-technical-probe-outcome.v1",
                "job_id": job_id,
                "intent_sha256": intent_sha256,
                "plan_sha256": intent["plan_sha256"],
                "state": state,
                "evidence_sha256": evidence_sha256,
                "no_replay": True,
                "qualification_granted": False,
                "model_calls_authorized": 0,
                "actual_model_calls": None,
                "evidence_reference_verified": False,
                "custody_scope": self.scope,
            },
        )
