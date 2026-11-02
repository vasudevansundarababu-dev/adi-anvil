"""Golden source → trusted reference package → real Harbor software rehearsal.

The fixture oracle is not the production generation model. No paid inference or API
activation. Only checked-in synthetic golden files and fixed repo scripts are executed.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

from anvil.harbor_worker import argv, child_environment
from anvil.praxis_executable import actor_view, parse
from anvil.praxis_export import parse_export

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "contracts/praxis/golden-v3"
SUPPORT = ROOT / "fixtures/executable-import"


def evaluator():
    spec = importlib.util.spec_from_file_location(
        "golden_reference", SUPPORT / "reference_evaluator.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evaluate


def contract_checks():
    evaluate = evaluator()
    results = []
    for path in sorted(GOLDEN.glob("*.export.json")):
        raw, envelope = parse_export(path.read_bytes())
        task = parse(raw)
        actor = actor_view(task)
        public = json.dumps(actor, sort_keys=True)
        assert task.evaluation_private.canary not in public
        assert (
            "expected_reward_bps" not in public
            and "observed_calls" not in public
            and '"probe"' not in public
        )
        data = json.loads(next(a.content for a in task.inputs if a.visibility == "actor"))
        reports = []
        for fixture in task.evaluation_private.fixtures:
            actual = evaluate(
                task.domain,
                data,
                fixture.output,
                [call.model_dump() for call in fixture.observed_calls],
            )
            assert actual["reward_bps"] == fixture.expected_reward_bps, (
                task.task_id,
                fixture.id,
                actual,
            )
            assert all(
                actual["checks"].get(key) == expected
                for key, expected in fixture.expected_checks.items()
            ), (task.task_id, fixture.id, actual)
            reports.append(
                {"fixture": fixture.id, "reward_bps": actual["reward_bps"], "passed": True}
            )
        results.append(
            {
                "task_id": task.task_id,
                "source_sha256": envelope.payload_sha256,
                "fixture_results": reports,
                "actor_isolation": "passed",
            }
        )
    assert len(results) == 3
    return results


def package(task, directory, mode):
    """Fixed trusted golden template only; never use this as arbitrary v3 generation."""
    directory.mkdir(parents=True)
    data = json.loads(next(a.content for a in task.inputs if a.visibility == "actor"))
    for name in ("tests", "solution", "environment"):
        (directory / name).mkdir()
    (directory / "task.toml").write_text(
        'schema_version = "1.4"\n[metadata]\norigin = "synthetic_golden_verification"\n[agent]\ntimeout_sec = 45.0\nuser = "10001"\n[verifier]\ntimeout_sec = 30.0\nuser = "root"\n[environment]\ndocker_image = '
        + json.dumps(task.environment.image_reference)
        + '\nbuild_timeout_sec = 60.0\ncpus = 1\nmemory_mb = 256\nstorage_mb = 1024\nnetwork_mode = "no-network"\n'
    )
    (directory / "instruction.md").write_text(
        task.instructions + "\n" + json.dumps(actor_view(task), indent=2)
    )
    (directory / "environment/Dockerfile").write_text(
        "FROM " + task.environment.image_reference + "\n"
    )
    (directory / "tests/test.sh").write_text(
        "#!/bin/sh\nset -eu\npython3 /tests/harbor_verifier.py\n"
    )
    for name in ("reference_evaluator.py", "harbor_verifier.py"):
        (directory / "tests" / name).write_bytes((SUPPORT / name).read_bytes())
    tools = [
        {
            "name": t.id,
            "description": t.description,
            "inputSchema": t.input_schema,
            "outputSchema": t.output_schema,
        }
        for server in task.mcp_servers
        for t in server.tools
    ]
    (directory / "tests/golden.json").write_text(
        json.dumps({"domain": task.domain, "data": data, "tools": tools})
    )
    (directory / "solution/actor_fixture.py").write_bytes(
        (SUPPORT / "actor_fixture.py").read_bytes()
    )
    (directory / "solution/solve.sh").write_text(
        "#!/bin/sh\nset -eu\npython3 /solution/actor_fixture.py "
        + task.domain
        + (" --guard" if mode == "guardrail" else "")
        + "\n"
    )
    return {
        str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def native_checks(report):
    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        raise RuntimeError("Native golden rehearsal requires explicit ANVIL_TEST_HARBOR=1")
    executable = ROOT / ".local/harbor-venv/bin/harbor"
    folder = ROOT / "artifacts/test-runs/golden-v3"
    folder.mkdir(parents=True, exist_ok=True)
    for source, result in zip(sorted(GOLDEN.glob("*.task.json")), report, strict=True):
        task = parse(source.read_bytes())
        with tempfile.TemporaryDirectory(prefix="golden-", dir=folder) as temporary:
            work = Path(temporary)
            home = work / "home"
            home.mkdir()
            env = child_environment(home)
            actual = subprocess.check_output(
                [
                    "docker",
                    "image",
                    "inspect",
                    task.environment.image_reference,
                    "--format",
                    "{{.Id}}",
                ],
                env=env,
                text=True,
            ).strip()
            if actual != task.environment.digest:
                raise RuntimeError("Supplied image digest mismatch; rebuild exports explicitly")
            result["harbor"] = []
            for mode, expected in (("positive", 1), ("empty", 0), ("guardrail", 0)):
                task_dir = work / mode
                bindings = package(task, task_dir, mode)
                outputs = work / (mode + "-results")
                command = argv(
                    executable,
                    task_dir,
                    outputs,
                    "empty_output" if mode == "empty" else "reference",
                )
                completed = subprocess.run(command, env=env, capture_output=True, timeout=120)
                (folder / (task.domain + "-" + mode + ".log")).write_bytes(
                    completed.stdout + completed.stderr
                )
                diagnostics = list(outputs.rglob("diagnostics.json"))
                if completed.returncode or len(diagnostics) != 1:
                    raise RuntimeError(
                        "Harbor fixture failed: "
                        + task.domain
                        + "/"
                        + mode
                        + "; inspect ignored log"
                    )
                observed = json.loads(diagnostics[0].read_text())
                if observed["reward_bps"] != expected * 10000:
                    raise RuntimeError("Unexpected golden Harbor reward")
                result["harbor"].append(
                    {
                        "mode": mode,
                        "reward_bps": observed["reward_bps"],
                        "passed": True,
                        "file_bindings": bindings,
                    }
                )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    report = contract_checks()
    if args.native:
        report = native_checks(report)
    output = ROOT / "artifacts/test-runs/golden-v3-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "origin": "synthetic_software_verification_only",
                "paid_calls": "not_dispatched",
                "tasks": report,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "tasks": len(report),
                "oracle_cases": sum(len(r["fixture_results"]) for r in report),
                "native_trials": sum(len(r.get("harbor", [])) for r in report),
                "report": str(output),
            }
        )
    )
