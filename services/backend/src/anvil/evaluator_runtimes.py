"""Operator-provisioned isolated library runtimes; requests never choose programs."""

import json
import os
import subprocess
import tempfile

from anvil.config import ROOT
from anvil.policy_rules import Rule, evaluate

VERSIONS = {"nemo": "0.24.1", "promptfoo": "0.125.1"}


def runtime_version(adapter):
    if adapter == "opa-local":
        import hashlib
        from pathlib import Path

        binary = Path(os.environ["ANVIL_OPA_BINARY"])
        if (
            binary.is_symlink()
            or binary.stat().st_mode & 0o022
            or hashlib.sha256(binary.read_bytes()).hexdigest() != os.environ["ANVIL_OPA_SHA256"]
        ):
            raise ValueError("Unqualified OPA binary")
        result = subprocess.run(
            [str(binary), "version"], capture_output=True, timeout=5, env={"PATH": "/usr/bin:/bin"}
        )
        if result.returncode or not result.stdout.startswith(b"Version: 1.22.2\n"):
            raise ValueError("Incompatible OPA binary")
        return "1.22.2"
    if adapter == "nemo":
        result = subprocess.run(
            [
                os.environ["ANVIL_NEMO_PYTHON"],
                "-I",
                "-c",
                "from importlib.metadata import version; print(version('nemoguardrails'))",
            ],
            capture_output=True,
            timeout=5,
            env={"PATH": "/usr/bin:/bin"},
        )
        if result.returncode:
            raise ValueError("NeMo package unavailable")
        value = result.stdout.decode().strip()
    elif adapter == "promptfoo":
        value = json.loads(
            (
                ROOT / "integrations/evaluators/promptfoo/node_modules/promptfoo/package.json"
            ).read_text()
        )["version"]
        if not os.path.isfile(os.environ["ANVIL_EVALUATOR_NODE"]):
            raise ValueError("Node runtime unavailable")
    else:
        raise ValueError("Unsupported library runtime")
    if value != VERSIONS[adapter]:
        raise ValueError("Incompatible library version")
    return value


def evaluate_library(adapter: str, rule: Rule, facts: dict):
    preflight = evaluate(rule, facts)
    if preflight["outcome"] == "unknown":
        return preflight
    if adapter == "nemo":
        if rule.kind != "forbidden_text":
            raise ValueError("NeMo adapter supports deterministic forbidden literals only")
        command = [
            os.environ["ANVIL_NEMO_PYTHON"],
            str(ROOT / "integrations/evaluators/local_worker.py"),
            "nemo",
        ]
        payload = {"text": facts[rule.field], "forbidden_literals": [rule.value]}
    elif adapter == "promptfoo":
        if rule.kind not in {"forbidden_text", "equals"} or not isinstance(rule.value, str):
            raise ValueError("Promptfoo adapter supports bounded literal assertions only")
        if not isinstance(facts[rule.field], str):
            return {"outcome": "unknown", "reason": "Captured text is not a string"}
        command = [
            os.environ["ANVIL_EVALUATOR_NODE"],
            str(ROOT / "integrations/evaluators/promptfoo/worker.mjs"),
        ]
        payload = {
            "output": facts[rule.field],
            "expected": rule.value,
            "kind": "not-contains" if rule.kind == "forbidden_text" else "equals",
        }
    else:
        raise ValueError("Unsupported installed library adapter")
    raw = json.dumps(payload, allow_nan=False).encode()
    if len(raw) > 65536:
        raise ValueError("Library evidence exceeds bound")
    with tempfile.TemporaryDirectory(prefix="anvil-evaluator-") as directory:
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": directory,
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PROMPTFOO_CONFIG_DIR": directory,
            "PROMPTFOO_DISABLE_TELEMETRY": "1",
            "PROMPTFOO_DISABLE_UPDATE": "1",
            "PROMPTFOO_SAFE_MODE": "true",
        }
        result = subprocess.run(
            command, input=raw, capture_output=True, timeout=15, cwd=directory, env=env
        )
    if result.returncode or len(result.stdout) > 65536:
        raise ValueError("Isolated library runtime failed")
    value = json.loads(result.stdout)
    if (
        value.get("outcome") not in {"pass", "fail", "unknown"}
        or value.get("runtime_version") != VERSIONS[adapter]
        or value.get("provider_calls") != 0
    ):
        raise ValueError("Library runtime version/result mismatch")
    return {"outcome": value["outcome"], "reason": "Deterministic upstream library check"}
