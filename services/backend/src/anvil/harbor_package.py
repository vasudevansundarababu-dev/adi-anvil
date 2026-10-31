"""Deterministic compiler for the qualified structured-decision-v1 template only."""

import hashlib
import io
import json
import zipfile

from anvil.praxis_contract import PraxisTask, actor_view, grade

HARBOR_VERSION = "0.25.0"
COMPILER_VERSION = "anvil-harbor-structured-v1"
BASE_IMAGE = "python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e"

# Verifier is trusted compiler code, not source task text. No eval, shell interpolation,
# generated imports or arbitrary paths. It is uploaded by Harbor only after actor execution.
GRADER = """import json, math
from pathlib import Path

def matches(b, out):
    if b["field"] not in out: return False
    v = out[b["field"]]
    if b["kind"] == "json_equals": return type(v) is type(b["value"]) and v == b["value"]
    if type(v) not in (int, float) or (type(v) is float and not math.isfinite(v)): return False
    return v >= b["value"] if b["kind"] == "json_number_min" else v <= b["value"]

task = json.loads(Path("/tests/grading.json").read_text())
valid_output = False
try:
    path = Path("/workspace/output.json")
    if path.is_symlink() or path.stat().st_size > 65536: raise ValueError()
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out: raise ValueError()
            out[k] = v
        return out
    out = json.loads(path.read_text(), object_pairs_hook=pairs)
    if not isinstance(out, dict): raise ValueError()
    json.dumps(out, allow_nan=False)
    valid_output = True
    criteria = {c["id"]: {"passed": matches(c["binding"], out), "weight_bps": c["weight_bps"]} for c in task["criteria"]}
    failures = [c["id"] for c in task["constraints"] if not matches(c["binding"], out)]
    hard = [c["id"] for c in task["constraints"] if c["hard_failure"] and c["id"] in failures]
    diagnostic = sum(c["weight_bps"] for c in criteria.values() if c["passed"]) / 10000
    result = {"reward_version":"hard-failure-zero-v1", "reward":0.0 if hard else diagnostic, "diagnostic_score":diagnostic, "criteria":criteria, "constraint_failures":failures, "hard_failures":hard}
except (OSError, ValueError, TypeError, OverflowError, RecursionError):
    result = {"reward_version":"hard-failure-zero-v1", "reward":0.0, "diagnostic_score":None, "criteria":{}, "hard_failures":["invalid_output"]}
Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
Path("/logs/verifier/reward.txt").write_text(str(result["reward"]))
Path("/logs/verifier/diagnostics.json").write_text(json.dumps(result, allow_nan=False))
try:
    p = Path("/workspace/output.json")
    if not p.is_symlink() and p.stat().st_size <= 65536:
        Path("/logs/verifier/output.txt").write_bytes(p.read_bytes())
except OSError:
    pass
"""


def encoded(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def compile_package(raw: bytes):
    from anvil.task_parser import json_value

    if len(raw) > 1024 * 1024:
        raise ValueError("Praxis payload exceeds 1 MiB")
    value = json_value(raw)
    if isinstance(value, dict) and value.get("schema_version") == "praxis.anvil.task.v2":
        from anvil.praxis_staged import PraxisTaskV2

        task = PraxisTaskV2.model_validate(value)
    else:
        task = PraxisTask.model_validate(value)
    reference = grade(task, task.rubric.reference_output)
    if reference["reward"] != 1:
        raise ValueError("Reference example does not satisfy every executable binding")
    source_hash = hashlib.sha256(raw).hexdigest()
    actor = encoded(actor_view(task))
    files = {
        "task.toml": b"""schema_version = "1.4"
[metadata]
origin = "synthetic_reference_verification"
compiler = "anvil-harbor-structured-v1"
[agent]
timeout_sec = 60.0
user = "10001"
[verifier]
timeout_sec = 30.0
user = "root"
[environment]
build_timeout_sec = 180.0
cpus = 1
memory_mb = 512
storage_mb = 1024
network_mode = "no-network"
""",
        "instruction.md": (
            "# Synthetic software verification task\n\n"
            + task.objective
            + "\n\nRead /workspace/task.json. Write /workspace/output.json.\n"
        ).encode(),
        "environment/Dockerfile": (
            f"FROM {BASE_IMAGE}\nWORKDIR /workspace\nCOPY task.json /workspace/task.json\n"
            "RUN useradd --uid 10001 --no-create-home --shell /bin/sh candidate && "
            "chmod 755 /workspace && touch /workspace/output.json && "
            "chown 10001:10001 /workspace/output.json && chmod 600 /workspace/output.json\n"
        ).encode(),
        "environment/task.json": actor,
        "tests/test.sh": b"#!/bin/sh\nset -eu\npython3 /tests/grader.py\n",
        "tests/grader.py": GRADER.encode(),
        "tests/grading.json": encoded(
            {
                "criteria": [c.model_dump() for c in task.rubric.criteria],
                "constraints": [c.model_dump() for c in task.constraints],
            }
        ),
        "solution/solve.sh": (
            "#!/bin/sh\nset -eu\ncat > /workspace/output.json <<'ANVIL_OUTPUT'\n"
            + encoded(task.rubric.reference_output).decode()
            + "\nANVIL_OUTPUT\n"
        ).encode(),
    }
    if task.schema_version == "praxis.anvil.task.v2":
        files = staged_files(task, files)
    negative = negative_check(task)
    if negative:
        files["anvil-checks/constraint-failure.json"] = encoded(negative)
    files["anvil-agent/admission.json"] = encoded(agent_admission(task))
    manifest = {
        "compiler_version": COMPILER_VERSION,
        "harbor_version": HARBOR_VERSION,
        "source_sha256": source_hash,
        "schema_version": task.schema_version,
        "task_id": task.task_id,
        "task_version": task.task_version,
        "revision_id": task.revision_id,
        "binding": task.environment.binding,
        "origin": "synthetic_reference_verification",
        "base_image": BASE_IMAGE,
        "source_review": task.provenance.review.model_dump(),
        "stage_order": [s.id for s in task.stages],
        "constraint_failure_supported": bool(negative),
        "rights": "author_declaration_only; local_PO_software_check_required",
        "files": {p: hashlib.sha256(data).hexdigest() for p, data in sorted(files.items())},
    }
    files["anvil-manifest.json"] = encoded(manifest)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for path, data in sorted(files.items()):
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100600 << 16
            archive.writestr(info, data)
    package = buffer.getvalue()
    return task, manifest, package


def agent_admission(task):
    staged = task.schema_version == "praxis.anvil.task.v2"
    stages = []
    for stage in task.stages:
        if staged:
            actor = {
                "objective": task.objective,
                "stage": {
                    "id": stage.id,
                    "instruction": stage.instruction,
                    "constraints": [
                        {"id": r.id, "description": r.description} for r in stage.constraints
                    ],
                },
                "evidence": [
                    e.model_dump(exclude_none=True)
                    for e in task.evidence
                    if e.id in stage.evidence_ids
                ],
                "deliverables": [d.model_dump() for d in task.deliverables],
            }
            grading = {
                "criteria": [c.model_dump() for c in stage.rubric.criteria],
                "constraints": [r.model_dump() for r in stage.constraints],
            }
            updates = [u.model_dump() for u in stage.state_updates]
        else:
            actor, grading, updates = actor_view(task), None, []
        stages.append(
            {"id": stage.id, "actor": actor, "grading": grading, "state_updates": updates}
        )
    return {
        "schema_version": "anvil.agent-admission.v1",
        "initial_state": task.environment.initial_state,
        "stages": stages,
        "source_schema_version": task.schema_version,
    }


def negative_check(task):
    staged = task.schema_version == "praxis.anvil.task.v2"
    target = task.stages[-1] if staged else task
    for constraint in target.constraints:
        b = constraint.binding
        if constraint.hard_failure and b.kind in ("json_number_min", "json_number_max"):
            output = dict(target.rubric.reference_output)
            output[b.field] = b.value + (1 if b.kind == "json_number_max" else -1)
            if not isinstance(output[b.field], float) or __import__("math").isfinite(
                output[b.field]
            ):
                return {
                    "rule_id": constraint.id,
                    "output": output,
                    "solution_path": f"steps/step-{len(task.stages):02d}/solution/solve.sh"
                    if staged
                    else "solution/solve.sh",
                }
    return None


def apply_check_overlay(task_dir, candidate):
    if candidate != "constraint_failure":
        return None
    data = (task_dir / "anvil-checks/constraint-failure.json").read_bytes()
    negative = json.loads(data)
    # Path comes exclusively from the compiler's fixed template, never an uploaded field.
    path = task_dir / negative["solution_path"]
    if path.name != "solve.sh" or not path.resolve().is_relative_to(task_dir.resolve()):
        raise ValueError("Unsupported negative-check path")
    script = (
        "#!/bin/sh\nset -eu\ncat > /workspace/output.json <<'ANVIL_OUTPUT'\n"
        + encoded(negative["output"]).decode()
        + "\nANVIL_OUTPUT\n"
    ).encode()
    path.write_bytes(script)
    return {
        "kind": "compiler_constraint_failure_v1",
        "rule_id": negative["rule_id"],
        "script_sha256": hashlib.sha256(script).hexdigest(),
        "spec_sha256": hashlib.sha256(data).hexdigest(),
    }


STAGE_FINISH = """
updates = task["state_updates"]
state_path = Path("/workspace/state.json")
if state_path.is_symlink(): raise ValueError("Invalid state path")
state = json.loads(state_path.read_text())
if result["reward"] == 1:
    for update in updates:
        value = out.get(update["from_field"])
        if update["from_field"] not in out or not (value is None or type(value) in (str,int,bool) or (type(value) is float and math.isfinite(value))):
            result["reward"] = 0.0
            result["hard_failures"].append("invalid_state_update")
            break
if task.get("final") and "out" in globals() and isinstance(out, dict):
    final = task["final"]
    final_criteria = {c["id"]:{"passed":matches(c["binding"],out),"weight_bps":c["weight_bps"]} for c in final["criteria"]}
    final_hard = [c["id"] for c in final["constraints"] if c["hard_failure"] and not matches(c["binding"],out)]
    final_score = sum(c["weight_bps"] for c in final_criteria.values() if c["passed"]) / 10000
    final_reward = 0.0 if final_hard else final_score
    result["final_task_diagnostics"] = {"criteria":final_criteria,"hard_failures":final_hard,"diagnostic_score":final_score,"reward":final_reward}
    result["reward"] = min(result["reward"],final_reward)
if result["reward"] == 1:
    state.update({u["key"]: out[u["from_field"]] for u in updates})
    state["completed_stage"] = task["stage_id"]
    state_path.write_text(json.dumps(state, allow_nan=False))
result["stage_id"] = task["stage_id"]
result["state_snapshot"] = state
Path("/logs/verifier/reward.txt").write_text(str(result["reward"]))
Path("/logs/verifier/diagnostics.json").write_text(json.dumps(result, allow_nan=False))
if valid_output: Path("/logs/verifier/output.json").write_text(json.dumps(out, allow_nan=False))
"""


def staged_files(task, files):
    # Only the initial state and actor-visible first-stage material enter the build context.
    config = (
        files["task.toml"]
        .decode()
        .replace("[metadata]", 'multi_step_reward_strategy = "final"\n[metadata]')
    )
    for path in ("tests/test.sh", "tests/grader.py", "tests/grading.json", "solution/solve.sh"):
        files.pop(path)
    files["environment/state.json"] = encoded(task.environment.initial_state)
    files["environment/Dockerfile"] += b"COPY state.json /workspace/state.json\n"
    previous = None
    for i, stage in enumerate(task.stages):
        name = f"step-{i + 1:02d}"
        prefix = f"steps/{name}/"
        config += f'\n[[steps]]\nname = "{name}"\nmin_reward = 1.0\n'
        visible = [
            e.model_dump(exclude_none=True) for e in task.evidence if e.id in stage.evidence_ids
        ]
        observation = {
            "stage_id": stage.id,
            "instruction": stage.instruction,
            "evidence": visible,
            "completion": stage.completion,
            "action_id": stage.action_id,
            "constraints": [{"id": c.id, "description": c.description} for c in stage.constraints],
        }
        files[prefix + "instruction.md"] = (
            stage.instruction
            + "\nRead /workspace/observation.json and /workspace/state.json. Write /workspace/output.json.\n"
        ).encode()
        files[prefix + "workdir/observation.json"] = encoded(observation)
        # Fixed setup; task text never enters shell code. Previous output cannot satisfy this turn.
        setup = "#!/bin/sh\nset -eu\n: > /workspace/output.json\npython3 - <<'ANVIL_PERMISSIONS'\nfrom pathlib import Path\nfor p in (Path('/workspace'), Path('/workspace/state.json')):\n    assert not p.is_symlink() and p.stat().st_uid == 0 and p.stat().st_mode & 0o022 == 0\nANVIL_PERMISSIONS\n"
        if previous:
            setup += (
                "python3 - <<'ANVIL_CHECK'\nimport json\nfrom pathlib import Path\nassert json.loads(Path('/workspace/state.json').read_text()).get('completed_stage') == "
                + repr(previous)
                + "\nANVIL_CHECK\n"
            )
        files[prefix + "workdir/setup.sh"] = setup.encode()
        grading = {
            "stage_id": stage.id,
            "criteria": [c.model_dump() for c in stage.rubric.criteria],
            "constraints": [c.model_dump() for c in stage.constraints],
            "state_updates": [u.model_dump() for u in stage.state_updates],
        }
        if i == len(task.stages) - 1:
            grading["final"] = {
                "criteria": [c.model_dump() for c in task.rubric.criteria],
                "constraints": [c.model_dump() for c in task.constraints],
            }
        files[prefix + "tests/grading.json"] = encoded(grading)
        files[prefix + "tests/grader.py"] = (GRADER + STAGE_FINISH).encode()
        files[prefix + "tests/test.sh"] = b"#!/bin/sh\nset -eu\npython3 /tests/grader.py\n"
        files[prefix + "solution/solve.sh"] = (
            "#!/bin/sh\nset -eu\ncat > /workspace/output.json <<'ANVIL_OUTPUT'\n"
            + encoded(stage.rubric.reference_output).decode()
            + "\nANVIL_OUTPUT\n"
        ).encode()
        previous = stage.id
    files["task.toml"] = config.encode()
    return files


def unpack(package, destination, expected_hash):
    """Extract compiler output only, checking paths and each immutable manifest member."""
    if hashlib.sha256(package).hexdigest() != expected_hash:
        raise ValueError("Package integrity mismatch")
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate package member")
        manifest = json.loads(archive.read("anvil-manifest.json"))
        if set(names) != set(manifest["files"]) | {"anvil-manifest.json"}:
            raise ValueError("Package manifest mismatch")
        for path in names:
            from pathlib import PurePosixPath

            if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
                raise ValueError("Unsafe package path")
            data = archive.read(path)
            if (
                path in manifest["files"]
                and hashlib.sha256(data).hexdigest() != manifest["files"][path]
            ):
                raise ValueError("Package member integrity mismatch")
            target = destination / path
            if target.is_symlink() or not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError("Unsafe existing package destination")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return manifest
