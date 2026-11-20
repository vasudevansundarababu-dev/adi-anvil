"""Exact QA-only eight-service rollout, no migration or paid activation.

Requires an independently accepted candidate component receipt before prepare.
Retains old config/receipt and rolls back each owned service on failed checks.
No template publication, import, policy/data approval or benchmark dispatch.
"""

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/var/lib/anvil-qa-v1")
REVISION = "39cb2d96418fd029f7c87274941b00639d12d87a"
SOURCE = "896b9c2b39b33ff45f75c989a73f11437abe0b00daa0932d0b639c5336a0e088"
MANIFEST_SHA = "509abde53df86b2254b9b13994406196953fabfc40a4ab29de0c44507dcd8dbf"
OLD_CONFIG_SHA = "4d566c5faae44090d296360347729e4ac846ae12e5055aca35cd740ed0f18e84"
OLD_RECEIPT_SHA = "19ece673da61599de0bd74e787c67909e8929df41a3484c072c7442209b80284"
CAPTURE_SHA = "be7bb48642cb448877635a93d4900cd6e586fe3f0685877c142e20104203553a"
TARGET = "8e8d48c90e9aed61044241af255268156386802a1cd3713a9d6f0d3fb318b1ec"
SERVICES = ("api", "worker", "business-worker", "golden-scheduler", "golden-grader", "web",
            "native-coordinator", "private-scoring-coordinator")
OLD_IDS = {
    "api": "ce3628a2e896a83bac90ea842dc25471f7694c147c8ee58d6ab7eb0da20c81f1",
    "worker": "df6bdb25a767d3f9db67a48b98430184f63a57ba957bf4d3969be341cffb6d28",
    "business-worker": "f569dacfa2be9646ca911a4bbdd783957dace4f21ffd2aaad1ce0fe71c8a21e9",
    "golden-scheduler": "3d872dc1df8b90d752d725b7c2c652b0819e492d8916312a7a58e987a989fae5",
    "golden-grader": "291cd5716fbfc749ae31b7cee4852416099e7dd927a32f62d048031436a6d108",
    "web": "5752a6446ee58d1d266de1567282fa3b60b60aaef725da20be6e52fe3f7040e5",
    "native-coordinator": "86fe839c3acc7850ba4c688c3ad6a2fb37869616b0ce55a756072a47f7c647d5",
    "private-scoring-coordinator": "79a68f0d21d865cdbfaf61f394e1d174ee741f5c0f6c9092cba12bf6633e7250",
}
FLAGS = ("ANVIL_LIVE_PROVIDERS_ENABLED", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED",
         "ANVIL_PRAXIS_TEMPLATE_CALLS_ENABLED", "ANVIL_REAL_EMAIL_ENABLED")
INTENT_LABEL = "qualification-39cb2d9"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def replace_sync(source, destination):
    os.replace(source, destination)
    sync_directory(destination.parent)


def exclusive(path, raw, mode=0o600):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode), "wb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)


def owned_kind(info, name, expected_image, old_image):
    """A familiar name or revision alone can never authorize cleanup."""
    labels = info["Config"]["Labels"]
    if (info["Name"] != "/anvil-qa-v1-" + name + "-1"
            or not re.fullmatch(r"[a-f0-9]{64}", info["Id"])
            or labels.get("com.docker.compose.project") != "anvil-qa-v1"
            or labels.get("com.docker.compose.service") != name):
        raise ValueError("Unknown service identity; do not stop or recreate")
    if (info["Id"] == OLD_IDS[name] and info["Config"]["Image"] == old_image
            and labels.get("org.opencontainers.image.revision") == "08d45ff8eeb515561fbcd50916d6a7adb8fca42c"):
        return "old"
    if (info["Id"] != OLD_IDS[name] and info["Config"]["Image"] == expected_image
            and labels.get("org.opencontainers.image.revision") == REVISION
            and labels.get("io.adi.forge.release_intent") == INTENT_LABEL):
        return "candidate"
    raise ValueError("Unknown service ownership; retain and reconcile")


def inspect(identifier):
    return json.loads(subprocess.check_output(["docker", "inspect", identifier], timeout=15))[0]


def schema():
    command = 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -A -t -c "SELECT max(version) FROM anvil.schema_versions; SELECT version_num FROM anvil.alembic_version"'
    value = subprocess.check_output(["docker", "exec", "anvil-qa-v1-postgres-1", "sh", "-c", command], timeout=15).decode().strip().splitlines()
    if value != ["133", "133"]:
        raise ValueError("Exact schema133 and Alembic133 required; never run migrate")
    return value


def quiescent():
    for folder in ("native-control-bridge", "private-grading-bridge"):
        root = ROOT / "runtime-functional" / folder
        for path in root.iterdir():
            if (path.is_dir() and (path / "request.json").exists()
                    and not any((path / name).exists() for name in ("completion.json", "failed.json", "result.json"))):
                raise ValueError("Reconcile owned bridge attempts before rollout")
    command = 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -A -t -c "SELECT (SELECT count(*) FROM banking.commands),(SELECT count(*) FROM banking.execution_jobs)"'
    if subprocess.check_output(["docker", "exec", "anvil-qa-v1-postgres-1", "sh", "-c", command], timeout=15).decode().strip() != "0|0":
        raise ValueError("Explicit reconciliation required for existing banking jobs")


def main(args):
    if os.geteuid() != 0 or os.uname().nodename != "anvil-qa-v1":
        raise ValueError("Existing QA root operator only")
    os.umask(0o077)
    config = ROOT / "config/compose-app.json"
    current = ROOT / "runtime-functional/harbor-proof/component-qualification/current.json"
    candidate = ROOT / "runtime-functional/harbor-proof/component-qualification-candidate39/current.json"
    capture = ROOT / "runtime-functional/capture-database-qualification/current.json"
    release_raw = Path("/tmp/forge-qualification-release-39cb2d9.json").read_bytes()
    if sha(release_raw) != MANIFEST_SHA or sha(config.read_bytes()) != OLD_CONFIG_SHA or sha(current.read_bytes()) != OLD_RECEIPT_SHA:
        raise ValueError("Exact current serving baseline required")
    new_receipt = candidate.read_bytes()
    release, receipt = json.loads(release_raw), json.loads(new_receipt)
    if (release["revision"] != REVISION or release["source_sha256"] != SOURCE
            or sha(new_receipt) != args.receipt_sha256 or sha(capture.read_bytes()) != CAPTURE_SHA
            or receipt.get("qualified") is not True or receipt.get("scope") != "technical_components_only"
            or receipt.get("spending_authority") is not False or receipt.get("human_legal_rights_approval") is not False
            or receipt.get("model_performance") is not False or receipt.get("golden_source_sha256") != SOURCE
            or receipt.get("runtime_image_sha256") != release["images"]["kyc-runtime"].rsplit("sha256:", 1)[1]
            or datetime.fromisoformat(receipt["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc)
            or len(receipt.get("checks", {})) != 14
            or any(item.get("status") != "passed" for item in receipt["checks"].values())):
        raise ValueError("Current exact accepted component/capture qualification required")
    controls = ROOT / "runtime-functional/controls-39cb2d9"
    for name in ("infra/gcp/qa_capture_database_wiring.py", "infra/gcp/qa_native_wiring.py"):
        if sha((controls / name).read_bytes()) != (release["control_files"] | release["operational_files"])[name]:
            raise ValueError("Pinned pure wiring source required")
    sys.path.insert(0, str(controls))
    from infra.gcp.qa_capture_database_wiring import PRIVATE_ENV, apply

    old_raw, old_receipt = config.read_bytes(), current.read_bytes()
    old = json.loads(old_raw)
    new = copy.deepcopy(old)
    expected = {}
    before = {}
    for name in SERVICES:
        info = inspect(OLD_IDS[name])
        if (not info["State"]["Running"] or info["Id"] != OLD_IDS[name] or info["RestartCount"]
                or info["Config"]["Labels"]["com.docker.compose.service"] != name
                or info["Config"]["Labels"]["org.opencontainers.image.revision"] != "08d45ff8eeb515561fbcd50916d6a7adb8fca42c"):
            raise ValueError("Exact actual eight-service baseline required")
        before[name] = info
        image = release["images"]["web" if name == "web" else "backend" if name in ("api", "worker", "business-worker") else "kyc-runtime"]
        expected[name] = image
        service = new["services"][name]
        service["image"] = image
        service.setdefault("labels", {})["io.adi.forge.release_intent"] = INTENT_LABEL
        environment = service.setdefault("environment", {})
        for flag in FLAGS:
            environment[flag] = "false"
        if name != "web":
            environment["ANVIL_RUNTIME_IMAGE_DIGEST"] = release["images"]["kyc-runtime"].rsplit("sha256:", 1)[1]
    new = apply(new, release["images"]["backend"], TARGET)
    schema()
    quiescent()
    backup = ROOT / "backups/qualification-39cb2d9"
    backup.mkdir(mode=0o700)
    sync_directory(backup.parent)
    exclusive(backup / "compose-app.json", old_raw)
    exclusive(backup / "old-component-receipt.json", old_receipt, 0o644)
    private_env = ROOT / "runtime-functional/capture-probe-39cb2d9-v1/capture.private.env"
    env_raw = private_env.read_bytes()
    if len(env_raw.splitlines()) != 1 or not env_raw.startswith(b"DATABASE_URL="):
        raise ValueError("Only the previously qualified private capture DB setting is permitted")
    exclusive(Path(PRIVATE_ENV), env_raw)
    planned = backup / "compose-candidate.json"
    new_raw = json.dumps(new, sort_keys=True).encode()
    exclusive(planned, new_raw)

    def run(phase, command, timeout=180):
        result = subprocess.run(command, capture_output=True, timeout=timeout)
        exclusive(backup / (phase + ".private.stdout"), result.stdout)
        exclusive(backup / (phase + ".private.stderr"), result.stderr)
        if result.returncode:
            raise RuntimeError("QA release command failed; private diagnostics retained")

    for key in ("backend", "web", "kyc-runtime", "marketing-runtime"):
        run("pull-" + key, ["docker", "pull", release["images"][key]])
        image_info = json.loads(subprocess.check_output(["docker", "image", "inspect", release["images"][key]], timeout=15))[0]
        if image_info["Config"]["Labels"]["org.opencontainers.image.revision"] != REVISION:
            raise ValueError("Actual immutable candidate image revision mismatch")
    run("compose-preflight", ["docker", "compose", "-p", "anvil-qa-v1", "-f", str(planned), "config", "--quiet"])
    schema()
    quiescent()
    if sha(config.read_bytes()) != OLD_CONFIG_SHA or sha(current.read_bytes()) != OLD_RECEIPT_SHA:
        raise ValueError("Baseline changed before release intent")
    exclusive(backup / "intent.json", json.dumps({"revision": REVISION, "old_ids": OLD_IDS,
        "old_config_sha256": OLD_CONFIG_SHA, "new_config_sha256": sha(new_raw),
        "old_receipt_sha256": OLD_RECEIPT_SHA, "new_receipt_sha256": args.receipt_sha256,
        "capture_receipt_sha256": CAPTURE_SHA, "schema": 133, "migration_replayed": False}).encode())
    try:
        run("stop-old", ["docker", "stop", "--time", "10", *OLD_IDS.values()], timeout=120)
        if any(inspect(identifier)["State"]["Running"] or inspect(identifier)["State"]["Pid"] for identifier in OLD_IDS.values()):
            raise RuntimeError("Old receipt readers did not stop")
        schema()
        temporary = current.with_name("pending-39cb2d9.json")
        exclusive(temporary, new_receipt, 0o644)
        replace_sync(temporary, current)
        temporary = config.with_name("compose-39cb2d9.json")
        exclusive(temporary, new_raw)
        replace_sync(temporary, config)
        run("up-candidate", ["docker", "compose", "-p", "anvil-qa-v1", "-f", str(config), "up", "-d",
            "--no-deps", "--force-recreate", "--no-build", *SERVICES])
        until = time.monotonic() + 180
        while True:
            try:
                with urllib.request.urlopen("https://anvil-qa.adi-labs.ai/api/v1/health", timeout=5) as response:
                    health = json.load(response)["data"]
                if (health["api"] == "ready" and health["database"] == "ready"
                        and health["live_inference"] == "disabled" and health["harbor_live_dispatch"] == "disabled"):
                    with urllib.request.urlopen("https://anvil-qa.adi-labs.ai/workspace", timeout=5) as response:
                        if response.status != 200:
                            raise ValueError("Workspace unavailable")
                    break
            except (OSError, ValueError, KeyError):
                pass
            if time.monotonic() >= until:
                raise RuntimeError("Candidate API health did not pass")
            time.sleep(2)
        observed = {}
        for name in SERVICES:
            info = inspect("anvil-qa-v1-" + name + "-1")
            if owned_kind(info, name, expected[name], before[name]["Config"]["Image"]) != "candidate":
                raise RuntimeError("Exact owned candidate identity required")
            environment = dict(value.split("=", 1) for value in info["Config"]["Env"])
            if (info["Config"]["Image"] != expected[name] or not info["State"]["Running"]
                    or info["State"]["Pid"] <= 0 or info["RestartCount"]
                    or info["Config"]["Labels"]["org.opencontainers.image.revision"] != REVISION
                    or any(environment.get(flag, "false") != "false" for flag in FLAGS)):
                raise RuntimeError("Actual candidate service identity/state/OFF flags failed")
            if (info["Config"]["User"] != before[name]["Config"]["User"]
                    or info["Path"] != before[name]["Path"] or info["Args"] != before[name]["Args"]):
                raise RuntimeError("Actual runtime user/entrypoint differs from baseline")
            for key in ("ReadonlyRootfs", "NetworkMode", "Privileged", "CapDrop", "CapAdd", "SecurityOpt",
                        "PidMode", "UTSMode", "UsernsMode", "CgroupnsMode", "Memory", "MemorySwap",
                        "NanoCpus", "PidsLimit", "Tmpfs", "RestartPolicy"):
                if info["HostConfig"].get(key) != before[name]["HostConfig"].get(key):
                    raise RuntimeError("Actual security/resource profile differs from baseline")
            def mounts(value):
                return {item["Destination"]: (item["Type"], item["Source"], item["RW"]) for item in value["Mounts"]}
            expected_mounts = mounts(before[name])
            if name == "api":
                expected_mounts.update({
                    "/app/.data/capture-database-trust": ("bind", str(ROOT / "runtime-functional/capture-database-trust"), False),
                    "/app/.data/runtime-qualification/capture-database": ("bind", str(ROOT / "runtime-functional/capture-database-qualification"), False)})
            if mounts(info) != expected_mounts or len(info["Mounts"]) != len(expected_mounts):
                raise RuntimeError("Actual role mount scope differs from exact plan")
            if name != "web":
                native = name not in ("api", "worker", "business-worker")
                python = "/opt/anvil-runtime/bin/python" if native else "/app/services/backend/.venv/bin/python"
                code = ("import json;from anvil.golden_kyc_source import source_hash;"
                        "from anvil.golden_component_qualification import installed;"
                        "assert source_hash()==" + repr(SOURCE) + ";q=installed();"
                        "assert q['ready'] is " + repr(name != "private-scoring-coordinator") + ";")
                if name == "api":
                    code += ("from anvil.marketing_capture_database_target import readiness;"
                             "c=readiness();assert c['ready'] is True and c['connection_probe_performed'] is False;"
                             "assert c['target_sha256']==" + repr(TARGET) + ";"
                             "assert c['qualification']['receipt_sha256']==" + repr(CAPTURE_SHA) + ";")
                if name == "native-coordinator":
                    code += ("from anvil.golden_native_peer import inspect_sdk;from anvil.praxis_generic_contract import digest;"
                             "s=inspect_sdk('unix:///run/docker.sock');"
                             "assert digest(s)==q['evidence']['mediated_sdk_profile_sha256'];")
                code += "print(json.dumps({'source_sha256':source_hash(),'component_ready':q['ready']}))"
                run("installed-" + name, ["docker", "exec", info["Id"], python, "-I", "-B", "-c", code], timeout=60)
            observed[name] = {"id": info["Id"], "image": info["Config"]["Image"], "restarts": info["RestartCount"]}
        schema()
        if sha(current.read_bytes()) != args.receipt_sha256 or sha(config.read_bytes()) != sha(new_raw):
            raise RuntimeError("Activated receipt/config changed")
        exclusive(backup / "rollout-summary.json", json.dumps({"revision": REVISION, "source_sha256": SOURCE,
            "services": observed, "schema": 133, "migration_replayed": False, "health": health,
            "component_receipt_sha256": args.receipt_sha256, "capture_receipt_sha256": CAPTURE_SHA,
            "config_sha256": sha(new_raw), "project_qualification_granted": False}).encode())
        print(json.dumps({"status": "deployed_requires_acceptance", "revision": REVISION,
            "schema": 133, "migration_replayed": False, "services": observed}))
    except BaseException:
        failures, safe = [], []
        for name in SERVICES:
            try:
                info = inspect("anvil-qa-v1-" + name + "-1")
                kind = owned_kind(info, name, expected[name], before[name]["Config"]["Image"])
                if kind == "candidate":
                    exclusive(backup / ("rollback-owned-" + name + ".json"), json.dumps({"id": info["Id"],
                        "project": "anvil-qa-v1", "service": name, "image": expected[name], "intent": INTENT_LABEL}).encode())
                    subprocess.run(["docker", "stop", "--time", "5", info["Id"]], capture_output=True, timeout=15, check=True)
                if inspect(info["Id"])["State"]["Pid"] == 0:
                    safe.append(name)
            except BaseException as error:
                failures.append({"service": name, "phase": "stop-candidate", "error_type": type(error).__name__})
        # A restored old receipt fails closed for any unconfirmed new reader.
        # Restore safe services independently rather than abandoning all API/UI
        # recovery because one coordinator could not be reconciled.
        for path, raw in ((current, old_receipt), (config, old_raw)):
            temporary = path.with_name(path.name + ".rollback-39cb2d9")
            exclusive(temporary, raw, 0o644 if path == current else 0o600)
            replace_sync(temporary, path)
        for name in safe:
            try:
                subprocess.run(["docker", "compose", "-p", "anvil-qa-v1", "-f", str(config), "up", "-d",
                    "--no-deps", "--force-recreate", "--no-build", name], capture_output=True, timeout=120, check=True)
            except BaseException as error:
                failures.append({"service": name, "phase": "restore-old", "error_type": type(error).__name__})
        exclusive(backup / "rollback.json", json.dumps({"failures": failures, "safe_services": safe,
            "old_receipt_restored": sha(current.read_bytes()) == OLD_RECEIPT_SHA,
            "old_config_restored": sha(config.read_bytes()) == OLD_CONFIG_SHA, "migration_replayed": False}).encode())
        raise RuntimeError("Candidate failed; retained rollback evidence requires reconciliation, never replay") from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-sha256", required=True)
    main(parser.parse_args())
