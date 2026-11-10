"""Add explicitly labelled software QA controls to this QA runtime only."""

import hashlib
import json
import os
import re
import socket
import subprocess
from pathlib import Path


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 0
    root = Path("/var/lib/anvil-overnight-qa")
    target = Path("/opt/anvil-overnight-qa/source/services/backend/src/anvil/benchmark_business_fixture.py")
    body = Path("/home/vasudevan_sundarababu_adi_labs_a/qa-business-controls.py").read_bytes()
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    target.write_bytes(body)
    target.chmod(0o644)
    config = root / "config/compose.json"
    data = json.loads(config.read_text())
    mount = str(target) + ":/app/services/backend/src/anvil/benchmark_business_fixture.py:ro"
    for name in ("api", "worker"):
        data["services"][name].setdefault("environment", {})["ANVIL_QA_ACCEPTANCE_CONTROLS_ENABLED"] = "true"
        if mount not in data["services"][name]["volumes"]:
            data["services"][name]["volumes"].append(mount)
    compose = ["docker", "compose", "-f", str(config)]
    config.write_text(json.dumps(data))
    subprocess.run([*compose, "up", "-d", "api", "worker"], check=True)
    digest = subprocess.check_output([*compose, "exec", "-T", "api", "python", "-c", "from anvil.environment_execution import source_hash; print(source_hash())"], text=True).strip()
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    data["services"]["api"]["environment"]["ANVIL_ENVIRONMENT_QA_SOURCE_SHA256"] = digest
    config.write_text(json.dumps(data))
    subprocess.run([*compose, "up", "-d", "api"], check=True)
    for name in ("anvil-qa-run-worker", "anvil-qa-model-worker"):
        unit = Path("/etc/systemd/system/" + name + ".service")
        content = unit.read_text()
        content, count = re.subn(r"(?m)^(ExecStart=.* )([0-9a-f]{64})$", lambda m: m[1] + digest, content)
        assert count == 1
        unit.write_text(content)
        dropin = Path("/etc/systemd/system/" + name + ".service.d")
        dropin.mkdir(exist_ok=True)
        (dropin / "qa-controls.conf").write_text("[Service]\nEnvironment=ANVIL_QA_ACCEPTANCE_CONTROLS_ENABLED=true\n")
    helper = Path("/home/vasudevan_sundarababu_adi_labs_a/qa-controls-worker-helper.py").read_bytes()
    Path("/opt/anvil-overnight-qa/overnight_qa_worker_launcher.py").write_bytes(helper)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "restart", "anvil-qa-run-worker", "anvil-qa-model-worker"], check=True)
    result = {"fixture_before_sha256": before, "fixture_after_sha256": hashlib.sha256(body).hexdigest(), "environment_source_sha256": digest, "image_rebuilt": False, "controls": ["fictional-zero-control-v1", "fictional-error-control-v1"], "model_performance": False}
    (root / "qa-team-controls-overlay-public.json").write_text(json.dumps(result))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
