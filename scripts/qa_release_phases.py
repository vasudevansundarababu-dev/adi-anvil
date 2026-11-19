"""Plan three independently resumable QA builds. Never submits or deploys."""
import argparse
import hashlib
import json
import re
from pathlib import Path

PHASES = ("core", "environments", "evaluation")
INPUTS = {
    "core": ("services/backend", "services/harbor", "services/openenv/uv.lock", "integrations/evaluators",
             "contracts", "fixtures", "task-packs", "assets/brand", "apps/web", "package.json", "pnpm-lock.yaml",
             "pnpm-workspace.yaml", ".python-version", "infra/docker/backend.Dockerfile", "infra/docker/web.Dockerfile",
             "infra/docker/marketing-runtime.Dockerfile", "infra/docker/seal-runtime-wheels.py",
             "infra/docker/api-evaluator-node", "runtime-checks/api_installed.py"),
    # Current runtime image contains backend source. Backend/evaluator edits
    # must rebuild it until a separately reviewed image-layer split exists.
    "environments": ("services/backend", "services/harbor", "services/openenv/uv.lock", "integrations/evaluators",
                     "contracts", "infra/docker/marketing-runtime.Dockerfile", "infra/docker/seal-runtime-wheels.py",
                     "runtime-checks/native_installed.py"),
    "evaluation": ("infra/docker/task-runtime-identity.Dockerfile", "runtime-checks"),
}
RETRY = {"read_poll": {"attempts": 4, "delays_seconds": [2, 5, 10], "wall_seconds": 60},
         "digest_pull": {"attempts": 3, "delays_seconds": [2, 5], "wall_seconds": 120},
         "build_submit": {"attempts": 1, "lost_ack": "reconcile operation_token and build_id before any new submission"},
         "effects": {"attempts": 1, "operations": ["migration", "approval", "Trial", "binding_reconcile", "payment"]}}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def inventory(root, phase):
    files = {}
    for name in (*INPUTS[phase], "infra/gcp/cloudbuild.qa-" + phase + ".json", "scripts/qa_release_phases.py", ".dockerignore"):
        path = root / name
        if not path.exists():
            raise ValueError("Missing declared build input: " + name)
        paths = path.rglob("*") if path.is_dir() else [path]
        for item in paths:
            relative = item.relative_to(root)
            if any(part in {".venv", "node_modules", "__pycache__", ".next", ".git", ".local", ".pytest_cache"} for part in relative.parts):
                continue
            if item.name.startswith(".env") or item.suffix == ".tsbuildinfo":
                continue
            if item.is_symlink():
                raise ValueError("Build input symlink must be reviewed: " + str(relative))
            if item.is_file():
                files[str(relative)] = hashlib.sha256(item.read_bytes()).hexdigest()
    return dict(sorted(files.items()))


def plan(root, target, receipts=None, *, source_sha256, source_commit):
    root = root.resolve()
    if (root / ".git").exists():
        raise ValueError("Use a fresh committed git-archive extraction, never a working tree")
    if not re.fullmatch(r"[a-f0-9]{64}", source_sha256) or not re.fullmatch(r"[a-f0-9]{7,40}", source_commit):
        raise ValueError("Actual Golden runtime source hash and Git revision required")
    if set(target) != {"project", "region", "repository"} or any(not re.fullmatch(r"[a-z][a-z0-9-]{1,62}", value) for value in target.values()):
        raise ValueError("Explicit GCP target required")
    receipts = receipts or {}
    if receipts and (receipts.get("schema_version") != "anvil.qa-build-receipts.v1" or receipts.get("target") != target):
        raise ValueError("Prior receipts belong to another target or schema")
    registry = f'{target["region"]}-docker.pkg.dev/{target["project"]}/{target["repository"]}/'
    output = {}
    for phase in PHASES:
        files = inventory(root, phase)
        dependencies = {}
        if phase == "evaluation":
            environment = output["environments"]
            dependencies = {"environment_input_sha256": environment["input_sha256"],
                            "environment_image": environment.get("artifacts", {}).get("task-runtime")}
        fingerprint = digest({"files": files, "target": target, "dependencies": dependencies,
                              "golden_source_sha256": source_sha256})
        token = "qa-" + phase + "-" + digest({"target": target, "input_sha256": fingerprint})[:32]
        previous = receipts.get("phases", {}).get(phase, {})
        expected = {"core": {"backend", "web"}, "environments": {"task-runtime"}, "evaluation": {"kyc-runtime", "marketing-runtime"}}[phase]
        valid = (previous.get("status") == "succeeded" and previous.get("input_sha256") == fingerprint
                 and previous.get("operation_token") == token and previous.get("dependencies") == dependencies
                 and re.fullmatch(r"[a-f0-9-]{36}", previous.get("build_id", ""))
                 and re.fullmatch(r"[a-f0-9]{64}", previous.get("evidence_sha256", ""))
                 and set(previous.get("artifacts", {})) == expected
                 and all(re.fullmatch(re.escape(registry + name) + r"@sha256:[a-f0-9]{64}", image)
                         for name, image in previous.get("artifacts", {}).items()))
        item = {"input_sha256": fingerprint, "operation_token": token, "dependencies": dependencies,
                "input_files": files, "config": "infra/gcp/cloudbuild.qa-" + phase + ".json",
                "action": "reuse" if valid else "prepare_build",
                "substitutions": {"_ARTIFACT_PREFIX": registry, "_RUNTIME_TAG": token,
                                  "_SOURCE_SHA256": source_sha256, "_SOURCE_COMMIT": source_commit}}
        if valid:
            item["artifacts"] = previous["artifacts"]
            item["build_id"] = previous["build_id"]
        elif phase == "evaluation" and not dependencies["environment_image"]:
            item["action"] = "blocked_on_environment_digest"
        if phase == "evaluation" and dependencies["environment_image"]:
            item["substitutions"]["_ENVIRONMENT_IMAGE"] = dependencies["environment_image"]
        item["reconcile_command"] = ["gcloud", "builds", "list", "--project=" + target["project"],
                                     "--region=" + target["region"], "--filter=tags=" + token,
                                     "--limit=10", "--format=json"]
        if previous and not valid:
            item["prior_result"] = "not_reusable; inspect prior build ID before resubmitting any pending/unknown operation"
            if previous.get("status") in {"pending", "unknown", "running"}:
                item["action"] = "reconcile_build_id_before_submit"
        if item["action"] == "prepare_build":
            item["submit_command"] = ["gcloud", "builds", "submit", str(root), "--async",
                "--project=" + target["project"], "--region=" + target["region"], "--config=" + str(root / item["config"]),
                "--substitutions=" + ",".join(key + "=" + value for key, value in item["substitutions"].items())]
        output[phase] = item
    return {"schema_version": "anvil.qa-release-phase-plan.v1", "target": target, "phases": output,
            "build_context": {"root": str(root), "required_origin": "fresh extraction of clean committed git archive",
                              "provenance_verified": False,
                              "operator_requirement": "Verify archive commit/pin and use this exact extraction for planning and submission; no working-tree/private overlay files.",
                              "command_cwd": str(root)},
            "retry_policy": RETRY, "cloud_mutation_performed": False,
            "binding_action": "separate explicit reconcile after exact runtime/source/qualification review; never replay automatically",
            "native_qualified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    for name in ("project", "region", "repository"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--receipts", type=Path)
    parser.add_argument("--receipts-sha256")
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    receipts = None
    if args.receipts:
        raw = args.receipts.read_bytes()
        if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != args.receipts_sha256:
            raise ValueError("Exact independently retained prior receipt pin required")
        receipts = json.loads(raw)
    print(json.dumps(plan(args.root.resolve(), {name: getattr(args, name) for name in ("project", "region", "repository")}, receipts,
                         source_sha256=args.source_sha256, source_commit=args.source_commit), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
