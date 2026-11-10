"""Configure only the dedicated QA managed store; never handles key values."""

import json
import os
import socket
import subprocess
from pathlib import Path

RESOURCE = "projects/676933531888/secrets/anvil-qa-model-credentials"


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 0
    root = Path("/var/lib/anvil-overnight-qa")
    index = root / "secret-index"
    index.mkdir(mode=0o700, exist_ok=True)
    assert not index.is_symlink()
    os.chown(index, 10001, 10001)
    index.chmod(0o700)
    host_index = Path("/opt/anvil-overnight-qa/source/.data/secret-index")
    host_index.mkdir(mode=0o700, exist_ok=True)
    os.chown(host_index, 10001, 10001)
    host_index.chmod(0o700)
    config = root / "config/compose.json"
    data = json.loads(config.read_text())
    api = data["services"]["api"]
    api.setdefault("environment", {}).update(
        ANVIL_CREDENTIAL_STORE_PROFILE="qa", ANVIL_QA_SECRET_RESOURCE=RESOURCE,
        ANVIL_CLOUD_SECRET_INDEX="/app/.data/secret-index",
    )
    mount = str(index) + ":/app/.data/secret-index"
    if mount not in api["volumes"]:
        api["volumes"].append(mount)
    config.write_text(json.dumps(data))
    dropin = Path("/etc/systemd/system/anvil-qa-model-worker.service.d")
    dropin.mkdir(exist_ok=True)
    (dropin / "credential-store.conf").write_text(
        "[Service]\nEnvironment=ANVIL_QA_SECRET_RESOURCE=" + RESOURCE + "\n"
        "BindPaths=" + str(index) + ":" + str(host_index) + "\n"
    )
    subprocess.run(["docker", "compose", "-f", str(config), "up", "-d", "postgres", "neo4j", "keycloak", "api", "worker", "web", "caddy"], check=True)
    # Restore only the actor daemon's dedicated bridge after this QA-only reboot.
    bridge = subprocess.run(["ip", "link", "show", "anvilqaactor0"], capture_output=True)
    if bridge.returncode:
        subprocess.run(["ip", "link", "add", "anvilqaactor0", "type", "bridge"], check=True)
    subprocess.run(["ip", "link", "set", "anvilqaactor0", "up"], check=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "start", "anvil-qa-actor-docker", "anvil-qa-run-worker", "anvil-qa-model-worker"], check=True)
    result = {"credential_store_resource": RESOURCE, "provider_calls_dispatched": 0,
              "managed_index_shared": True, "paid_runtime_activation": False}
    (root / "credential-store-setup-public.json").write_text(json.dumps(result))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
