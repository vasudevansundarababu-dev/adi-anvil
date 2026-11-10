"""Exact QA-only source overlay; no image rebuild or production changes."""

import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 0
    root = Path("/var/lib/anvil-overnight-qa")
    source = Path(
        "/opt/anvil-overnight-qa/source/services/backend/src/anvil/environment_openenv.py"
    )
    incoming = Path("/home/vasudevan_sundarababu_adi_labs_a/qa-environment-openenv.py")
    before = "d5c495274cb81bcd1a692ccae55f92c538e3d3254a6865d10d4af2948fec7f29"
    after = "1200d98ad20718d64a59b5e519f2f2b3cda46dda5c823c140df3c316cf7fd082"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert hashlib.sha256(incoming.read_bytes()).hexdigest() == after
    subprocess.run(["systemctl", "stop", "anvil-qa-run-worker"], check=True)
    source.write_bytes(incoming.read_bytes())
    source.chmod(0o644)
    os.chown(source, 10001, 10001)
    config = root / "config/compose.json"
    data = json.loads(config.read_text())
    mount = str(source) + ":/app/services/backend/src/anvil/environment_openenv.py:ro"
    for service in ("api", "worker"):
        assert mount not in data["services"][service]["volumes"]
        data["services"][service]["volumes"].append(mount)
    config.write_text(json.dumps(data))
    subprocess.run(
        ["docker", "compose", "-f", str(config), "up", "-d", "api", "worker"], check=True
    )
    subprocess.run(
        [
            "/opt/anvil-overnight-qa/backend/bin/python",
            "/home/vasudevan_sundarababu_adi_labs_a/qa-worker-setup.py",
        ],
        check=True,
    )
    # Setup freezes the new source hash in Compose; activate that admission value.
    subprocess.run(
        ["docker", "compose", "-f", str(config), "up", "-d", "api"], check=True
    )
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "start", "anvil-qa-run-worker"], check=True)
    (root / "openenv-overlay-public.json").write_text(
        json.dumps(
            {
                "before_sha256": before,
                "after_sha256": after,
                "image_rebuilt": False,
                "paid_calls_enabled": False,
            }
        )
    )
    print("QA OpenEnv overlay applied; exact-source worker refreshed")


if __name__ == "__main__":
    main()
