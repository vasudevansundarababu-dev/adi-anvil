"""Studio's own OpenEnv environment image (recipe kind `studio-openenv`, plan decision 1b, Part A).

The RL Gym does not build these images: Studio builds them with the local Docker daemon and the version record names
the image (`image_recipe.image_ref`) and its identity (`image_digest`, the local image id). Nothing is pulled.

- Identity: the image found locally must have exactly the registered id, and the recipe's digest must equal the
  version's immutable `image_digest`; otherwise the run is refused and an environment-defect To do card opens.
- Instance: one container per run, no network, read-only root, no capabilities, the same limits as bridge images.
  The server listens on loopback inside the container; the RL Gym reaches it through one `docker exec -i` bridge per
  episode that forwards JSON lines to it (no port is published).
- Admission: before the run starts, `/readyz` must be ready and report the registered environment key, seed and
  (when the recipe states it) spec hashes.
- Episodes: `/reset` starts each one; every agent action is a `/step` bound to the episode's reset generation. At the
  end the RL Gym reads `/state`, resets once more to make the simulator seal the generation, and keeps Studio's sealed
  evidence hash next to its own transcript as a cross-check.
- Qualification (receipt mode `openenv_http`): identity, then the six RL Gym checks over Studio's routes, in a
  disposable container of the same image.
"""

import hashlib
import json
import re
import time
import uuid

from anvil.rlgym.common import GymError
from anvil.rlgym.runs import images

KIND = "studio-openenv"
MODE = "openenv_http"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
READY_WAIT_S = 90
PATH = re.compile(r"^/[A-Za-z0-9._/-]*$")

# Runs inside the container with its own Python (standard library only). One JSON request per line in, one JSON
# response per line out: {"method", "path", "body"?} -> {"status", "body"} (status 0 when the server is unreachable).
BRIDGE = r"""
import json, sys, urllib.error, urllib.request
base = "http://127.0.0.1:" + sys.argv[1]
for line in sys.stdin:
    q = json.loads(line)
    data = None if q.get("body") is None else json.dumps(q["body"]).encode()
    req = urllib.request.Request(base + q["path"], data=data, method=q["method"],
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=q.get("timeout", 30)) as r:
            raw = r.read()
            out = {"status": r.status, "body": json.loads(raw) if raw else None}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            body = json.loads(raw)
        except ValueError:
            body = {"raw": raw[:500].decode("utf-8", "replace")}
        out = {"status": e.code, "body": body}
    except (urllib.error.URLError, OSError, ValueError) as e:
        out = {"status": 0, "error": type(e).__name__}
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()
"""


def is_openenv(env):
    return bool(env) and (env.get("image_recipe") or {}).get("kind") == KIND


def recipe(env):
    """The validated recipe of a `studio-openenv` version (raises VALIDATION_FAILED or HASH_MISMATCH)."""
    r = dict(env.get("image_recipe") or {})
    missing = [
        k
        for k in ("image_ref", "image_digest", "port", "environment_key", "qualification")
        if not r.get(k)
    ]
    q = r.get("qualification") or {}
    missing += [
        f"qualification.{k}" for k in ("read_operation", "fixtures", "write_call") if not q.get(k)
    ]
    if missing:
        raise GymError(
            "VALIDATION_FAILED", "The studio-openenv recipe is incomplete", {"missing": missing}
        )
    if not DIGEST.match(str(r["image_digest"])):
        raise GymError("VALIDATION_FAILED", "image_digest must be sha256:<64 hex>")
    if r["image_digest"] != env["image_digest"]:
        # The recipe is not covered by the release guard; the version's image_digest is. They must agree.
        raise GymError(
            "HASH_MISMATCH",
            "The recipe's image digest differs from the released version's image_digest",
            {"recipe": r["image_digest"], "version": env["image_digest"]},
        )
    write = q["write_call"]
    if not isinstance(write, dict) or not write.get("operation_id"):
        raise GymError("VALIDATION_FAILED", "qualification.write_call needs an operation_id")
    port = int(r["port"])
    if not 1 <= port <= 65535:
        raise GymError("VALIDATION_FAILED", "port out of range")
    for key in ("health_path", "ready_path"):
        if r.get(key) and not PATH.match(r[key]):
            raise GymError("VALIDATION_FAILED", f"{key} is not a plain path")
    return {
        **r,
        "port": port,
        "health_path": r.get("health_path") or "/healthz",
        "ready_path": r.get("ready_path") or "/readyz",
        "limits": r.get("limits") or {},
    }


def expected_identity(env, rec):
    """What `/readyz` must report. The recipe may state the simulator's own seed and spec hashes; otherwise the
    version's seed hash is compared and the spec hash is not (the version's spec hash is the registry record's)."""
    out = {
        "environment_key": rec["environment_key"],
        "seed_sha256": rec.get("seed_sha256") or env["seed_sha256"],
    }
    if rec.get("spec_sha256"):
        out["spec_sha256"] = rec["spec_sha256"]
    return out


def local_image_id(ref):
    try:
        proc = images._run(["image", "inspect", "--format", "{{.Id}}", ref], timeout=15)
    except Exception:  # Docker missing or slow is reported by the caller as not present
        return None
    return proc.stdout.decode().strip() if proc.returncode == 0 else None


def check_image(env, rec):
    """Returns the local image id, or raises: not present (nothing is pulled), or a different identity."""
    found = local_image_id(rec["image_ref"])
    if not found:
        raise GymError(
            "VALIDATION_FAILED",
            "Studio's image is not present in local Docker; nothing is pulled from the network",
            {"image_ref": rec["image_ref"]},
        )
    if found != rec["image_digest"]:
        raise GymError(
            "HASH_MISMATCH",
            "The local image differs from the registered environment version",
            {"image_digest": {"registered": rec["image_digest"], "observed": found}},
        )
    return found


def resolve(c, vid, env):
    """The environment_images row for a Studio-built image (identity checked every time; nothing is built)."""
    rec = recipe(env)
    image_id = check_image(env, rec)
    context = hashlib.sha256(json.dumps(env["image_recipe"], sort_keys=True).encode()).hexdigest()
    seed = expected_identity(env, rec)["seed_sha256"]
    return c.execute(
        """INSERT INTO runs.environment_images(environment_version_id,image_tag,local_image_id,base_image,context_sha256,
             image_seed_sha256,cases,build_seconds) VALUES(%s,%s,%s,%s,%s,%s,%s,0)
           ON CONFLICT (environment_version_id) DO UPDATE SET image_tag=EXCLUDED.image_tag,
             local_image_id=EXCLUDED.local_image_id, base_image=EXCLUDED.base_image,
             context_sha256=EXCLUDED.context_sha256, image_seed_sha256=EXCLUDED.image_seed_sha256,
             cases=EXCLUDED.cases, built_at=now() RETURNING *""",
        (
            vid,
            rec["image_ref"],
            image_id,
            "studio-built",
            context,
            seed,
            int((env.get("case_catalog") or {}).get("cases") or 0),
        ),
    ).fetchone()


def start_container(label, image_id):
    """A no-network instance running the image's own server (its default entrypoint)."""
    name = f"rlgym-{label}-{uuid.uuid4().hex[:6]}"
    proc = images._run(
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
            f"ai.adi-labs.rlgym.run={label}",
            "-e",
            f"SIMULATOR_INSTANCE_ID={uuid.uuid4()}",
            image_id,
        ],
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError("instance_start_failed: " + proc.stderr.decode()[-300:])
    return name


class Bridge:
    """HTTP to the server inside the container, over one `docker exec -i` JSON-lines bridge."""

    def __init__(self, container, port, deadline, session=None):
        self.session = session or images.EnvSession(
            [images.docker(), "exec", "-i", container, "python", "-u", "-c", BRIDGE, str(port)],
            deadline,
        )

    @property
    def deadline(self):
        return self.session.deadline

    def call(self, method, path, body=None, timeout=30):
        return self.session.request(
            {"method": method, "path": path, "body": body, "timeout": timeout}
        )

    def ok(self, method, path, body=None):
        out = self.call(method, path, body)
        if out.get("status") != 200:
            raise RuntimeError(
                f"environment {method} {path} answered {out.get('status')}: {str(out.get('body'))[:200]}"
            )
        return out["body"]

    def close(self):
        self.session.close()


def wait_ready(bridge, ready_path):
    """Poll readiness until 200 (the server takes a moment to start). Returns the readiness body."""
    last = None
    while time.monotonic() < bridge.deadline:
        last = bridge.call("GET", ready_path, timeout=5)
        if last.get("status") == 200 and (last.get("body") or {}).get("ready"):
            return last["body"]
        time.sleep(0.5)
    raise RuntimeError(f"environment did not report ready: {last}")


def admit(env, rec, readiness):
    """Admission (Studio's runner.admit): the simulator must be the registered one. Returns the mismatches."""
    mismatches = {}
    for key, value in expected_identity(env, rec).items():
        if readiness.get(key) != value:
            mismatches[key] = {"registered": value, "observed": readiness.get(key)}
    return mismatches


def start_instance(run_id, env, image_id):
    """Start the run's instance and admit it. Raises GymError HASH_MISMATCH (refused, differences listed) or
    RuntimeError (infrastructure); the container is removed on any failure."""
    rec = recipe(env)
    container = start_container(run_id, image_id)
    bridge = None
    try:
        bridge = Bridge(container, rec["port"], time.monotonic() + READY_WAIT_S)
        readiness = wait_ready(bridge, rec["ready_path"])
        mismatches = admit(env, rec, readiness)
        if mismatches:
            raise GymError(
                "HASH_MISMATCH",
                "The simulator differs from the registered environment version",
                {"mismatches": mismatches},
            )
        return container, readiness
    except BaseException:
        images.stop_instance(container)
        raise
    finally:
        if bridge:
            bridge.close()


class OpenEnvSession:
    """One episode on a Studio simulator, speaking the runner's session protocol (`reset`, `call`, `state`)."""

    def __init__(self, container, rec, deadline, bridge=None):
        self.rec = rec
        self.bridge = bridge or Bridge(container, rec["port"], deadline)
        self.generation = None
        self.episode = None

    def request(self, body):
        op = body.get("op")
        if op == "reset":
            out = self.bridge.ok("POST", "/reset")
            obs = out.get("observation") or {}
            if not obs.get("ready"):
                return {"ok": False, "error": "environment not ready after reset"}
            self.generation, self.episode = obs.get("reset_generation"), obs.get("episode_id")
            inject = body.get("inject")
            return {
                "ok": True,
                "case_id": body.get("case_id"),
                "reset_generation": self.generation,
                "episode_id": self.episode,
                # Studio's simulator has no injection point; a trust-and-safety prompt reaches the agent with the
                # user message, and the bundle records that placement.
                "user_message": inject["text"] if inject else None,
                "injection": inject and "rlgym_user_message",
            }
        if op == "call":
            out = self.bridge.call(
                "POST",
                "/step",
                {
                    "action": {"operation_id": body["tool"], "arguments": body.get("args") or {}},
                    "reset_generation": self.generation,
                },
            )
            status = out.get("status")
            if status == 200:
                obs = (out.get("body") or {}).get("observation") or {}
                output = obs.get("output")
                return {
                    "ok": obs.get("state") in ("completed", "pending")
                    and (output or {}).get("status") != "denied",
                    "state": obs.get("state"),
                    "output": output,
                    "pending": obs.get("pending"),
                    "sequence": obs.get("sequence"),
                    "done": bool((out.get("body") or {}).get("done")),
                }
            if 400 <= (status or 0) < 500:
                err = out.get("body") or {}
                return {
                    "ok": False,
                    "error": err.get("code") or f"http_{status}",
                    "message": err.get("message"),
                }
            raise RuntimeError(
                f"environment step failed: {status} {out.get('error') or out.get('body')}"
            )
        if op == "state":
            state = self.bridge.ok("GET", "/state")
            sealed = (self.bridge.ok("POST", "/reset").get("info")) or {}
            return {
                "ok": True,
                "driver": KIND,
                **state,
                "studio_sealed": {
                    "generation": sealed.get("sealed_generation"),
                    "sealed_sha256": sealed.get("sealed_sha256"),
                    "tool_events": sealed.get("sealed_tool_events"),
                },
            }
        raise ValueError(f"unknown session op {op}")

    def close(self):
        self.bridge.close()


# --- qualification ------------------------------------------------------------------------------------------

LIKELY_CAUSE = {
    "identity": "the image or simulator differs from the registered version",
    "health": "the environment does not answer its health route",
    "known_fixtures": "the read operation does not list the template's known fixtures",
    "write_state": "the write call did not complete or did not change state",
    "reset": "the reset was refused or did not start a new generation",
    "state_cleared": "the reset does not restore the seed state",
    "pending_cleared": "pending work or writes survive the reset",
}


def _records(output):
    return (output or {}).get("records") or []


def run_checks(bridge, env, rec, readiness_body=None):
    """identity + the six checks. Returns (checks, failure_class). Bridge errors raise (infrastructure)."""
    q = rec["qualification"]
    checks = []

    def check(name, ok, **evidence):
        checks.append({"name": name, "result": "pass" if ok else "fail", "evidence": evidence})
        if not ok:
            checks[-1]["likely_cause"] = LIKELY_CAUSE[name]
        return ok

    ready = readiness_body or wait_ready(bridge, rec["ready_path"])
    mismatches = admit(env, rec, ready)
    if not check(
        "identity", not mismatches, image_digest=rec["image_digest"], mismatches=mismatches
    ):
        return checks, "environment_defect"
    health = bridge.call("GET", rec["health_path"])
    if not check("health", health.get("status") == 200, status=health.get("status")):
        return checks, "environment_defect"
    seed_state = bridge.ok("GET", "/state")["seed_state_sha256"]
    listed = bridge.call(
        "POST", "/step", {"action": {"operation_id": q["read_operation"], "arguments": {}}}
    )
    output = ((listed.get("body") or {}).get("observation") or {}).get("output")
    ids = {v for r in _records(output) for k, v in r.items() if k.endswith("_id") or k == "id"}
    found = [f for f in q["fixtures"] if f in ids]
    if not check(
        "known_fixtures", found == list(q["fixtures"]), expected=q["fixtures"], found=found
    ):
        return checks, "environment_defect"
    wrote = bridge.call("POST", "/step", {"action": dict(q["write_call"])})
    obs = (wrote.get("body") or {}).get("observation") or {}
    dirty = bridge.ok("GET", "/state")
    if not check(
        "write_state",
        wrote.get("status") == 200
        and obs.get("state") == "completed"
        and dirty["state_sha256"] != seed_state,
        status=wrote.get("status"),
        state=obs.get("state"),
        writes=dirty.get("writes"),
    ):
        return checks, "environment_defect"
    before = dirty["reset_generation"]
    reset = bridge.call("POST", "/reset")
    after = bridge.ok("GET", "/state")
    if not check(
        "reset",
        reset.get("status") == 200 and after["reset_generation"] == before + 1,
        status=reset.get("status"),
        generation={"before": before, "after": after["reset_generation"]},
        sealed_sha256=((reset.get("body") or {}).get("info") or {}).get("sealed_sha256"),
    ):
        return checks, "environment_defect"
    if not check(
        "state_cleared",
        after["state_sha256"] == after["seed_state_sha256"] == seed_state,
        state_sha256=after["state_sha256"],
        seed_state_sha256=seed_state,
    ):
        return checks, "environment_defect"
    check(
        "pending_cleared",
        after["pending"] == 0 and after["writes"] == 0,
        pending=after["pending"],
        writes=after["writes"],
    )
    return checks, (None if checks[-1]["result"] == "pass" else "environment_defect")


def qualify(env):
    """Qualify a `studio-openenv` version in a disposable container. Returns (checks, failure_class); raises
    RuntimeError or OSError on infrastructure failures (the caller retries once)."""
    try:
        rec = recipe(env)
        image_id = check_image(env, rec)
    except GymError as exc:
        defect = exc.code == "HASH_MISMATCH"
        return [
            {
                "name": "identity",
                "result": "fail",
                "evidence": {"error": exc.message, **(exc.details or {})},
                "likely_cause": LIKELY_CAUSE["identity"]
                if defect
                else "Studio's image is not in local Docker or the recipe is incomplete",
            }
        ], ("environment_defect" if defect else "infrastructure")
    container = start_container(f"qual-{images.SAFE.sub('-', env['id'].lower())[:24]}", image_id)
    bridge = None
    try:
        bridge = Bridge(container, rec["port"], time.monotonic() + READY_WAIT_S)
        return run_checks(bridge, env, rec)
    finally:
        if bridge:
            bridge.close()
        images.stop_instance(container)
