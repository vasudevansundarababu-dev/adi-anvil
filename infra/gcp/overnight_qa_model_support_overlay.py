"""Apply two checksum-verified model-support files to the paid-off QA runtime."""

import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 0
    root = Path("/var/lib/anvil-overnight-qa")
    changes = {
        "workspace_costs.py": (
            "82c5b162e465474a0a1859d2c549773702bd6f716620845e0f16c9e1b131e33a",
            "38537cd4e36472df14ca3b89e33d4c377da8faea7ff44bda5dade7490ae9fe12",
        ),
        "providers.py": (
            "3c8511df3f3be3b640868f04455ca39fc7df46c3b454648fe7ba06705bfb8677",
            "4ba54a78f57cf1e274e6c2dbd3c889aa02092ffd158a726fee800d3a3961cd13",
        ),
    }
    config = root / "config/compose.json"
    data = json.loads(config.read_text())
    for name, (before, after) in changes.items():
        target = Path("/opt/anvil-overnight-qa/source/services/backend/src/anvil") / name
        incoming = Path("/home/vasudevan_sundarababu_adi_labs_a") / ("qa-model-" + name)
        assert hashlib.sha256(target.read_bytes()).hexdigest() == before
        assert hashlib.sha256(incoming.read_bytes()).hexdigest() == after
    subprocess.run(["systemctl", "stop", "anvil-qa-run-worker"], check=True)
    for name in changes:
        target = Path("/opt/anvil-overnight-qa/source/services/backend/src/anvil") / name
        target.write_bytes(
            (Path("/home/vasudevan_sundarababu_adi_labs_a") / ("qa-model-" + name)).read_bytes()
        )
        target.chmod(0o644)
        os.chown(target, 10001, 10001)
        mount = str(target) + ":/app/services/backend/src/anvil/" + name + ":ro"
        for service in ("api", "worker"):
            assert mount not in data["services"][service]["volumes"]
            data["services"][service]["volumes"].append(mount)
    config.write_text(json.dumps(data))
    subprocess.run(
        ["docker", "compose", "-f", str(config), "up", "-d", "api", "worker"], check=True
    )
    subprocess.run(["systemctl", "start", "anvil-qa-run-worker"], check=True)
    (root / "model-support-overlay-public.json").write_text(
        json.dumps({"files": changes, "paid_flags_changed": False, "image_rebuilt": False})
    )
    print("Exact model support overlay applied; paid flags unchanged")


if __name__ == "__main__":
    main()
