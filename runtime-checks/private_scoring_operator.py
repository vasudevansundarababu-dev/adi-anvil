"""QA root operator: fresh isolated private queue→executor controls, never retry.

Run from an exact committed release bundle; no source overlays. All generated
credentials stay in private files. No serving database/approval is modified.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import time
from pathlib import Path

PG = "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/core-postgres-security@sha256:2bb3e2ab0cea85749f75dd2751ae015075274e89fb3c04736c64d932693927a2"


def private(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def main(manifest_path, bundle):
    if os.geteuid() != 0 or os.uname().nodename != "anvil-qa-v1":
        raise ValueError("Existing QA root operator only")
    manifest = json.loads(Path(manifest_path).read_bytes())
    required = {"runtime-checks/kyc_sql_fixture_setup.py", "runtime-checks/private_scoring_fixture.py",
        "runtime-checks/private_scoring_controls.py", "runtime-checks/private_scoring_operator.py",
        "runtime-checks/native_transport_operator.py", "fixtures/private-scoring-control/arithmetic.py",
        "fixtures/private-scoring-control/cases.json", "fixtures/private-scoring-control/technical-review.json"}
    if set(manifest.get("control_files", {})) != required:
        raise ValueError("Exact committed control inventory required")
    for name, expected in manifest["control_files"].items():
        path = bundle / name
        info = path.lstat()
        if path.resolve() != path or info.st_uid != 0 or info.st_mode & 0o022 or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Root-owned release control bytes changed")
    image = manifest["images"]["kyc-runtime"]
    if manifest["schema"] != 133 or not re.fullmatch(r"us-west1-docker\.pkg\.dev/adi-anvil-mvp-2026/anvil-qa-v1/kyc-runtime@sha256:[a-f0-9]{64}", image):
        raise ValueError("Exact immutable schema133 release required")
    nonce = secrets.token_hex(4)
    base = Path("/var/lib/anvil-qa-v1/runtime-functional") / ("private-score-" + nonce)
    base.mkdir(mode=0o700)
    folders = {}
    for name in ("owner", "control", "grader", "bridge", "data", "socket"):
        folders[name] = base / name
        folders[name].mkdir(mode=0o700 if name != "socket" else 0o755)
    os.chown(folders["socket"], 999, 999)
    password = secrets.token_urlsafe(40)
    private(folders["owner"] / "postgres.env", ("POSTGRES_PASSWORD=" + password + "\nPOSTGRES_INITDB_ARGS=--auth-local=scram-sha-256\n").encode())
    config = {"schema_version": "anvil.synthetic-sql-fixture-setup.v2", "host": str(folders["socket"]),
        "dbname": "postgres", "user": "postgres", "password": password,
        "new_database": "anvil_golden_kyc_component_" + nonce, "runtime_image_sha256": image.rsplit("sha256:", 1)[1]}
    private(folders["owner"] / "setup.json", json.dumps(config).encode())
    prefix = "forge-private-" + nonce
    started = {}

    def docker(arguments, timeout=30):
        return subprocess.run(["docker", *arguments], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=True, timeout=timeout).stdout

    docker(["image", "inspect", PG])
    installed = json.loads(docker(["image", "inspect", image]))[0]
    if installed["Config"]["Labels"].get("org.opencontainers.image.revision") != manifest["revision"]:
        raise ValueError("Actual immutable release image revision required")
    pgname = prefix + "-postgres"
    docker(["run", "--pull=never", "-d", "--name", pgname, "--network", "none", "--memory", "768m", "--pids-limit", "128",
        "--cpus", "2", "--label", "io.adi.forge.scope=private-scoring-controls", "--env-file", str(folders["owner"] / "postgres.env"),
        "--mount", f"type=bind,src={folders['data']},dst=/var/lib/postgresql/data",
        "--mount", f"type=bind,src={folders['socket']},dst=/var/run/postgresql", PG])

    def command(phase, program, arguments, mounts, coordinator=False):
        args = ["docker", "run", "--pull=never", "--name", prefix + "-" + phase, "--read-only", "--user", "0:0",
            "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "1536m",
            "--pids-limit", "128", "--cpus", "2", "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=128m",
            "--label", "io.adi.forge.scope=private-scoring-controls", "-e", "ANVIL_ENV=local", "-e", "WEB_ORIGIN=http://127.0.0.1:3202",
            "-e", "ANVIL_RUNTIME_IMAGE_DIGEST=" + config["runtime_image_sha256"], "-e", "ANVIL_LIVE_PROVIDERS_ENABLED=false",
            "-e", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED=false", "-e", "ANVIL_REAL_EMAIL_ENABLED=false"]
        if coordinator:
            args += ["--pid", "host", "--uts", "host", "--userns", "host", "--cgroupns", "host"]
        for source, target, writable in mounts:
            args += ["--mount", f"type=bind,src={source},dst={target}" + ("" if writable else ",readonly")]
        return args + ["--entrypoint", "/opt/anvil-runtime/bin/python", image, "-I", "-B", "/controls/" + program, *arguments]

    scripts = [(bundle / "runtime-checks", "/controls", False)]
    sqlsocket = [(folders["socket"], folders["socket"], False)]
    bridge = [(folders["bridge"], folders["bridge"], True)]

    def retain(phase, process, timeout=180):
        stdout, stderr = process.communicate(timeout=timeout)
        private(base / (phase + ".stdout"), stdout)
        private(base / (phase + ".stderr"), stderr)
        if password.encode() in stdout or b"password=" in stdout.lower():
            raise ValueError("Private diagnostic output retained; do not display")
        print(json.dumps({"phase": phase, "exit_code": process.returncode, "evidence": str(base),
                          "stdout_sha256": hashlib.sha256(stdout).hexdigest()}), flush=True)
        if process.returncode:
            raise RuntimeError("Physical control failed; retained without replay")
        return json.loads(stdout)

    def launch(phase, arguments):
        process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        started[phase] = process
        return process

    def run(phase, program, arguments, mounts, coordinator=False):
        return retain(phase, launch(phase, command(phase, program, arguments, mounts, coordinator)))

    try:
        for _ in range(60):
            if (folders["socket"] / ".s.PGSQL.5432").is_socket():
                break
            time.sleep(.5)
        else:
            raise TimeoutError("Fresh isolated SQL startup expired")
        run("setup", "kyc_sql_fixture_setup.py", ["--config", str(folders["owner"] / "setup.json"),
            "--output", str(folders["control"] / "control.json")], scripts + sqlsocket + [
                (folders["owner"], folders["owner"], False), (folders["control"], folders["control"], True)])
        fixture = json.loads((folders["control"] / "control.json").read_bytes())
        if fixture["golden_source_sha256"] != manifest["source_sha256"]:
            raise ValueError("Actual installed Golden source does not match release")
        run("admit", "private_scoring_fixture.py", ["--owner-config", str(folders["owner"] / "setup.json"),
            "--fixture-config", str(folders["control"] / "control.json"), "--fixture-files", "/fixtures",
            "--output", str(folders["grader"] / "driver.json"), "--bridge-root", str(folders["bridge"])],
            scripts + sqlsocket + bridge + [(folders["owner"], folders["owner"], False),
            (folders["control"], folders["control"], False), (folders["grader"], folders["grader"], True),
            (bundle / "fixtures/private-scoring-control", "/fixtures", False)])
        driver = json.loads((folders["grader"] / "driver.json").read_bytes())
        packets = []
        for index, case in enumerate(driver["cases"]):
            phase = "grader-" + str(index)
            grader = launch(phase, command(phase, "private_scoring_controls.py", ["grader", "--config",
                str(folders["grader"] / "driver.json"), "--case", str(index)], scripts + sqlsocket + bridge + [
                (folders["grader"], folders["grader"], False)]))
            pending = folders["bridge"] / case["context"]["job_id"].replace("-", "") / "request.json"
            polling_cutoff = time.monotonic() + 110
            while time.monotonic() < polling_cutoff:
                if pending.is_file() or grader.poll() is not None:
                    break
                time.sleep(.1)
            if not pending.is_file():
                if grader.poll() is not None:
                    retain(phase, grader)
                raise RuntimeError("No committed private claim; no coordinator dispatch")
            run("coordinator-" + str(index), "private_scoring_controls.py", ["coordinator", "--root", str(folders["bridge"])],
                scripts + bridge + [("/run/docker.sock", "/run/docker.sock", False), ("/usr/bin/docker", "/usr/bin/docker", False)], True)
            packet = retain(phase, grader)
            if packet["status"] != "passed" or packet["qualification_granted"] is not False:
                raise ValueError("Actual scoped private-scoring evidence required")
            info = json.loads(docker(["inspect", packet["executor_container"]]))[0]
            intent = json.loads((pending.parent / "executor/launch-intent.json").read_bytes())
            if (info["State"]["Running"] or info["Config"]["User"] != "10001:10001" or info["Mounts"]
                    or info["HostConfig"]["NetworkMode"] != "none" or not info["HostConfig"]["ReadonlyRootfs"]
                    or set(info["HostConfig"].get("CapDrop") or []) != {"ALL"}
                    or info["Image"] != "sha256:72b8eaacefaa82ffdec3ee632375df24057962d8c14cc327f1990113f7c2b951"
                    or info["Config"]["Labels"].get("org.adi.anvil.custom-python") != intent["label"]
                    or "no-new-privileges" not in (info["HostConfig"].get("SecurityOpt") or [])
                    or (info["HostConfig"]["Memory"], info["HostConfig"]["MemorySwap"], info["HostConfig"]["PidsLimit"], info["HostConfig"]["NanoCpus"])
                        != (134217728, 134217728, 32, 500000000)):
                raise ValueError("Actual retained private executor isolation changed")
            private(base / ("executor-" + str(index) + ".inspect.json"), json.dumps(info, sort_keys=True).encode())
            packets.append(packet)
        evidence = {"schema_version": "anvil.physical-private-scoring-controls.v1", "release": manifest,
            "cases": packets, "qualification_granted": False, "task_score": None, "model_calls_authorized": 0,
            "actual_model_calls": None, "operator_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        raw = json.dumps(evidence, sort_keys=True).encode()
        private(base / "evidence.json", raw)
        print(json.dumps({"status": "physical_controls_observed_not_qualified", "cases": len(packets),
            "evidence": str(base / "evidence.json"), "evidence_sha256": hashlib.sha256(raw).hexdigest()}))
    finally:
        cleanup = []
        for phase, process in started.items():
            if process.poll() is None:
                try:
                    docker(["stop", "--time", "1", prefix + "-" + phase], timeout=6)
                    stdout, stderr = process.communicate(timeout=3)
                except (subprocess.SubprocessError, OSError) as error:
                    cleanup.append({"phase": phase, "error_type": type(error).__name__})
                    process.kill()
                    stdout, stderr = process.communicate(timeout=3)
                for suffix, raw in (("stdout", stdout), ("stderr", stderr)):
                    path = base / (phase + ".partial." + suffix)
                    if not path.exists():
                        private(path, raw)
        try:
            docker(["stop", "--time", "5", pgname])
        except (subprocess.SubprocessError, OSError) as error:
            cleanup.append({"phase": "postgres", "error_type": type(error).__name__})
        private(base / "cleanup.json", json.dumps({"failures": cleanup, "containers_retained": True}).encode())
        if cleanup:
            raise RuntimeError("Owned cleanup incomplete; retained for reconciliation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    main(args.manifest, args.bundle)
