"""Print reviewed-input staging backend/web build recipe. Never submit a build."""
import argparse
import json
from pathlib import Path
import re

CLI = "/Users/vasudevansundarababu/Documents/Codex/anvil-tools/google-cloud-sdk/bin/gcloud"
CONFIG = "/Users/vasudevansundarababu/Documents/Codex/anvil-tools/cloud-config"


def recipe(contract):
    required = {"project", "region", "build_identity", "registry", "source_sha", "source_archive_sha256", "source_manifest_sha256", "build_context_sha256", "fresh_context_directory", "build_tag"}
    if not isinstance(contract, dict) or set(contract) != required:
        raise ValueError("Exact separately reviewed build input contract required")
    if contract["project"] != "adi-anvil-mvp-2026" or contract["region"] != "us-west1":
        raise ValueError("Only the separate Anvil staging build target is supported")
    if not re.fullmatch(r"anvil-staging(?:-demo)?-build@adi-anvil-mvp-2026\.iam\.gserviceaccount\.com", contract["build_identity"] or ""):
        raise ValueError("Explicit independently scoped staging build identity required")
    if contract["registry"] not in {"us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-staging", "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-staging-demo"}:
        raise ValueError("Explicit separate staging registry required")
    for key, length in (("source_sha", 40), ("source_archive_sha256", 64), ("source_manifest_sha256", 64), ("build_context_sha256", 64)):
        if not re.fullmatch(rf"[a-f0-9]{{{length}}}", contract[key] or ""):
            raise ValueError("Exact source/archive/inventory/context hashes required")
    context = Path(contract["fresh_context_directory"] or "")
    if not context.is_absolute() or ".." in context.parts or context == Path("/"):
        raise ValueError("Explicit fresh sanitized context directory required")
    tag = contract["build_tag"]
    if not isinstance(tag, str) or not re.fullmatch(re.escape(contract["source_sha"][:12]) + r"-[a-z0-9][a-z0-9-]{0,40}", tag):
        raise ValueError("Unique reviewed build tag must bind the source prefix")
    cloudbuild = {
        "serviceAccount": "projects/adi-anvil-mvp-2026/serviceAccounts/" + contract["build_identity"],
        "steps": [{"id": name, "name": "gcr.io/cloud-builders/docker", "args": ["build", "--platform=linux/amd64", "--file", f"infra/docker/{name}.Dockerfile", "--label", "org.opencontainers.image.revision=${_SOURCE_SHA}", "--tag", "${_REPO}/" + name + ":${_TAG}", "."], "waitFor": ["-"]} for name in ("backend", "web")],
        "images": ["${_REPO}/backend:${_TAG}", "${_REPO}/web:${_TAG}"],
        "substitutions": {"_REPO": contract["registry"], "_TAG": tag, "_SOURCE_SHA": contract["source_sha"]},
        "options": {"machineType": "E2_HIGHCPU_8", "logging": "CLOUD_LOGGING_ONLY"},
        "timeout": "2400s",
        "tags": ["anvil-staging-demo", "source-" + contract["source_sha"][:12]],
    }
    base = ["env", "CLOUDSDK_CONFIG=" + CONFIG, "CLOUDSDK_CORE_DISABLE_USAGE_REPORTING=true", CLI,
            "--project=adi-anvil-mvp-2026", "--account=vasudevan.sundarababu@adi-labs.ai"]
    return {"executed": False, "build_authorized": False, "requires_separate_paid_build_approval": True,
            "public_input_bindings": contract,
            "cloudbuild_config_to_review_and_materialize": cloudbuild,
            "prospective_submit_argv": base + ["builds", "submit", str(context), "--region=us-west1", "--config=REVIEWED_STAGING_BACKEND_WEB_CONFIG.json", "--service-account=projects/adi-anvil-mvp-2026/serviceAccounts/" + contract["build_identity"]],
            "postbuild_readonly_template": base + ["builds", "describe", "ACTUAL_SUCCESSFUL_BUILD_ID_REQUIRED", "--region=us-west1", "--format=json(id,status,serviceAccount,sourceProvenance,results.images,buildStepImages,substitutions,timing)"],
            "required_prebuild_proofs": ["explicit paid-build approval and budget", "new scoped build identity and registry IAM reviewed", "fresh context hashes verified against approved public archive/inventory", "no env credentials private keys private data logs or ignored local state", "unique tag absent and immutable-output policy", "current mutable base tags and unpinned hatchling limitation reviewed"],
            "required_output_receipt": ["actual build ID and status", "submitted context/archive/source/inventory hashes", "builder and resolved base image digests from actual build provenance", "backend and web immutable output digests", "actual dependency/build-system versions and provenance", "no deployment implied"],
            "not_built": ["Harbor legacy image", "golden-tools fixture image", "native actor image", "production application"],
            "limitations": ["Current Dockerfiles use mutable base tags and backend unversioned hatchling build dependency", "This renderer does not inspect context or prove its hash; actual trusted prebuild validation remains required", "Build config materialization and actual build-ID substitution are manual reviewed steps; placeholder commands must never be executed"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = recipe(json.loads(args.contract.read_text()))
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"executed": False, "build_authorized": False, "error": "Missing or invalid approved staging build inputs; no command executed"}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
