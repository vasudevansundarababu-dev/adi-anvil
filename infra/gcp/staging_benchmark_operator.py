"""Prepare a non-executing fictional benchmark operator recipe. Never runs jobs.

This is not deployment, a queue daemon, a native qualification receipt or a human
approval. Secret values are inspected only for role separation and never emitted.
"""

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from urllib.parse import unquote, urlsplit
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
    for name, required_role in (
        ("ANVIL_DATABASE_URL", "anvil_app"),
        ("ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL", "anvil_benchmark_evaluator"),
    ):
        try:
            url = urlsplit(environ.get(name, ""))
            if (
                url.scheme not in {"postgres", "postgresql"}
                or unquote(url.username or "") != required_role
                or not url.hostname
                or not url.path.strip("/")
            ):
                raise ValueError("role")
        except ValueError:
            blockers.append(name.lower() + "_separate_role_reference_required")
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
        "secret_references_only": ["ANVIL_DATABASE_URL", "ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL"],
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
