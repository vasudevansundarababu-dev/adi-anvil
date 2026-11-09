"""Recipe CLI never executes jobs; explicit post-approval library helper is separate.

This is not deployment, a queue daemon, a native qualification receipt or a human
approval. Secret values are inspected only for role separation and never emitted.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit
from uuid import UUID

OFF = {
    "ANVIL_LIVE_PROVIDERS_ENABLED": "false",
    "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "false",
    "ANVIL_IMPORT_GENERATION_ENABLED": "false",
    "ANVIL_REAL_EMAIL_ENABLED": "false",
    "ANVIL_BENCHMARK_ENABLED": "false",
    "ANVIL_BENCHMARK_EVALUATION_ENABLED": "false",
    "ANVIL_BENCHMARK_OFFLINE_ENABLED": "false",
    "ANVIL_TEST_HARBOR": "0",
}
GATES = [
    "application deployment approval is separate from Linux QA host approval",
    "actual invited identities and three distinct current reviewer assignments",
    "actual signed fictional source and current source-rights evidence review",
    "actual reviewed evaluator registry and exact-source native qualification",
    "independently reviewed complete source manifest, Python 3.12 and frozen lock installations",
    "explicit frozen thresholds, calibration and human result reviews",
    "operator database role and evaluator role verified independently in SQL",
    "dedicated daemon ownership, image digests and network isolation verified",
]
REQUIRED_SOURCE = {
    "services/backend/src/anvil/benchmark_pipeline_worker.py",
    "services/backend/src/anvil/benchmark_offline_worker.py",
    "services/backend/src/anvil/benchmark_qualification.py",
    "services/backend/src/anvil/benchmark_protocol.py",
    "services/harbor/src/anvil_harbor/sme.py",
}


EVALUATOR_LOGIN_ROLES = {"anvil_staging_benchmark_evaluator_login"}
EVALUATOR_ROLE = "anvil_benchmark_evaluator"
OPERATOR_ROOT = Path("/opt/anvil")
MIN_BOOT_FREE_BYTES = 10 * 1024**3


def boot_space_guard(root):
    """Native source, image data and captured outputs live on the reviewed boot device."""
    if root.stat().st_dev != Path("/").stat().st_dev:
        raise RuntimeError("Operator source is not on the reviewed boot-root device")
    if shutil.disk_usage("/").free < MIN_BOOT_FREE_BYTES:
        raise RuntimeError("At least10GiB free boot space required before native admission")


@contextmanager
def exclusive_native_guard(root):
    """Hold one persistent-inode host lock; never replaces product SQL fences."""
    root = _plain_path(root)
    if root != OPERATOR_ROOT:
        raise ValueError("Exact staging operator checkout required")
    parent = _plain_path(str(root / ".local"))
    info = parent.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("Operator lock parent must be owned nonsymlink0700")
    descriptor = os.open(
        parent / "staging-native.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ValueError("Operator lock must be owned single regular0600 file")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = os.read(descriptor, 2)
        if state not in {b"", b"0"}:
            raise RuntimeError(
                "Prior native work is unknown; actual actor-stop evidence and SQL reconciliation required before manual lock reset"
            )
        if state == b"":
            os.write(descriptor, b"0")
            os.fsync(descriptor)
        boot_space_guard(root)
        yield descriptor
    finally:
        # Persistent inode prevents a second process acquiring a replacement lock.
        os.close(descriptor)


def run_guarded_one_shot(argv, environ):
    """Explicit operator API after deployment approval; never called by recipe CLI.

    One qualification operation (its full qualification matrix), or one offline
    trial. Current source rights, SQL reservations, fences and cancellation remain
    product authority. A persistent unknown marker survives wrapper death/timeout;
    it must not be reset without actual actor-stop evidence and SQL reconciliation.
    """
    root = OPERATOR_ROOT
    python = str(root / ".local/backend-venv/bin/python")
    if not isinstance(argv, list) or len(argv) not in {9, 11} or argv[:2] != [python, "-m"]:
        raise ValueError("Fixed one-shot Python module argv required")
    if argv[2] == "anvil.benchmark_pipeline_worker":
        if len(argv) != 9 or argv[3::2] != ["--project", "--operation", "--admin"]:
            raise ValueError("Fixed qualification one-shot required")
    elif argv[2] == "anvil.benchmark_offline_worker":
        if (
            len(argv) != 11
            or argv[3::2] != ["--project", "--run", "--operator", "--max-trials"]
            or argv[-1] != "1"
        ):
            raise ValueError("Exactly one offline trial per staging invocation required")
    else:
        raise ValueError("Unapproved operator module")
    for value in argv[4:9:2]:
        if _uuid(value) != value:
            raise ValueError("Canonical scoped UUIDs required")
    if (
        any(environ.get(key, "false") != "false" for key in tuple(OFF)[:4])
        or environ.get("ANVIL_TEST_HARBOR") != "1"
        or environ.get("ANVIL_BENCHMARK_OFFLINE_ENABLED") != "true"
    ):
        raise ValueError("Explicit offline-only operator environment required")
    if environ.get("ANVIL_ROOT") != str(root) or environ.get(
        "ANVIL_HARBOR_DOCKER_HOST"
    ) != "unix://" + str(root / ".local/benchmark-docker/docker.sock"):
        raise ValueError("Exact separate native daemon and checkout required")
    allowed = set(OFF) | {
        "ANVIL_ROOT",
        "ANVIL_ENV",
        "WEB_ORIGIN",
        "OIDC_ISSUER",
        "ANVIL_SESSION_KEY",
        "ANVIL_FIXTURE_MODE",
        "LANGSMITH_TRACING",
        "ANVIL_SUPPORT_VERTEX_PROJECT",
        "ANVIL_SUPPORT_MODEL",
        "ARTIFACT_ROOT",
        "ANVIL_BENCHMARK_VAULT_ROOT",
        "ANVIL_HARBOR_DOCKER_HOST",
        "DATABASE_URL",
        "ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL",
    }
    if set(environ) - allowed:
        raise ValueError(
            "Native operator cannot inherit unreviewed environment or executable hooks"
        )
    target = _dsn_target(environ.get("DATABASE_URL", ""), "anvil_app")
    evaluator_target = _dsn_target(
        environ.get("ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL", ""),
        "anvil_staging_benchmark_evaluator_login",
        evaluator=True,
    )
    if (
        target != ("127.0.0.1", 5432, "/anvil")
        or evaluator_target != target
        or environ.get("ARTIFACT_ROOT") != str(root / ".data/artifacts")
        or environ.get("ANVIL_BENCHMARK_VAULT_ROOT") != str(root / ".local/benchmark-vault")
        or environ.get("ANVIL_SUPPORT_VERTEX_PROJECT", "")
        or environ.get("ANVIL_SUPPORT_MODEL", "")
        or environ.get("LANGSMITH_TRACING", "false") != "false"
    ):
        raise ValueError("Exact isolated staging data roots, roles and paid-off profile required")
    with exclusive_native_guard(str(root)) as descriptor:
        # No shell, capture or stdout logging; private receipts belong to worker.
        # Mark unknown BEFORE spawning, including wrapper SIGKILL/power loss.
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.write(descriptor, b"1")
        os.fsync(descriptor)
        # File-backed private output avoids unbounded in-memory communicate buffers.
        # The trusted worker's bounded receipt is read only after successful exit.
        with (
            tempfile.TemporaryFile(dir=root / ".local") as stdout,
            tempfile.TemporaryFile(dir=root / ".local") as stderr,
        ):
            try:
                subprocess.run(
                    argv,
                    env={**environ, "PATH": "/usr/bin:/bin"},
                    cwd=str(root),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    timeout=3600,
                    check=True,
                )
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                raise RuntimeError(
                    "Native outcome unknown; descendants are not assumed stopped. Manual actor-stop evidence and SQL reconciliation required; host admission remains blocked"
                ) from None
            if stdout.tell() > 65536 or stderr.tell() > 65536:
                raise RuntimeError(
                    "Unexpected operator receipt; admission remains unknown pending manual reconciliation"
                )
            stdout.seek(0)
            receipt_bytes = stdout.read(65537)
        try:
            if argv[2] == "anvil.benchmark_pipeline_worker":
                terminal = receipt_bytes.decode().strip() in {"passed", "not_claimed"}
            else:
                receipt = json.loads(receipt_bytes)
                terminal = (
                    set(receipt) == {"statuses", "paid_calls"}
                    and receipt["paid_calls"] is False
                    and receipt["statuses"] in [["completed"], ["not_claimed"]]
                )
        except (ValueError, TypeError, UnicodeError):
            terminal = False
        if not terminal:
            raise RuntimeError(
                "Operator did not return a known terminal receipt; admission stays unknown, manual actor-stop evidence and SQL reconciliation required"
            )
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.write(descriptor, b"0")
        os.fsync(descriptor)
        return {
            "status": "known_terminal_one_shot_returned",
            "operation": argv[2],
            "paid_calls": False,
        }


def _dsn_target(value, user, *, evaluator=False):
    url = urlsplit(value)
    if (
        url.scheme not in {"postgres", "postgresql"}
        or unquote(url.username or "") != user
        or not url.hostname
        or not url.path.strip("/")
    ):
        raise ValueError("separate SQL identity required")
    parameters = parse_qsl(url.query, keep_blank_values=True)
    allowed = {"connect_timeout", "application_name", "sslmode", "sslrootcert"} | (
        {"options"} if evaluator else set()
    )
    if len({key for key, _ in parameters}) != len(parameters) or any(
        key not in allowed for key, _ in parameters
    ):
        raise ValueError("unreviewed SQL connection overrides")
    if evaluator and dict(parameters).get("options") != "-c role=" + EVALUATOR_ROLE:
        raise ValueError("exact evaluator role startup option required")
    return url.hostname, url.port or 5432, unquote(url.path)


def _uuid(value):
    return str(UUID(str(value)))


def _hash(value, length):
    if not isinstance(value, str) or not re.fullmatch("[a-f0-9]{" + str(length) + "}", value):
        raise ValueError("invalid immutable digest")
    return value


def _plain_path(value):
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute normalized path required")
    for candidate in [path, *path.parents]:
        if candidate.is_symlink():
            raise ValueError("symlink paths are forbidden")
    return path


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_path(relative):
    if not isinstance(relative, str):
        raise ValueError("manifest path")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or str(path) != relative:
        raise ValueError("manifest path")
    allowed_dotfiles = {
        ".node-version",
        ".python-version",
        ".gitignore",
        ".dockerignore",
        ".editorconfig",
        ".prettierignore",
        ".prettierrc",
    }
    for index, part in enumerate(path.parts):
        if part in {
            "node_modules",
            "credentials",
            "secrets",
            "id_rsa",
            "id_ed25519",
        } or part.endswith((".pem", ".key", ".p12")):
            raise ValueError("secret or generated path")
        if part.startswith(".") and not (
            index == 0
            and (
                relative in allowed_dotfiles
                or (
                    part == ".github"
                    and len(path.parts) >= 3
                    and path.parts[1] == "workflows"
                    and path.suffix in {".yml", ".yaml"}
                )
            )
        ):
            raise ValueError("unreviewed hidden path")
    return path


def prepare(contract, environ=None):
    """Return redacted argv and blockers; no subprocess, network or file writes."""
    environ = os.environ if environ is None else environ
    operation = contract["operation"]
    if operation not in {"qualification", "offlineworker"}:
        raise ValueError("fixed operation required")
    project, operator = _uuid(contract["project"]), _uuid(contract["operator"])
    target = _uuid(contract["target"])
    trials = contract.get("max_trials", 1)
    if (
        type(trials) is not int
        or not 1 <= trials <= 18
        or (operation == "qualification" and trials != 1)
    ):
        raise ValueError("bounded trials required")
    source = _hash(contract["source_sha"], 40)
    locks = contract["lock_sha256"]
    if set(locks) != {"services/backend/uv.lock", "services/harbor/requirements.lock"}:
        raise ValueError("both exact runtime locks required")
    for value in locks.values():
        _hash(value, 64)
    root, vault = _plain_path(contract["checkout"]), _plain_path(contract["vault_root"])
    manifest = _plain_path(contract["source_manifest"])
    manifest_hash = _hash(contract["source_manifest_sha256"], 64)
    blockers = []
    try:
        if _digest(manifest) != manifest_hash:
            raise ValueError("manifest digest")
        inventory = json.loads(manifest.read_text())
        if (
            not {"scope", "git_head", "files"}
            <= set(inventory)
            <= {"scope", "git_head", "files", "uncommitted_manifest_paths", "provenance"}
            or not isinstance(inventory["scope"], str)
            or not inventory["scope"]
            or inventory["git_head"] != source
            or not REQUIRED_SOURCE <= set(inventory["files"])
        ):
            raise ValueError("manifest source")
        provenance = inventory.get("uncommitted_manifest_paths", [])
        if not isinstance(provenance, list) or any(
            path not in inventory["files"] for path in provenance
        ):
            raise ValueError("manifest provenance")
        derivation = inventory.get("provenance")
        if derivation is not None:
            if (
                set(derivation) != {"source_manifest_sha256", "omitted_paths", "omission_reason"}
                or not isinstance(derivation["omitted_paths"], list)
                or not isinstance(derivation["omission_reason"], str)
                or not derivation["omission_reason"]
            ):
                raise ValueError("derived inventory provenance")
            _hash(derivation["source_manifest_sha256"], 64)
            for omitted in derivation["omitted_paths"]:
                _source_path(omitted)
                if omitted in inventory["files"]:
                    raise ValueError("omitted path still present")
        for relative, expected in inventory["files"].items():
            path = _source_path(relative)
            if _digest(_plain_path(str(root / path))) != _hash(expected, 64):
                raise ValueError("source bytes")
        for relative, expected in locks.items():
            if inventory["files"].get(relative) != expected or _digest(root / relative) != expected:
                raise ValueError("runtime lock")
    except (OSError, ValueError, KeyError, TypeError):
        blockers.append("exact_source_manifest_or_runtime_locks_unverified")
    try:
        metadata = vault.stat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.getuid()
        ):
            raise ValueError("vault custody")
    except (OSError, ValueError):
        blockers.append("fresh_owner_only_private_vault_required")
    daemon = root / ".local/benchmark-docker/docker.sock"
    try:
        if not stat.S_ISSOCK(_plain_path(str(daemon)).stat().st_mode):
            raise ValueError("dedicated socket")
    except (OSError, ValueError):
        blockers.append("exact_dedicated_native_daemon_socket_required")
    if any(environ.get(key, "false") != "false" for key in tuple(OFF)[:4]):
        blockers.append("paid_generation_and_email_flags_must_remain_off")
    app_target = None
    try:
        app_target = _dsn_target(environ.get("DATABASE_URL", ""), "anvil_app")
    except ValueError:
        blockers.append("database_url_separate_role_reference_required")
    login_role = contract.get("evaluator_login_role")
    if login_role not in EVALUATOR_LOGIN_ROLES:
        blockers.append("reviewed_dedicated_evaluator_login_role_required")
    try:
        if login_role not in EVALUATOR_LOGIN_ROLES:
            raise ValueError("dedicated wrapper required")
        evaluator_target = _dsn_target(
            environ.get("ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL", ""), login_role, evaluator=True
        )
        if app_target is None or evaluator_target != app_target:
            raise ValueError("same project database target required")
    except ValueError:
        blockers.append("anvil_benchmark_evaluator_database_url_separate_role_reference_required")
    # Syntax does not prove actual LOGIN, membership, SET ROLE or least privilege.
    blockers.append("actual_evaluator_login_membership_and_current_user_sql_proof_required")
    python = str(root / ".local/backend-venv/bin/python")
    if operation == "qualification":
        argv = [
            python,
            "-m",
            "anvil.benchmark_pipeline_worker",
            "--project",
            project,
            "--operation",
            target,
            "--admin",
            operator,
        ]
    else:
        argv = [
            python,
            "-m",
            "anvil.benchmark_offline_worker",
            "--project",
            project,
            "--run",
            target,
            "--operator",
            operator,
            "--max-trials",
            str(trials),
        ]
    return {
        "schema": "anvil.staging.operator.recipe.v1",
        "status": "blocked_preparation" if blockers else "prepared_not_authorized_or_executed",
        "execution_supported": False,
        "separate_operator_execution_guard": {
            "implementation": "staging_benchmark_operator.run_guarded_one_shot",
            "offline_maximum_trials": 1,
            "qualification_operations": 1,
            "exclusive_lock": "/opt/anvil/.local/staging-native.lock",
            "minimum_boot_free_bytes": MIN_BOOT_FREE_BYTES,
            "does_not_replace": "product SQL reservations, lease fences, cancellation or human approvals",
        },
        "source_sha": source,
        "source_manifest_sha256": manifest_hash,
        "argv": argv,
        "cwd": str(root),
        "default_environment": OFF.copy(),
        "explicit_fictional_profile_after_approval": {
            "ANVIL_BENCHMARK_ENABLED": "true",
            "ANVIL_BENCHMARK_EVALUATION_ENABLED": "true",
            "ANVIL_BENCHMARK_OFFLINE_ENABLED": "true",
        },
        "operator_only_environment_after_approval": {
            "ANVIL_TEST_HARBOR": "1",
            "ANVIL_HARBOR_DOCKER_HOST": "unix://" + str(daemon),
            "ANVIL_BENCHMARK_VAULT_ROOT": str(vault),
        },
        "secret_references_only": ["DATABASE_URL", "ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL"],
        "evaluator_sql_contract": {
            "login_role": login_role if login_role in EVALUATOR_LOGIN_ROLES else None,
            "protected_nologin_role": EVALUATOR_ROLE,
            "required_startup_options": "-c role=" + EVALUATOR_ROLE,
            "verify_session_user": login_role if login_role in EVALUATOR_LOGIN_ROLES else None,
            "verify_current_user": EVALUATOR_ROLE,
            "sql_proof_recorded": False,
            "future_separate_deployment_approval": "Create reviewed dedicated LOGIN wrapper/membership only; never ALTER protected evaluator role LOGIN. Verify no superuser, BYPASSRLS, CREATEROLE, CREATEDB or owner memberships before execution.",
        },
        "required_runtime": {
            "backend_python": "3.12 exact reviewed lock installation",
            "harbor_python": str(root / ".local/harbor-venv/bin/python"),
            "native_command": ["sudo", "-n", "/usr/bin/docker"],
            "api_must_not_receive": [
                "evaluator DSN",
                "Docker socket",
                "sudo authority",
                "ANVIL_TEST_HARBOR",
            ],
        },
        "blockers": blockers,
        "unverified_human_and_runtime_gates": GATES,
        "origin": "original_synthetic_software_conformance_not_model_performance",
        "paid_calls": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = prepare(json.loads(args.contract.read_text()))
    except (OSError, ValueError, KeyError, TypeError):
        result = {"status": "invalid_preparation_contract", "execution_supported": False}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
