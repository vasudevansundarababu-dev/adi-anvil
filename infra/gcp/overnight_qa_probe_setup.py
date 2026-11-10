"""Run a one-shot credential probe in the existing QA worker's sandbox."""

import json
import os
import socket
import subprocess
from pathlib import Path


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 0
    home = Path("/home/vasudevan_sundarababu_adi_labs_a")
    base = Path("/opt/anvil-overnight-qa")
    for source, target in (("qa-credential-probe.py", "credential-probe.py"),
                           ("qa-credential-bindings-public.json", "credential-bindings-public.json")):
        (base / target).write_bytes((home / source).read_bytes())
        (base / target).chmod(0o644)
    launcher = base / "credential-probe-launcher.py"
    launcher.write_text('import importlib.util,os,sys\nsys.path.insert(0,"/opt/anvil-overnight-qa")\nspec=importlib.util.spec_from_file_location("modelworker","/opt/anvil-overnight-qa/model-worker.py")\nm=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\nenv=m.environment(os.environ,sys.argv[1])\nos.execve("/opt/anvil-overnight-qa/backend/bin/python",["/opt/anvil-overnight-qa/backend/bin/python","/opt/anvil-overnight-qa/credential-probe.py","/opt/anvil-overnight-qa/credential-bindings-public.json"],env)\n')
    launcher.chmod(0o644)
    unit = Path("/etc/systemd/system/anvil-qa-model-worker.service").read_text()
    old = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    unit = unit.replace(old, old.replace("/model-worker.py", "/credential-probe-launcher.py"))
    unit = unit.replace("Type=simple", "Type=oneshot")
    unit = unit.replace("[Install]", "BindPaths=/var/lib/anvil-overnight-qa/secret-index:/opt/anvil-overnight-qa/source/.data/secret-index\nEnvironment=ANVIL_QA_SECRET_RESOURCE=projects/676933531888/secrets/anvil-qa-model-credentials\n[Install]")
    Path("/etc/systemd/system/anvil-qa-credential-probe.service").write_text(unit)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "start", "anvil-qa-credential-probe"], check=True)
    result = json.loads(Path("/var/lib/anvil-qa-native/credential-probe-public.json").read_text())
    print(json.dumps(result))


if __name__ == "__main__":
    main()
