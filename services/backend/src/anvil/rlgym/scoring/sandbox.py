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


def run(framework, config, evidence, reference, timeout=10):
    if framework["runtime_id"] != "python" or not framework["installed_locally"]:
        raise GymError(
            "VALIDATION_FAILED",
            f"Framework {framework['id']} is not installed in the local scoring sandbox",
            {"framework": framework["id"], "note": framework.get("install_note")},
        )
    if framework["state"] == "revoked":
        raise GymError("VALIDATION_FAILED", f"Framework {framework['id']} is revoked")
    job = json.dumps({"config": config, "evidence": evidence, "reference": reference})
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
