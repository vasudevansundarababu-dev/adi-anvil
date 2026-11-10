"""Deploy exact-source, paid-off fictional QA business admission; no image build."""

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
    base = Path("/opt/anvil-overnight-qa/source/services/backend/src/anvil")
    config = root / "config/compose.json"
    compose = ["docker", "compose", "-f", str(config)]
    active = subprocess.check_output([*compose, "exec", "-T", "postgres", "psql", "-U", "anvil_migration", "-d", "anvil", "-Atc", "SELECT count(*) FROM anvil.harbor_checks WHERE candidate='agent' AND state IN ('queued','running')"], text=True).strip()
    assert active == "0", "Finish admitted smoke before paid-off QA deployment"
    data = json.loads(config.read_text())
    assert data["services"]["api"]["environment"].get("ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED") == "false"
    files = {}
    for name in ("benchmark_business_admission.py", "benchmark_runs.py", "benchmark_run_worker.py", "workspace.py"):
        target = base / name
        before = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        body = Path("/home/vasudevan_sundarababu_adi_labs_a/qa-business-" + name).read_bytes()
        target.write_bytes(body)
        files[name] = {"before": before, "after": hashlib.sha256(body).hexdigest()}
        target.chmod(0o644)
        mount = str(target) + ":/app/services/backend/src/anvil/" + name + ":ro"
        for service in ("api", "worker"):
            if mount not in data["services"][service]["volumes"]:
                data["services"][service]["volumes"].append(mount)
    config.write_text(json.dumps(data))
    subprocess.run([*compose, "up", "-d", "api", "worker"], check=True)
    sha = subprocess.check_output([*compose, "exec", "-T", "api", "python", "-c", "from anvil.benchmark_runs import source_hash; print(source_hash())"], text=True).strip()
    assert re.fullmatch(r"[0-9a-f]{64}", sha)
    for service in ("api", "worker"):
        data["services"][service].setdefault("environment", {}).update(ANVIL_BUSINESS_QA_ENABLED="true", ANVIL_BUSINESS_QA_SOURCE_SHA256=sha)
    config.write_text(json.dumps(data))
    subprocess.run([*compose, "up", "-d", "api", "worker"], check=True)
    dropin = Path("/etc/systemd/system/anvil-qa-run-worker.service.d/business-qa.conf")
    dropin.write_text("[Service]\nEnvironment=ANVIL_BUSINESS_QA_ENABLED=true\nEnvironment=ANVIL_BUSINESS_QA_SOURCE_SHA256=" + sha + "\n")
    Path("/opt/anvil-overnight-qa/overnight_qa_worker_launcher.py").write_bytes(Path("/home/vasudevan_sundarababu_adi_labs_a/qa-controls-worker-helper.py").read_bytes())
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "restart", "anvil-qa-run-worker"], check=True)
    result = {"business_qa_source_sha256": sha, "files": files, "paid_enabled": False, "image_rebuilt": False, "authentic_source_qualification": False}
    (root / "qa-team-business-admission-public.json").write_text(json.dumps(result))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
