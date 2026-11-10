"""Install exact model bridge and paid-off worker on the single owned QA host."""

import hashlib
import importlib.util
import json
import os
import re
import socket
import subprocess
from pathlib import Path


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 0
    root = Path("/var/lib/anvil-overnight-qa")
    home = Path("/home/vasudevan_sundarababu_adi_labs_a")
    manifest = json.loads((home / "qa-model-bridge-manifest.json").read_text())
    assert set(manifest) == {
        "harbor_agents.py",
        "harbor_worker.py",
        "environment_structured_agent.py",
    }
    target_root = Path("/opt/anvil-overnight-qa/source/services/backend/src/anvil")
    config = root / "config/compose.json"
    compose = ["docker", "compose", "-f", str(config)]
    active = subprocess.check_output(
        [
            *compose,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "anvil_migration",
            "-d",
            "anvil",
            "-Atc",
            "SELECT count(*) FROM anvil.harbor_checks WHERE state IN ('queued','running')",
        ],
        text=True,
    ).strip()
    assert active == "0", "No active Harbor checks may be interrupted"
    for name, hashes in manifest.items():
        target = target_root / name
        if hashes["before"] is None:
            assert not target.exists()
        else:
            assert hashlib.sha256(target.read_bytes()).hexdigest() == hashes["before"]
        assert (
            hashlib.sha256((home / ("qa-bridge-" + name)).read_bytes()).hexdigest()
            == hashes["after"]
        )
    data = json.loads(config.read_text())
    for name in manifest:
        target = target_root / name
        target.write_bytes((home / ("qa-bridge-" + name)).read_bytes())
        target.chmod(0o644)
        os.chown(target, 10001, 10001)
        mount = str(target) + ":/app/services/backend/src/anvil/" + name + ":ro"
        for service in ("api", "worker"):
            assert mount not in data["services"][service]["volumes"]
            data["services"][service]["volumes"].append(mount)
    config.write_text(json.dumps(data))
    subprocess.run([*compose, "up", "-d", "api", "worker"], check=True)
    base = Path("/opt/anvil-overnight-qa")
    for source, name in (
        ("qa-model-worker.py", "model-worker.py"),
        ("qa-run-worker-helper.py", "overnight_qa_worker_launcher.py"),
    ):
        (base / name).write_bytes((home / source).read_bytes())
        (base / name).chmod(0o644)
    source_sha = subprocess.check_output(
        [
            *compose,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "from anvil.environment_execution import source_hash; print(source_hash())",
        ],
        text=True,
    ).strip()
    assert re.fullmatch(r"[0-9a-f]{64}", source_sha)
    spec = importlib.util.spec_from_file_location("qa_model_worker", base / "model-worker.py")
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.path.insert(0, str(base))
    spec.loader.exec_module(module)
    for folder in (
        base / "source/.data/artifacts",
        Path("/var/lib/anvil-qa-native/structured-checks"),
    ):
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        assert not folder.is_symlink()
        folder.chmod(0o700)
        os.chown(folder, 10001, 10001)
    Path("/etc/systemd/system/anvil-qa-model-worker.service").write_text(module.unit(source_sha))
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "start", "anvil-qa-model-worker"], check=True)
    (root / "model-bridge-overlay-public.json").write_text(
        json.dumps(
            {
                "files": manifest,
                "worker": "anvil-qa-model-worker",
                "paid_dispatch_enabled": False,
                "credential_resources_created": False,
                "image_rebuilt": False,
                "execution_source_sha256": source_sha,
            }
        )
    )
    print("Exact guarded model bridge installed; separate paid-off worker started")


if __name__ == "__main__":
    main()
