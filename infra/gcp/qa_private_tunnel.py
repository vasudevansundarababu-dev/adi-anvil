"""Start only the existing owned QA HTTPS forward, never new cloud resources."""

import json
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from overnight_qa_lifecycle import NAME, PROJECT, STOP
from overnight_qa_provision import CLI, CONFIG


def main():
    assert datetime.now(timezone.utc) < STOP
    root = Path("/private/tmp/anvil-overnight-qa-20261110-operator")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8443)) == 0:
            print("Existing HTTPS listener retained; verify strict QA health before use")
            return
    env = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "CLOUDSDK_CONFIG": CONFIG,
           "CLOUDSDK_CORE_DISABLE_USAGE_REPORTING": "true", "CLOUDSDK_PYTHON": "/private/tmp/anvil-evaluators-20261109-venv/bin/python"}
    args = [CLI, "--project=" + PROJECT, "--account=vasudevan.sundarababu@adi-labs.ai", "--quiet", "compute", "ssh", "vasudevan_sundarababu_adi_labs_a@" + NAME, "--zone=us-west1-a", "--tunnel-through-iap", "--ssh-key-file=" + str(root / "operator-key"), "--ssh-flag=-oUserKnownHostsFile=" + str(root / "known_hosts"), "--ssh-flag=-oStrictHostKeyChecking=accept-new", "--ssh-flag=-oExitOnForwardFailure=yes", "--ssh-flag=-oServerAliveInterval=30", "--ssh-flag=-N", "--ssh-flag=-L127.0.0.1:8443:127.0.0.1:8443"]
    with (root / "https-tunnel-extended.log").open("a") as log:
        process = subprocess.Popen(args, env=env, stdout=log, stderr=log, start_new_session=True)
    result = {"launcher_pid": process.pid, "local_port": 8443, "target_vm": NAME, "shutdown_at": STOP.isoformat()}
    (root / "https-tunnel-extended-public.json").write_text(json.dumps(result))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
