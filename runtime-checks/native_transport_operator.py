"""Root-owned physical private-PID worker/SDK transport control on existing QA.

No SQL/provider mount or secret. Fixed installed no-effect worker only. Source
and kernel/profile observations must pass before any qualification is issued.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path


def private(path, raw):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main(manifest_path, *, observe_network=False):
    if os.geteuid() != 0 or os.uname().nodename != "anvil-qa-v1":
        raise ValueError("Existing QA root only")
    release = json.loads(Path(manifest_path).read_bytes())
    image = release["images"]["kyc-runtime"]
    if release["schema"] != 133 or not re.fullmatch(r"us-west1-docker\.pkg\.dev/adi-anvil-mvp-2026/anvil-qa-v1/kyc-runtime@sha256:[a-f0-9]{64}", image):
        raise ValueError("Exact release required")
    base = Path("/var/lib/anvil-qa-v1/runtime-functional")
    proof, bridge = base / "harbor-proof", base / "native-control-bridge"
    work = proof / "native-control-work"
    qualification = proof / "component-qualification"
    if not qualification.exists():
        qualification.mkdir(mode=0o755)
    if qualification.stat().st_uid != 0 or qualification.stat().st_mode & 0o022:
        raise ValueError("Root-controlled read-only qualification projection required")
    if not bridge.exists():
        bridge.mkdir(mode=0o700)
        os.chown(bridge, 10001, 10001)
    if not work.exists():
        work.mkdir(mode=0o700)
    if bridge.stat().st_uid != 10001 or bridge.stat().st_mode & 0o077 or work.stat().st_uid != 0 or work.stat().st_mode & 0o077:
        raise ValueError("Exact disjoint worker and operator roots required")
    before = {path.name for path in bridge.iterdir()}
    tag = release["revision"][:12] + "-" + str(time.monotonic_ns())
    evidence = base / ("transport-" + tag)
    evidence.mkdir(mode=0o700)

    def command(role):
        root = role == "sdk"
        args = ["docker", "run", "--pull=never", "--name", "forge-transport-" + role + "-" + tag,
            "--label", "io.adi.forge.scope=native-transport-control", "--read-only", "--user", "0:0" if root else "10001:10001",
            "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--userns", "host",
            "--memory", "1536m", "--pids-limit", "256", "--cpus", "2", "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=128m",
            "--mount", f"type=bind,src={bridge},dst={bridge}", "-e", "ANVIL_ENV=local", "-e", "WEB_ORIGIN=http://127.0.0.1:3202",
            "-e", "ANVIL_RUNTIME_IMAGE_DIGEST=" + image.rsplit("sha256:", 1)[1], "-e", "ANVIL_LIVE_PROVIDERS_ENABLED=false",
            "-e", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED=false", "-e", "ANVIL_REAL_EMAIL_ENABLED=false"]
        if root:
            args += ["--pid", "host", "--uts", "host", "--cgroupns", "host", "--cap-add", "SYS_PTRACE",
                "--cap-add", "DAC_OVERRIDE", "--cap-add", "CHOWN",
                "--security-opt", "apparmor=unconfined", "--mount", f"type=bind,src={proof},dst={proof}",
                "--mount", f"type=bind,src={qualification},dst=/opt/anvil-runtime-source/.data/component-qualification,readonly",
                "--mount", "type=bind,src=/run/docker.sock,dst=/run/docker.sock,readonly",
                "--mount", "type=bind,src=/usr/bin/docker,dst=/usr/bin/docker,readonly",
                "--mount", "type=bind,src=/usr/libexec/docker/cli-plugins/docker-compose,dst=/usr/libexec/docker/cli-plugins/docker-compose,readonly",
                "-e", "ANVIL_GOLDEN_NATIVE_COORDINATOR_ENABLED=true", "-e", "ANVIL_NATIVE_BRIDGE_ROOT=" + str(bridge),
                "-e", "ANVIL_GOLDEN_NATIVE_WORK_ROOT=" + str(work), "-e", "ANVIL_HARBOR_DOCKER_HOST=unix:///run/docker.sock",
                "-e", "ANVIL_HARBOR_PYTHON=/opt/anvil-runtime/bin/python"]
        return args + ["--entrypoint", "/opt/anvil-runtime/bin/python", image, "-I", "-B", "-m"]

    with ExitStack() as cleanup:
        observers = []

        def launch(role, arguments):
            if observe_network:
                from network_observer import FilteredSDKObserver, NetworkObserver

                observed = (FilteredSDKObserver if role == "sdk" else NetworkObserver)(arguments, evidence, role, bridge)
                observers.append(observed)
                cleanup.callback(observed.abort)
                return observed.process
            process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            def stop():
                if process.poll() is None:
                    subprocess.run(["docker", "stop", "--time", "1", arguments[arguments.index("--name")+1]], capture_output=True, timeout=6)
                    stdout, stderr = process.communicate(timeout=3)
                    private(evidence / (role + ".partial.stdout"), stdout)
                    private(evidence / (role + ".partial.stderr"), stderr)

            cleanup.callback(stop)
            return process

        worker = launch("worker", command("worker") + ["anvil.golden_native_control", "--root", str(bridge)])
        # Cold isolated imports precede the worker's own 300-second cutoff.
        # Tracing makes imports slower; do not confuse startup with no intent.
        for _ in range(600):
            pending = [p for p in bridge.iterdir() if p.name not in before and re.fullmatch("[a-f0-9]{32}", p.name) and (p / "request.json").is_file()]
            if pending or worker.poll() is not None:
                break
            time.sleep(.1)
        if len(pending) != 1:
            private(evidence / "startup-failure.json", json.dumps({"observed_intents": len(pending),
                "worker_terminal": worker.poll() is not None, "qualification_granted": False,
                "status": "unknown_no_replay"}).encode())
            if worker.poll() is not None:
                stdout, stderr = worker.communicate(timeout=3)
                private(evidence / "worker.stdout", stdout)
                private(evidence / "worker.stderr", stderr)
            raise RuntimeError("Exactly one fresh worker intent required; no replay")
        attempt = pending[0]
        sdk = launch("sdk", command("sdk") + ["anvil.golden_native_bridge", "--once", attempt.name])
        for role, process in (("sdk", sdk), ("worker", worker)):
            stdout, stderr = process.communicate(timeout=430)
            private(evidence / (role + ".stdout"), stdout)
            private(evidence / (role + ".stderr"), stderr)
            print(json.dumps({"phase": role, "exit_code": process.returncode, "evidence": str(evidence)}), flush=True)
            if process.returncode:
                raise RuntimeError("Physical transport failed; retained without replay")
        networks = [observer.finish() for observer in observers]
        completion = json.loads((attempt / "completion.json").read_bytes())
        result = completion["framework"]
        if result["worker_bridge_purpose"] != "native_transport_control_only" or result["cleanup"] != {"complete": True, "retained": True}:
            raise ValueError("Actual purpose-fenced collection and cleanup required")
        raw = json.dumps({"schema_version": "anvil.physical-native-transport-observation.v1", "release": release,
            "framework": result, "attempt": str(attempt), "qualification_granted": False, "task_score": None,
            "operator_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "network_observations": networks,
            "model_calls_authorized": 0, "actual_model_calls": None}, sort_keys=True).encode()
        private(evidence / "evidence.json", raw)
        print(json.dumps({"status": "observed_not_qualified", "evidence_sha256": hashlib.sha256(raw).hexdigest(), "evidence": str(evidence)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--observe-network", action="store_true")
    args = parser.parse_args()
    main(args.manifest, observe_network=args.observe_network)
