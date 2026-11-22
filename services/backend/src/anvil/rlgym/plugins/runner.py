"""The generic verifier plug-in runner (D22): runs any qualified plug-in image with one job on stdin and reads one
result from stdout. It knows nothing about what is inside the image.

- No network (`--network none`). Plug-ins that call a model need a gateway-only network, which is not built yet,
  so they are refused here rather than given a network.
- Read-only root file system (a small `/tmp` only), non-root user, no capabilities, CPU, memory and process limits,
  the manifest's time limit.
- Exit 0: results. Exit 2: bad job, every block `blocked` with the error. Anything else, or the time limit: retried
  once, then every block `blocked`. A missing or malformed result is never a pass.
"""

import json
import subprocess

from anvil.rlgym.common import GymError
from anvil.rlgym.plugins import contract
from anvil.rlgym.runs import images


def docker_args(manifest):
    return [
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:size=16m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "10001:10001",
        "--memory",
        "512m",
        "--cpus",
        "1",
        "--pids-limit",
        "64",
        "--label",
        f"ai.adi-labs.rlgym.plugin={manifest['id']}@{manifest['version']}",
        "--entrypoint",
        manifest["entrypoint"][0],
        image_ref(manifest),
        *manifest["entrypoint"][1:],
    ]


def image_ref(manifest):
    """The pinned image as Docker takes it: a local image id (sha256:…) or name@sha256:digest."""
    return manifest["image"]


def _blocked(job, reason):
    return {
        "schema": contract.RESULT,
        "results": [
            {
                "block_id": b["id"],
                "verdict": "blocked",
                "points": None,
                "expected": None,
                "actual": {"missing": reason},
                "on_fail": b.get("on_fail"),
                "detail": reason,
            }
            for b in job.get("blocks") or []
        ],
    }


def _parse(job, stdout):
    try:
        out = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(out, dict) or out.get("schema") != contract.RESULT:
        return None
    results = out.get("results")
    wanted = {b["id"] for b in job.get("blocks") or []}
    if (
        not isinstance(results, list)
        or {r.get("block_id") for r in results if isinstance(r, dict)} != wanted
    ):
        return None
    if any(r.get("verdict") not in contract.VERDICTS for r in results):
        return None
    return out


def run(manifest, job, invoke=None):
    """→ adi.verifier-result.v1. `invoke(args, input, timeout)` replaces Docker in tests."""
    if manifest.get("calls_model"):
        return _blocked(
            job, "plug-ins that call a model need the gateway network, which is not built yet"
        )
    invoke = invoke or _docker
    payload = json.dumps(job).encode()
    reason = "plug-in failed"
    for _attempt in (1, 2):
        try:
            code, stdout, stderr = invoke(
                docker_args(manifest), payload, manifest["timeout_seconds"]
            )
        except subprocess.TimeoutExpired:
            reason = f"plug-in ran past its {manifest['timeout_seconds']} s limit"
            continue
        if code == 0:
            out = _parse(job, stdout)
            if out:
                return out
            reason = "plug-in wrote no valid result"
            continue
        if code == 2:
            return _blocked(job, "bad job: " + stderr.decode(errors="replace")[-300:].strip())
        reason = f"plug-in exited {code}: " + stderr.decode(errors="replace")[-200:].strip()
    return _blocked(job, reason)


def _docker(args, payload, timeout):
    exe = images.docker()
    if not exe:
        raise GymError("VALIDATION_FAILED", "Docker is not installed on this machine")
    proc = subprocess.run(
        [exe, *args], input=payload, capture_output=True, timeout=timeout + 10, check=False
    )
    return proc.returncode, proc.stdout, proc.stderr
