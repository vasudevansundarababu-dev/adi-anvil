"""Run an evaluator configuration in its framework's sandbox.

Only the locally installed `python` framework can execute here. Other frameworks (ZEN, Promptfoo, Pramaana) are
registered but have no image on this machine, so a configuration on them is refused rather than simulated.
"""

import json
import resource
import subprocess
import sys

from anvil.rlgym.admin.users import PYTHON_RUNNER
from anvil.rlgym.common import GymError


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


def _check(framework):
    if framework["runtime_id"] != "python" or not framework["installed_locally"]:
        raise GymError(
            "VALIDATION_FAILED",
            f"Framework {framework['id']} is not installed in the local scoring sandbox",
            {"framework": framework["id"], "note": framework.get("install_note")},
        )
    if framework["state"] == "revoked":
        raise GymError("VALIDATION_FAILED", f"Framework {framework['id']} is revoked")


def run(framework, config, evidence, reference, timeout=10, extra=None):
    _check(framework)
    out = _invoke(
        {**(extra or {}), "config": config, "evidence": evidence, "reference": reference}, timeout
    )
    return out if isinstance(out, dict) else out[0]


def run_batch(framework, configs, evidence, reference, timeout=20, extras=None):
    """Score several configurations of one framework version over one episode's evidence in one sandbox process.
    `extras` (one dict per configuration) adds the job fields a verifier-blocks configuration needs: blocks, case_id,
    slots, expected_values_from. They stay in the scoring sandbox, like the reference."""
    _check(framework)
    extras = extras or [{} for _ in configs]
    out = _invoke(
        {
            "jobs": [
                {**x, "config": c, "evidence": evidence, "reference": reference}
                for c, x in zip(configs, extras, strict=True)
            ]
        },
        timeout,
    )
    if isinstance(
        out, dict
    ):  # the sandbox itself failed: every configuration is an error, never a pass
        return [out for _ in configs]
    return out


def _invoke(payload, timeout):
    job = json.dumps(payload)
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-S", str(PYTHON_RUNNER)],
            input=job.encode(),
            capture_output=True,
            timeout=timeout,
            env={},
            cwd="/",
            preexec_fn=_limits,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"verdict": "error", "points": None, "detail": ["evaluator timed out"]}
    if proc.returncode != 0:
        return {
            "verdict": "error",
            "points": None,
            "detail": [f"evaluator exited {proc.returncode}"],
        }
    return json.loads(proc.stdout)
