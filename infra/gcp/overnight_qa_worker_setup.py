"""Install an exact-source, paid-off Run worker on the single owned QA host."""

import json
import os
import re
import socket
import subprocess
from pathlib import Path


def main():
    if socket.gethostname() != "anvil-overnight-qa-20261110" or os.getuid() != 0:
        raise ValueError("QA operator identity required")
    root = Path("/var/lib/anvil-overnight-qa")
    native = Path("/var/lib/anvil-qa-native")
    native.mkdir(mode=0o700, exist_ok=True)
    assert native.resolve() == native and native.is_dir()
    native.chmod(0o700)
    os.chown(native, 10001, 10001)
    config = root / "config/compose.json"
    sha = subprocess.check_output(
        [
            "docker",
            "compose",
            "-f",
            str(config),
            "exec",
            "-T",
            "worker",
            "python",
            "-c",
            "from anvil.environment_execution import source_hash; print(source_hash())",
        ],
        text=True,
    ).strip()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("Execution source digest absent")
    for name in (".data", ".local"):
        path = Path("/opt/anvil-overnight-qa/source") / name
        path.mkdir(mode=0o700, exist_ok=True)
        os.chown(path, 10001, 10001)
    launcher = Path("/opt/anvil-overnight-qa/worker-launcher.py")
    launcher.write_bytes(
        Path("/home/vasudevan_sundarababu_adi_labs_a/qa-worker-launcher.py").read_bytes()
    )
    launcher.chmod(0o644)
    unit = f"""[Unit]
Description=Anvil isolated QA durable Run worker
After=docker.service
[Service]
Type=simple
User=anvilqa
Group=anvilqa
WorkingDirectory=/opt/anvil-overnight-qa/source
EnvironmentFile=/var/lib/anvil-overnight-qa/config/worker.env
ExecStart=/opt/anvil-overnight-qa/backend/bin/python /opt/anvil-overnight-qa/worker-launcher.py {sha}
Restart=no
UMask=0077
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
PrivateTmp=true
ReadWritePaths=/opt/anvil-overnight-qa/source/.data /opt/anvil-overnight-qa/source/.local /run/anvil-qa-docker /var/lib/anvil-qa-native
KillMode=control-group
TimeoutStopSec=120
[Install]
WantedBy=multi-user.target
"""
    Path("/etc/systemd/system/anvil-qa-run-worker.service").write_text(unit)
    data = json.loads(config.read_text())
    data["services"]["api"]["environment"] = {
        "ANVIL_ENVIRONMENT_QA_ENABLED": "true",
        "ANVIL_ENVIRONMENT_QA_SOURCE_SHA256": sha,
    }
    config.write_text(json.dumps(data))
    (root / "run-worker-public.json").write_text(
        json.dumps(
            {
                "source_sha256": sha,
                "provider_calls": 0,
                "sql_role": "anvil_worker",
                "provider_keys_forwarded": False,
            }
        )
    )
    print("Exact-source paid-off QA Run worker prepared", sha)


if __name__ == "__main__":
    main()
