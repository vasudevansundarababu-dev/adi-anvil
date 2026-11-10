"""Exact QA runtime switch; application Run/cost/identity gates remain mandatory."""

import hashlib
import json
import os
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main(enabled):
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 0
    assert datetime.now(timezone.utc) < datetime(2026, 11, 11, 18, tzinfo=timezone.utc)
    root = Path("/var/lib/anvil-overnight-qa")
    config = root / "config/compose.json"
    data = json.loads(config.read_text())
    api = data["services"]["api"]["environment"]
    assert api["ANVIL_QA_SECRET_RESOURCE"] == "projects/676933531888/secrets/anvil-qa-model-credentials"
    api["ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED"] = "true" if enabled else "false"
    assert api.get("ANVIL_LIVE_PROVIDERS_ENABLED", "false") == "false"
    config.write_text(json.dumps(data))
    uploaded = Path("/home/vasudevan_sundarababu_adi_labs_a/qa-live-model-worker.py")
    content = uploaded.read_bytes()
    destination = Path("/opt/anvil-overnight-qa/model-worker.py")
    destination.write_bytes(content)
    destination.chmod(0o644)
    short = Path("/var/lib/anvil-qa-native/s")
    short.mkdir(mode=0o700, exist_ok=True)
    assert not short.is_symlink()
    os.chown(short, 10001, 10001)
    short.chmod(0o700)
    dropin = Path("/etc/systemd/system/anvil-qa-model-worker.service.d/smoke.conf")
    dropin.write_text("[Service]\nEnvironment=ANVIL_QA_MODEL_SMOKE_ENABLED=" + ("true" if enabled else "false") + "\n")
    subprocess.run(["docker", "compose", "-f", str(config), "up", "-d", "api"], check=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "restart", "anvil-qa-model-worker"], check=True)
    receipt = {"enabled": enabled, "worker_source_sha256": hashlib.sha256(content).hexdigest(), "shutdown_at": "2026-11-11T18:00:00Z", "legacy_live_enabled": False, "source_approvals_created": 0}
    (root / "model-smoke-activation-public.json").write_text(json.dumps(receipt))
    print(json.dumps(receipt))


if __name__ == "__main__":
    import sys
    assert sys.argv[1] in {"on", "off"}
    main(sys.argv[1] == "on")
