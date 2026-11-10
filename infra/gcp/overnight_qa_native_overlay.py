"""Exact QA-only shared native workspace fix; keeps systemd PrivateTmp enabled."""

import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 0
    root = Path("/var/lib/anvil-overnight-qa")
    source = Path("/opt/anvil-overnight-qa/source/services/backend/src/anvil/environment_temp.py")
    incoming = Path("/home/vasudevan_sundarababu_adi_labs_a/qa-environment-temp.py")
    before = "68f2555c810b576512fac9cd5f381b89612957fdb365d9f21ab9783176193a1d"
    after = "8a8b5a203fccc0bd6b36703bf21057fd9189b33a167fab6bdf6e1da9c5ebe4a0"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert hashlib.sha256(incoming.read_bytes()).hexdigest() == after
    subprocess.run(["systemctl", "stop", "anvil-qa-run-worker"], check=True)
    source.write_bytes(incoming.read_bytes())
    source.chmod(0o644)
    os.chown(source, 10001, 10001)
    config = root / "config/compose.json"
    data = json.loads(config.read_text())
    mount = str(source) + ":/app/services/backend/src/anvil/environment_temp.py:ro"
    for service in ("api", "worker"):
        assert mount not in data["services"][service]["volumes"]
        data["services"][service]["volumes"].append(mount)
    config.write_text(json.dumps(data))
    compose = ["docker", "compose", "-f", str(config), "up", "-d"]
    subprocess.run([*compose, "api", "worker"], check=True)
    subprocess.run(
        [
            "/opt/anvil-overnight-qa/backend/bin/python",
            "/home/vasudevan_sundarababu_adi_labs_a/qa-worker-setup.py",
        ],
        check=True,
    )
    subprocess.run([*compose, "api"], check=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "start", "anvil-qa-run-worker"], check=True)
    (root / "native-overlay-public.json").write_text(
        json.dumps(
            {
                "before_sha256": before,
                "after_sha256": after,
                "image_rebuilt": False,
                "private_tmp_retained": True,
                "native_parent": "/var/lib/anvil-qa-native",
            }
        )
    )
    print("QA shared native workspace applied; exact-source worker refreshed")


if __name__ == "__main__":
    main()
