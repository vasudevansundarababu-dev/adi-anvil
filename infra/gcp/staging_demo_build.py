"""Print reviewed-input staging backend/web build recipe. Never submit a build."""

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path

CLI = "/Users/vasudevansundarababu/Documents/Codex/anvil-tools/google-cloud-sdk/bin/gcloud"
CONFIG = "/Users/vasudevansundarababu/Documents/Codex/anvil-tools/cloud-config"
BUILD_IDENTITY = "anvil-staging-build@adi-anvil-mvp-2026.iam.gserviceaccount.com"
REGISTRY = "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-staging-demo"
LIFECYCLE = {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 7}}]}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(value):
    path = Path(value or "")
    if not path.is_absolute() or ".." in path.parts or path == Path("/") or path.resolve() != path:
        raise ValueError("Absolute nonsymlink local input required")
    return path


def local_json(value, expected):
    path = safe_path(value)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid not in {0, os.getuid()}
            or info.st_mode & 0o022
            or info.st_size > 2097152
        ):
            raise ValueError("Owned regular immutable local input required")
        raw = stream.read(2097153)
    if len(raw) > 2097152 or sha(raw) != expected:
        raise ValueError("Local input digest differs from review contract")
    return json.loads(raw)


def validate_local_inputs(contract, context):
    lifecycle = local_json(contract["lifecycle_file"], contract["lifecycle_sha256"])
    if lifecycle != LIFECYCLE:
        raise ValueError("Exactly one unconditional Delete-after7-days lifecycle required")
    native = local_json(contract["source_manifest_file"], contract["source_manifest_sha256"])
    unfiltered = local_json(
        contract["context_inventory_file"], contract["context_inventory_receipt_sha256"]
    )
    upload = local_json(
        contract["upload_inventory_file"], contract["upload_inventory_receipt_sha256"]
    )
    if (
        native.get("git_head") != contract["source_sha"]
        or unfiltered.get("source_sha") != contract["source_sha"]
        or upload.get("source_sha") != contract["source_sha"]
        or unfiltered.get("source_archive_sha256") != contract["source_archive_sha256"]
        or upload.get("source_archive_sha256") != contract["source_archive_sha256"]
    ):
        raise ValueError("Archive/source/native/upload lineage differs")
    before, selected = unfiltered["inventory"], upload["files"]
    if (
        sha(canonical(before)) != contract["build_context_sha256"]
        or unfiltered["context_inventory_sha256"] != contract["build_context_sha256"]
        or upload["unfiltered_context_inventory_sha256"] != contract["build_context_sha256"]
        or sha(canonical(selected)) != contract["upload_inventory_sha256"]
        or upload["upload_inventory_sha256"] != contract["upload_inventory_sha256"]
    ):
        raise ValueError("Filtered upload inventory must be distinct and independently bound")
    if (
        upload.get("status") != "local_upload_inventory_verified_not_uploaded"
        or upload.get("cloud_mutations") is not False
        or any(
            upload.get(key) is not None
            for key in ("cloud_build_id", "gcs_object", "gcs_generation", "uploaded_package_sha256")
        )
    ):
        raise ValueError("Pre-upload receipt must not invent post-upload observations")
    expected = {}
    for row in before:
        relative = row["path"]
        path = Path(relative)
        if (
            path.is_absolute()
            or ".." in path.parts
            or str(path) != relative
            or any(
                part in {".git", ".local", ".data", ".secrets", "node_modules", ".venv"}
                or (part.startswith(".env") and relative != ".env.example")
                or part.endswith((".pem", ".key", ".p12"))
                for part in path.parts
            )
        ):
            raise ValueError("Unreviewed secret/generated source path")
        target = safe_path(str(context / path))
        metadata = target.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or relative in expected
            or metadata.st_size != row["size"]
            or sha(target.read_bytes()) != row["sha256"]
        ):
            raise ValueError("Current context differs from reviewed public source bytes")
        expected[relative] = row
    actual = set()
    for member in context.rglob("*"):
        if member.is_symlink() or not (member.is_dir() or member.is_file()):
            raise ValueError("Context aliases/special files prohibited")
        if member.is_file():
            actual.add(member.relative_to(context).as_posix())
    if (
        actual != set(expected)
        or not {
            "infra/docker/backend.Dockerfile",
            "infra/docker/web.Dockerfile",
            ".gcloudignore",
            ".dockerignore",
        }
        <= actual
    ):
        raise ValueError("Complete current context and ignore/Dockerfile bindings required")
    if (
        len({row["path"] for row in selected}) != len(selected)
        or any(
            expected.get(row["path"]) != row
            or any(part.startswith(".env") for part in Path(row["path"]).parts)
            for row in selected
        )
        or not {"infra/docker/backend.Dockerfile", "infra/docker/web.Dockerfile"}
        <= {row["path"] for row in selected}
    ):
        raise ValueError("Official upload selection must be an exact context subset")
    if not native.get("files") or any(
        path not in expected or expected[path]["sha256"] != value
        for path, value in native["files"].items()
    ):
        raise ValueError("Native-qualified source manifest differs from context")
    return len(before), len(selected)


def recipe(contract):
    required = {
        "project",
        "region",
        "build_identity",
        "registry",
        "source_sha",
        "source_archive_sha256",
        "source_manifest_sha256",
        "build_context_sha256",
        "fresh_context_directory",
        "build_tag",
        "staging_source_bucket",
        "upload_inventory_sha256",
        "source_manifest_file",
        "context_inventory_file",
        "context_inventory_receipt_sha256",
        "upload_inventory_file",
        "upload_inventory_receipt_sha256",
        "lifecycle_file",
        "lifecycle_sha256",
        "build_config_file",
    }
    if not isinstance(contract, dict) or set(contract) != required:
        raise ValueError("Exact separately reviewed build input contract required")
    if contract["project"] != "adi-anvil-mvp-2026" or contract["region"] != "us-west1":
        raise ValueError("Only the separate Anvil staging build target is supported")
    if contract["build_identity"] != BUILD_IDENTITY:
        raise ValueError("Explicit independently scoped staging build identity required")
    if contract["registry"] != REGISTRY:
        raise ValueError("Explicit separate staging registry required")
    if contract["staging_source_bucket"] != "gs://adi-anvil-mvp-2026-anvil-staging-build-source":
        raise ValueError("Explicit isolated staging source bucket required")
    for key, length in (
        ("source_sha", 40),
        *(
            (key, 64)
            for key in (
                "source_archive_sha256",
                "source_manifest_sha256",
                "build_context_sha256",
                "upload_inventory_sha256",
                "context_inventory_receipt_sha256",
                "upload_inventory_receipt_sha256",
                "lifecycle_sha256",
            )
        ),
    ):
        if not re.fullmatch(rf"[a-f0-9]{{{length}}}", contract[key] or ""):
            raise ValueError("Exact source/archive/inventory/context hashes required")
    context = safe_path(contract["fresh_context_directory"])
    info = context.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("Fresh public context must be an owned0700 directory")
    build_config_file = safe_path(contract["build_config_file"])
    counts = validate_local_inputs(contract, context)
    tag = contract["build_tag"]
    if not isinstance(tag, str) or not re.fullmatch(
        re.escape(contract["source_sha"][:12]) + r"-[a-z0-9][a-z0-9-]{0,40}", tag
    ):
        raise ValueError("Unique reviewed build tag must bind the source prefix")
    cloudbuild = {
        "serviceAccount": "projects/adi-anvil-mvp-2026/serviceAccounts/"
        + contract["build_identity"],
        "steps": [
            {
                "id": name,
                "name": "gcr.io/cloud-builders/docker",
                "args": [
                    "build",
                    "--platform=linux/amd64",
                    "--file",
                    f"infra/docker/{name}.Dockerfile",
                    "--label",
                    "org.opencontainers.image.revision=${_SOURCE_SHA}",
                    "--tag",
                    "${_REPO}/" + name + ":${_TAG}",
                    ".",
                ],
                "waitFor": ["-"],
            }
            for name in ("backend", "web")
        ],
        "images": ["${_REPO}/backend:${_TAG}", "${_REPO}/web:${_TAG}"],
        "substitutions": {
            "_REPO": contract["registry"],
            "_TAG": tag,
            "_SOURCE_SHA": contract["source_sha"],
            "_SOURCE_ARCHIVE_SHA256": contract["source_archive_sha256"],
            "_NATIVE_MANIFEST_SHA256": contract["source_manifest_sha256"],
            "_CONTEXT_INVENTORY_SHA256": contract["build_context_sha256"],
            "_UPLOAD_INVENTORY_SHA256": contract["upload_inventory_sha256"],
        },
        "options": {"machineType": "E2_HIGHCPU_8", "logging": "CLOUD_LOGGING_ONLY"},
        "timeout": "2400s",
        "tags": ["anvil-staging-demo", "source-" + contract["source_sha"][:12]],
    }
    base = [
        "env",
        "CLOUDSDK_CONFIG=" + CONFIG,
        "CLOUDSDK_CORE_DISABLE_USAGE_REPORTING=true",
        CLI,
        "--project=adi-anvil-mvp-2026",
        "--account=vasudevan.sundarababu@adi-labs.ai",
    ]
    for step in cloudbuild["steps"]:
        for label, substitution in (
            ("source-archive", "_SOURCE_ARCHIVE_SHA256"),
            ("native-manifest", "_NATIVE_MANIFEST_SHA256"),
            ("context-inventory", "_CONTEXT_INVENTORY_SHA256"),
            ("upload-inventory", "_UPLOAD_INVENTORY_SHA256"),
        ):
            step["args"][-1:-1] = [
                "--label",
                "io.adi.anvil." + label + "-sha256=${" + substitution + "}",
            ]
    config_bytes = (json.dumps(cloudbuild, sort_keys=True, indent=2) + "\n").encode()
    if build_config_file.exists():
        info = build_config_file.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid not in {0, os.getuid()}
            or info.st_nlink != 1
            or info.st_mode & 0o022
            or info.st_size > 65536
        ):
            raise ValueError("Materialized config must be bounded owned regular reviewed input")
    config_verified = build_config_file.is_file() and build_config_file.read_bytes() == config_bytes
    if build_config_file.exists() and not config_verified:
        raise ValueError("Materialized build configuration differs from exact reviewed inputs")
    resources = [
        [
            "artifacts",
            "repositories",
            "create",
            "anvil-staging-demo",
            "--location=us-west1",
            "--repository-format=docker",
            "--immutable-tags",
        ],
        ["iam", "service-accounts", "create", "anvil-staging-build"],
        [
            "storage",
            "buckets",
            "create",
            contract["staging_source_bucket"],
            "--location=us-west1",
            "--uniform-bucket-level-access",
            "--public-access-prevention",
        ],
        [
            "storage",
            "buckets",
            "update",
            contract["staging_source_bucket"],
            "--lifecycle-file=" + contract["lifecycle_file"],
        ],
        [
            "artifacts",
            "repositories",
            "add-iam-policy-binding",
            "anvil-staging-demo",
            "--location=us-west1",
            "--member=serviceAccount:" + BUILD_IDENTITY,
            "--role=roles/artifactregistry.writer",
        ],
        [
            "storage",
            "buckets",
            "add-iam-policy-binding",
            contract["staging_source_bucket"],
            "--member=serviceAccount:" + BUILD_IDENTITY,
            "--role=roles/storage.objectViewer",
        ],
        [
            "projects",
            "add-iam-policy-binding",
            "adi-anvil-mvp-2026",
            "--member=serviceAccount:" + BUILD_IDENTITY,
            "--role=roles/logging.logWriter",
            "--condition=None",
        ],
        [
            "iam",
            "service-accounts",
            "add-iam-policy-binding",
            BUILD_IDENTITY,
            "--member=user:vasudevan.sundarababu@adi-labs.ai",
            "--role=roles/iam.serviceAccountUser",
        ],
    ]
    return {
        "executed": False,
        "build_authorized": False,
        "resource_and_new_builder_IAM_approval_required": True,
        "public_input_bindings": contract,
        "cloudbuild_config_to_review_and_materialize": cloudbuild,
        "local_validation": {
            "unfiltered_files": counts[0],
            "upload_files": counts[1],
            "exact_seven_day_lifecycle": True,
            "build_config_materialized_and_verified": config_verified,
        },
        "prospective_resource_argv": [base + argv for argv in resources]
        if config_verified
        else None,
        "prospective_submit_argv": base
        + [
            "builds",
            "submit",
            str(context),
            "--region=us-west1",
            "--gcs-source-staging-dir=" + contract["staging_source_bucket"] + "/source",
            "--config=" + str(build_config_file),
            "--service-account=projects/adi-anvil-mvp-2026/serviceAccounts/"
            + contract["build_identity"],
        ]
        if config_verified
        else None,
        "proposed_receipt": {
            "source_sha": contract["source_sha"],
            "source_archive_sha256": contract["source_archive_sha256"],
            "native_manifest_sha256": contract["source_manifest_sha256"],
            "unfiltered_context_inventory_sha256": contract["build_context_sha256"],
            "upload_inventory_sha256": contract["upload_inventory_sha256"],
            "build_config_sha256": sha(config_bytes),
            "build_config_canonical_sha256": sha(canonical(cloudbuild)),
            "uploaded_package_sha256": None,
            "gcs_bucket": contract["staging_source_bucket"],
            "gcs_object": None,
            "gcs_generation": None,
            "cloud_build_id": None,
            "output_digests": None,
            "sourceProvenance": None,
        },
        "postbuild_readonly_template": base
        + [
            "builds",
            "describe",
            "ACTUAL_SUCCESSFUL_BUILD_ID_REQUIRED",
            "--region=us-west1",
            "--format=json(id,status,serviceAccount,sourceProvenance,results.images,buildStepImages,substitutions,timing)",
        ],
        "required_prebuild_proofs": [
            "explicit paid-build approval and budget",
            "new scoped build identity and registry IAM reviewed",
            "fresh context hashes verified against approved public archive/inventory",
            "no env credentials private keys private data logs or ignored local state",
            "unique tag absent and immutable-output policy",
            "current mutable base tags and unpinned hatchling limitation reviewed",
        ],
        "required_output_receipt": [
            "actual build ID and status",
            "submitted context/archive/source/inventory hashes",
            "builder and resolved base image digests from actual build provenance",
            "backend and web immutable output digests",
            "actual dependency/build-system versions and provenance",
            "no deployment implied",
        ],
        "not_built": [
            "Harbor legacy image",
            "golden-tools fixture image",
            "native actor image",
            "production application",
        ],
        "limitations": [
            "Current Dockerfiles use mutable base tags and backend unversioned hatchling build dependency",
            "Renderer rehashes local context and reviewed inventory receipts; it does not rerun SDK packaging or prove a future uploaded object/generation",
            "User approval of new build identity/IAM/resource scope, fresh absence/API/org-policy checks and actual build-ID substitution remain required; no command is executed here",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = recipe(json.loads(args.contract.read_text()))
    except (OSError, ValueError, TypeError, KeyError):
        print(
            json.dumps(
                {
                    "executed": False,
                    "build_authorized": False,
                    "error": "Missing or invalid approved staging build inputs; no command executed",
                }
            )
        )
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
