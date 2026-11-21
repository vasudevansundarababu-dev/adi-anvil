"""One-shot installed QA SQL/registry/OPA/ZEN controls, not qualification.

Every SQL mode gets a fresh standalone cluster. Registry mode's manufactured
approval/publication prerequisites remain synthetic software fixtures only.
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
from urllib.parse import quote, urlencode

PG = "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/core-postgres-security@sha256:2bb3e2ab0cea85749f75dd2751ae015075274e89fb3c04736c64d932693927a2"


def private(path, raw):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main(manifest_path, bundle, kind):
    if os.geteuid() != 0 or os.uname().nodename != "anvil-qa-v1" or kind not in {"sql", "registry", "components"}:
        raise ValueError("Exact existing QA control mode required")
    release = json.loads(Path(manifest_path).read_bytes())
    image = release["images"]["kyc-runtime"]
    if release["schema"] != 134 or not re.fullmatch(r"us-west1-docker\.pkg\.dev/adi-anvil-mvp-2026/anvil-qa-v1/kyc-runtime@sha256:[a-f0-9]{64}", image):
        raise ValueError("Exact immutable schema134 QA runtime required")
    nonce = secrets.token_hex(4)
    prefix = "forge-qualification-" + kind + "-" + nonce
    base = Path("/var/lib/anvil-qa-v1/runtime-functional") / ("qualification-" + kind + "-" + nonce)
    base.mkdir(mode=0o700)
    cleanup_failures = []
    files = {}
    for name in ("kyc_sql_fixture_setup.py", "kyc_sql_component_controls.py", "kyc_policy_registry_controls.py",
                 "kyc_policy_registry_fixture.py", "component_controls.py"):
        relative = "runtime-checks/" + name
        expected = (release["control_files"] | release["operational_files"])[relative]
        path = bundle / relative
        if path.resolve() != path or path.stat().st_uid != 0 or path.stat().st_mode & 0o022 or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Exact committed root-owned control bytes required")
        files[name] = expected

    def docker(arguments, timeout=30):
        return subprocess.run(["docker", *arguments], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=True, timeout=timeout).stdout

    def run(phase, program, arguments, mounts):
        args = ["docker", "run", "--pull=never", "--name", prefix + "-" + phase, "--read-only", "--user", "0:0" if kind != "components" else "10001:10001",
            "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "1536m", "--cpus", "2", "--pids-limit", "128",
            "--label", "io.adi.forge.scope=isolated-qualification-controls", "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=128m,mode=1777",
            "-e", "ANVIL_ENV=local", "-e", "WEB_ORIGIN=http://127.0.0.1:3202", "-e", "ANVIL_RUNTIME_IMAGE_DIGEST=" + image.rsplit("sha256:", 1)[1],
            "-e", "ANVIL_LIVE_PROVIDERS_ENABLED=false", "-e", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED=false", "-e", "ANVIL_REAL_EMAIL_ENABLED=false",
            "--mount", f"type=bind,src={bundle / 'runtime-checks'},dst=/controls,readonly"]
        for source, target, writable in mounts:
            args += ["--mount", f"type=bind,src={source},dst={target}" + ("" if writable else ",readonly")]
        args += ["--entrypoint", "/opt/anvil-runtime/bin/python", image, "-I", "-B", "/controls/" + program, *arguments]
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=340)
        except BaseException:
            try:
                docker(["stop", "--time", "1", prefix + "-" + phase], timeout=6)
            except (OSError, subprocess.SubprocessError) as error:
                cleanup_failures.append({"phase": phase, "container_stop_error": type(error).__name__})
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=3)
                cleanup_failures.append({"phase": phase, "cli_killed_after_owned_stop": True})
            private(base / (phase + ".partial.stdout"), stdout)
            private(base / (phase + ".partial.stderr"), stderr)
            raise
        private(base / (phase + ".stdout"), stdout)
        private(base / (phase + ".stderr"), stderr)
        print(json.dumps({"kind": kind, "phase": phase, "exit_code": process.returncode, "evidence": str(base)}), flush=True)
        if process.returncode:
            raise RuntimeError("Installed control failed; retained without replay")
        info = json.loads(docker(["inspect", prefix + "-" + phase]))[0]
        if info["State"]["Running"] or info["State"]["ExitCode"] or info["Config"]["Image"] != image or info["Config"]["Labels"].get("org.opencontainers.image.revision") != release["revision"]:
            raise ValueError("Actual exact installed terminal container required")
        private(base / (phase + ".inspect.json"), json.dumps(info, sort_keys=True).encode())
        return json.loads(stdout), hashlib.sha256(stdout).hexdigest()

    pgname = None
    try:
        if kind == "components":
            packet, sha = run("runtime", "component_controls.py", [], [])
            if packet.get("golden_source_sha256") != release["source_sha256"]:
                raise ValueError("Actual installed component source does not match release")
        else:
            folders = {}
            for name in ("owner", "control", "data", "socket"):
                folders[name] = base / name
                folders[name].mkdir(mode=0o755 if name == "socket" else 0o700)
            os.chown(folders["socket"], 999, 999)
            password = secrets.token_urlsafe(40)
            database = "anvil_golden_kyc_component_" + nonce
            private(folders["owner"] / "postgres.env", ("POSTGRES_PASSWORD=" + password + "\nPOSTGRES_INITDB_ARGS=--auth-local=scram-sha-256\n").encode())
            setup = {"schema_version": "anvil.synthetic-sql-fixture-setup.v2", "host": str(folders["socket"]), "dbname": "postgres", "user": "postgres",
                "password": password, "new_database": database, "runtime_image_sha256": image.rsplit("sha256:", 1)[1]}
            private(folders["owner"] / "setup.json", json.dumps(setup).encode())
            pgname = prefix + "-postgres"
            docker(["run", "--pull=never", "-d", "--name", pgname, "--network", "none", "--memory", "768m", "--cpus", "2", "--pids-limit", "128",
                "--env-file", str(folders["owner"] / "postgres.env"), "--mount", f"type=bind,src={folders['data']},dst=/var/lib/postgresql/data",
                "--mount", f"type=bind,src={folders['socket']},dst=/var/run/postgresql", PG])
            for _ in range(60):
                if (folders["socket"] / ".s.PGSQL.5432").is_socket():
                    break
                time.sleep(.5)
            else:
                raise TimeoutError("Fresh isolated SQL startup failed")
            run("setup", "kyc_sql_fixture_setup.py", ["--config", str(folders["owner"] / "setup.json"), "--output", str(folders["control"] / "control.json")],
                [(folders["socket"], folders["socket"], False), (folders["owner"], folders["owner"], False), (folders["control"], folders["control"], True)])
            fixture = json.loads((folders["control"] / "control.json").read_bytes())
            if fixture["golden_source_sha256"] != release["source_sha256"]:
                raise ValueError("Actual installed Golden source must match this release")
            mounts = [(folders["socket"], folders["socket"], False), (folders["control"], folders["control"], False)]
            program, config = "kyc_sql_component_controls.py", folders["control"] / "control.json"
            if kind == "registry":
                driver = {"schema_version": "anvil.synthetic-policy-registry-controls.v1", "fixture_config": str(config),
                    "owner_dsn": "postgresql://postgres:" + quote(password, safe="") + "@/" + database + "?" + urlencode({"host": str(folders["socket"])})}
                config = folders["owner"] / "registry-driver.json"
                private(config, json.dumps(driver).encode())
                mounts += [(folders["owner"], folders["owner"], False)]
                program = "kyc_policy_registry_controls.py"
            packet, sha = run("runtime", program, ["--config", str(config)], mounts)
        if not packet.get("controls") or any(item["status"] != "passed" for item in packet["controls"].values()):
            raise ValueError("All actual installed controls must pass")
        evidence = {"schema_version": "anvil.installed-qualification-control-execution.v1", "kind": kind, "release": release,
            "packet": packet, "packet_stdout_sha256": sha, "control_scripts": files, "qualification_granted": False,
            "model_calls_authorized": 0, "actual_model_calls": None}
        raw = json.dumps(evidence, sort_keys=True).encode()
        private(base / "evidence.json", raw)
        print(json.dumps({"status": "observed_not_qualified", "kind": kind, "evidence": str(base / "evidence.json"),
            "evidence_sha256": hashlib.sha256(raw).hexdigest()}), flush=True)
    finally:
        if pgname is not None:
            try:
                docker(["stop", "--time", "5", pgname])
            except (OSError, subprocess.SubprocessError) as error:
                cleanup_failures.append({"phase": "postgres", "error_type": type(error).__name__})
        private(base / "cleanup.json", json.dumps({"failures": cleanup_failures, "containers_retained": True}).encode())
        if cleanup_failures:
            raise RuntimeError("Owned control cleanup incomplete; retained for reconciliation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--kind", choices=("sql", "registry", "components"), required=True)
    args = parser.parse_args()
    main(args.manifest, args.bundle, args.kind)
