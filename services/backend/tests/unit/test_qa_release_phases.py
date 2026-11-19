"""Phase plans are local, dependency-aware and cannot authorize cloud effects."""
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def planner(tmp_path):
    source = Path(__file__).resolve().parents[4] / "scripts/qa_release_phases.py"
    spec = importlib.util.spec_from_file_location("phase_planner", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "source"
    names = {name for values in module.INPUTS.values() for name in values} | {".dockerignore", "scripts/qa_release_phases.py"} | {f"infra/gcp/cloudbuild.qa-{phase}.json" for phase in module.PHASES}
    directories = {"services/backend", "services/harbor", "integrations/evaluators", "contracts", "fixtures",
                   "task-packs", "assets/brand", "apps/web", "runtime-checks"}
    for name in sorted(names):
        # Explicit files suffice for the deterministic synthetic inventory.
        path = root / name
        if name in directories:
            path.mkdir(parents=True, exist_ok=True)
            path = path / "synthetic-input"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic " + name)
    target = {"project": "synthetic-project", "region": "us-west1", "repository": "synthetic-repo"}

    def plan(receipts=None, **kw):
        return module.plan(root, target, receipts, source_sha256=kw.get("source_sha256", "a" * 64), source_commit="abcdef1234")

    return module, root, target, plan


def receipts_for(plan, target):
    names = {"core": ["backend", "web"], "environments": ["task-runtime"], "evaluation": ["kyc-runtime", "marketing-runtime"]}
    prefix = f'{target["region"]}-docker.pkg.dev/{target["project"]}/{target["repository"]}/'
    return {"schema_version": "anvil.qa-build-receipts.v1", "target": dict(target), "phases": {
        phase: {key: item[key] for key in ("input_sha256", "dependencies", "operation_token")} | {
            "status": "succeeded", "build_id": str(uuid4()), "evidence_sha256": "c" * 64,
            "artifacts": {name: prefix + name + "@sha256:" + "d" * 64 for name in names[phase]}}
        for phase, item in plan["phases"].items()}}


def completed(planner):
    _, _, target, make = planner
    receipts = receipts_for(make(), target)
    # Evaluation is planned only after the exact environment digest is known.
    next_plan = make(receipts)
    receipts["phases"]["evaluation"] = receipts_for(next_plan, target)["phases"]["evaluation"]
    return receipts


def test_unchanged_reuses_all_and_web_change_reuses_other_two(planner):
    _, root, _, make = planner
    receipts = completed(planner)
    assert all(item["action"] == "reuse" for item in make(receipts)["phases"].values())
    (root / "apps/web/synthetic-input").write_text("changed frontend")
    result = make(receipts)
    assert [result["phases"][p]["action"] for p in ("core", "environments", "evaluation")] == ["prepare_build", "reuse", "reuse"]
    assert result["cloud_mutation_performed"] is False


def test_backend_changes_invalidate_runtime_and_transitively_evaluation(planner):
    _, root, _, make = planner
    receipts = completed(planner)
    (root / "services/backend/synthetic-input").write_text("changed backend packaged in both images")
    result = make(receipts)
    assert result["phases"]["core"]["action"] == "prepare_build"
    assert result["phases"]["environments"]["action"] == "prepare_build"
    assert result["phases"]["evaluation"]["action"] == "blocked_on_environment_digest"


def test_evaluation_only_change_reuses_core_and_environments(planner):
    _, root, _, make = planner
    receipts = completed(planner)
    (root / "infra/docker/task-runtime-identity.Dockerfile").write_text("changed identity metadata")
    result = make(receipts)
    assert [result["phases"][p]["action"] for p in ("core", "environments", "evaluation")] == ["reuse", "reuse", "prepare_build"]


def test_unknown_ack_reconciles_and_wrong_target_or_mutable_tag_cannot_reuse(planner):
    _, _, _, make = planner
    receipts = completed(planner)
    receipts["phases"]["core"]["status"] = "unknown"
    assert make(receipts)["phases"]["core"]["action"] == "reconcile_build_id_before_submit"
    receipts["phases"]["environments"]["artifacts"]["task-runtime"] = "example:latest"
    assert make(receipts)["phases"]["environments"]["action"] == "prepare_build"
    receipts["target"]["project"] = "foreign-project"
    with pytest.raises(ValueError):
        make(receipts)


def test_configs_have_separate_builds_and_immutable_environment_input():
    root = Path(__file__).resolve().parents[4]
    configs = {phase: json.loads((root / f"infra/gcp/cloudbuild.qa-{phase}.json").read_text()) for phase in ("core", "environments", "evaluation")}
    assert "backend-api" in {s["id"] for s in configs["core"]["steps"]}
    assert "native-core" in {s["id"] for s in configs["environments"]["steps"]}
    evaluation = configs["evaluation"]
    assert "sha256:" in evaluation["steps"][0]["args"][-1]
    for step in evaluation["steps"]:
        if step["id"] in {"kyc-identity", "marketing-identity"}:
            assert "TASK_RUNTIME_IMAGE=${_ENVIRONMENT_IMAGE}" in step["args"]
    assert not any("deploy" in json.dumps(value) for value in configs.values())


def test_missing_or_symlinked_input_blocks_and_retry_ceilings_are_explicit(planner):
    module, root, _, make = planner
    assert module.RETRY["read_poll"]["attempts"] == 4
    assert module.RETRY["build_submit"]["attempts"] == module.RETRY["effects"]["attempts"] == 1
    (root / "contracts/synthetic-input").unlink()
    (root / "contracts/synthetic-input").symlink_to(root / "package.json")
    with pytest.raises(ValueError, match="symlink"):
        make()


def test_exact_pull_shell_uses_real_quotes_and_rejects_foreign_target_or_tags():
    root = Path(__file__).resolve().parents[4]
    step = json.loads((root / "infra/gcp/cloudbuild.qa-evaluation.json").read_text())["steps"][0]
    script = step["args"][-1].replace("$$", "$")
    prefix = "us-west1-docker.pkg.dev/synthetic-project/synthetic-repo/"
    valid = prefix + "task-runtime@sha256:" + "a" * 64
    for image, accepted in ((valid, True), (valid.replace("synthetic-project", "foreign-project"), False),
                            (prefix + "task-runtime:latest", False), ('"' + valid + '"', False)):
        result = subprocess.run(["bash", "-ceu", 'timeout(){ shift 2; "$@"; }; docker(){ printf "%s\\n" "$@"; }; ' + script],
                                env={"PATH": os.environ["PATH"], "ENVIRONMENT_IMAGE": image,
                                     "ARTIFACT_PREFIX": prefix}, capture_output=True, timeout=2)
        assert (result.returncode == 0) is accepted
        assert result.stdout.decode() == ("pull\n" + valid + "\n" if accepted else "")


@pytest.mark.parametrize("succeed_at,expected,success", [(2, 2, True), (99, 3, False)])
def test_exact_digest_pull_enforces_retry_attempt_and_delay_ceiling(tmp_path, succeed_at, expected, success):
    root = Path(__file__).resolve().parents[4]
    script = json.loads((root / "infra/gcp/cloudbuild.qa-evaluation.json").read_text())["steps"][0]["args"][-1].replace("$$", "$")
    prefix = "us-west1-docker.pkg.dev/synthetic-project/synthetic-repo/"
    log = tmp_path / "calls"
    stub = '''calls=0
timeout(){ [[ "$1" == --kill-after=2s && "$2" == 35s ]]; shift 2; "$@"; }
sleep(){ printf 'sleep:%s\\n' "$1" >> "$CALL_LOG"; }
docker(){ calls=$((calls+1)); printf 'pull:%s\\n' "$calls" >> "$CALL_LOG"; ((calls >= SUCCEED_AT)); }
'''
    result = subprocess.run(["bash", "-ceu", stub + script], env={"PATH": os.environ["PATH"],
        "ENVIRONMENT_IMAGE": prefix + "task-runtime@sha256:" + "a" * 64, "ARTIFACT_PREFIX": prefix,
        "CALL_LOG": str(log), "SUCCEED_AT": str(succeed_at)}, capture_output=True, timeout=2)
    assert (result.returncode == 0) is success
    lines = log.read_text().splitlines()
    assert [line for line in lines if line.startswith("pull:")] == [f"pull:{i}" for i in range(1, expected + 1)]
    assert [line for line in lines if line.startswith("sleep:")] == (["sleep:2"] if success else ["sleep:2", "sleep:5"])


def test_context_is_archive_only_and_submit_uses_exact_absolute_path(planner):
    _, root, _, make = planner
    result = make()
    assert result["build_context"]["root"] == str(root.resolve())
    assert str(root.resolve()) in result["phases"]["core"]["submit_command"]
    (root / ".git").write_text("gitdir: /synthetic/private-worktree")
    with pytest.raises(ValueError, match="archive"):
        make()
