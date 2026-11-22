"""Environment images and instances, built and run locally with Docker.

The image of an environment version is built on this machine from the recipe the Studio stub serves for that version
(Dockerfile, tool server, case seed without reference answers). Every file is checked against the hashes the recipe
states, the base image is pinned by digest and must already be present, and the build has no network. An instance is
one container per run and environment version: no network, read-only root, no capabilities, CPU, memory and process
limits. Each episode is a fresh tool-server process inside it, so writable state never crosses episodes.
"""

import hashlib
import json
import os
import re
import select
import shutil
import subprocess
import time
import uuid

from anvil.config import ROOT
from anvil.rlgym import integrations
from anvil.rlgym.common import GymError

IMAGE_ROOT = ROOT / ".local/rlgym/images"
# python:3.12 (arm64) already present on this machine; override with RLGYM_ENV_BASE_IMAGE (a digest-pinned reference).
DEFAULT_BASE = "python@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e"
SAFE = re.compile(r"[^a-z0-9.-]+")
SERVER = "/app/golden_kyc_env.py"


def base_image():
    value = os.environ.get("RLGYM_ENV_BASE_IMAGE", DEFAULT_BASE)
    if "@sha256:" not in value:
        raise GymError("VALIDATION_FAILED", "RLGYM_ENV_BASE_IMAGE must be pinned by digest")
    return value


def docker():
    return shutil.which("docker")


def _run(args, timeout=120, input_bytes=None):
    exe = docker()
    if not exe:
        raise GymError("VALIDATION_FAILED", "Docker is not installed on this machine")
    return subprocess.run(
        [exe, *args], capture_output=True, timeout=timeout, input=input_bytes, check=False
    )


def docker_status():
    if not docker():
        return False, "Docker is not installed"
    try:
        proc = _run(["info", "--format", "{{.ServerVersion}}"], timeout=15)
    except subprocess.TimeoutExpired:
        return False, "Docker did not answer within 15 s"
    if proc.returncode != 0:
        return False, "Docker is not running"
    return True, f"Docker {proc.stdout.decode().strip()}"


def image_present(ref):
    try:
        return _run(["image", "inspect", "--format", "{{.Id}}", ref], timeout=15).returncode == 0
    except (subprocess.TimeoutExpired, GymError):
        return False


def built(c, vid):
    row = c.execute(
        "SELECT * FROM runs.environment_images WHERE environment_version_id=%s", (vid,)
    ).fetchone()
    if row and image_present(row["local_image_id"]):
        return row
    return None


def build(c, vid):
    """Build (or confirm) the local image of `vid` from the Studio recipe. Returns the environment_images row."""
    env = c.execute("SELECT * FROM catalog.environment_versions WHERE id=%s", (vid,)).fetchone()
    if not env:
        raise GymError("NOT_FOUND", "Environment version not mirrored")
    if env["state"] != "qualified":
        raise GymError("CONFLICT", f"{vid} is {env['state']}; only qualified versions are built")
    existing = built(c, vid)
    if existing:
        return existing
    base = base_image()
    if not image_present(base):
        raise GymError(
            "VALIDATION_FAILED",
            "The pinned base image is not present locally; nothing is pulled from the network",
            {"base_image": base},
        )
    context = integrations.registry_get(f"/versions/{vid}/image-context", timeout=60)
    files = context["files"]
    for name, content in files.items():
        if hashlib.sha256(content.encode()).hexdigest() != context["files_sha256"].get(name):
            raise GymError("HASH_MISMATCH", f"Image recipe file {name} does not match its hash")
    if hashlib.sha256(files["cases.jsonl"].encode()).hexdigest() != context["image_seed_sha256"]:
        raise GymError("HASH_MISMATCH", "Image seed does not match its hash")
    if json.dumps(context["recipe"], sort_keys=True) != json.dumps(
        env["image_recipe"], sort_keys=True
    ):
        raise GymError("HASH_MISMATCH", "Image recipe differs from the registered version")
    expected_cases = (env["case_catalog"] or {}).get("cases")
    if context["cases"] != expected_cases:
        raise GymError("HASH_MISMATCH", "Image seed case count differs from the case catalog")
    for line in files["cases.jsonl"].splitlines():
        if line.strip() and "reference" in json.loads(line):
            raise GymError("VALIDATION_FAILED", "Image seed contains reference answers; refused")
    context_sha = hashlib.sha256(
        json.dumps(context["files_sha256"], sort_keys=True).encode()
    ).hexdigest()
    folder = IMAGE_ROOT / SAFE.sub("-", vid.lower())
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        if name not in ("Dockerfile", "golden_kyc_env.py", "cases.jsonl"):
            raise GymError("VALIDATION_FAILED", f"Unexpected recipe file {name}")
        (folder / name).write_text(content)
    tag = f"rlgym-local/{SAFE.sub('-', env['contract_id'])}:v{env['version']}-{context_sha[:12]}"
    started = time.monotonic()
    proc = _run(
        [
            "build",
            "--quiet",
            "--network",
            "none",
            "--build-arg",
            f"BASE_IMAGE={base}",
            "--label",
            f"ai.adi-labs.rlgym.environment-version={vid}",
            "-t",
            tag,
            str(folder),
        ],
        timeout=600,
    )
    if proc.returncode != 0:
        raise GymError(
            "VALIDATION_FAILED",
            "Docker build of the environment image failed",
            {"stderr": proc.stderr.decode()[-600:]},
        )
    image_id = _run(["image", "inspect", "--format", "{{.Id}}", tag]).stdout.decode().strip()
    ready = _run(["run", "--rm", "--network", "none", "--read-only", image_id, "ready"], timeout=60)
    if ready.returncode != 0 or json.loads(ready.stdout or b"{}").get("cases") != expected_cases:
        raise GymError("VALIDATION_FAILED", "The built image did not report its cases as ready")
    return c.execute(
        """INSERT INTO runs.environment_images(environment_version_id,image_tag,local_image_id,base_image,context_sha256,
             image_seed_sha256,cases,build_seconds) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (environment_version_id) DO UPDATE SET image_tag=EXCLUDED.image_tag,
             local_image_id=EXCLUDED.local_image_id, base_image=EXCLUDED.base_image, context_sha256=EXCLUDED.context_sha256,
             image_seed_sha256=EXCLUDED.image_seed_sha256, cases=EXCLUDED.cases, built_at=now(),
             build_seconds=EXCLUDED.build_seconds RETURNING *""",
        (
            vid,
            tag,
            image_id,
            base,
            context_sha,
            context["image_seed_sha256"],
            context["cases"],
            round(time.monotonic() - started, 2),
        ),
    ).fetchone()


def start_instance(run_id, image_id):
    name = f"rlgym-{run_id}-{uuid.uuid4().hex[:6]}"
    proc = _run(
        [
            "run",
            "-d",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:size=16m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--pids-limit",
            "64",
            "--label",
            f"ai.adi-labs.rlgym.run={run_id}",
            image_id,
            "idle",
        ],
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError("instance_start_failed: " + proc.stderr.decode()[-300:])
    return name


def stop_instance(container):
    try:
        _run(["rm", "-f", container], timeout=60)
    except (subprocess.TimeoutExpired, GymError):
        pass


def instance_alive(container):
    try:
        proc = _run(["inspect", "--format", "{{.State.Running}}", container], timeout=15)
    except (subprocess.TimeoutExpired, GymError):
        return False
    return proc.returncode == 0 and proc.stdout.decode().strip() == "true"


class EnvSession:
    """One episode's tool-server process. JSON lines in, JSON lines out, every read bounded by the episode deadline."""

    def __init__(self, argv, deadline, env=None):
        self.deadline = deadline
        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )

    @classmethod
    def docker(cls, container, deadline):
        return cls([docker(), "exec", "-i", container, "python", SERVER, "session"], deadline)

    def request(self, body):
        if time.monotonic() > self.deadline:
            raise TimeoutError("episode timeout")
        self.proc.stdin.write((json.dumps(body) + "\n").encode())
        self.proc.stdin.flush()
        remaining = self.deadline - time.monotonic()
        ready, _, _ = select.select([self.proc.stdout], [], [], max(remaining, 0))
        if not ready:
            raise TimeoutError("episode timeout")
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("environment_session_closed")
        return json.loads(line)

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
