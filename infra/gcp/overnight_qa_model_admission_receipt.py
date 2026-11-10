"""Public source/counter readback only; never inspect credentials or secret versions."""

import ast
import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 0
    root = Path("/opt/anvil-overnight-qa/source")
    node = next(
        n
        for n in ast.parse((root / "services/backend/src/anvil/harbor_agents.py").read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == "code_digest"
    )
    names = {
        n.value
        for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.endswith(".py")
    }
    files = [
        root / name if "/" in name else root / "services/backend/src/anvil" / name for name in names
    ]
    values = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    host = hashlib.sha256(
        json.dumps(
            values, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()
    compose = ["docker", "compose", "-f", "/var/lib/anvil-overnight-qa/config/compose.json"]
    api = subprocess.check_output(
        [
            *compose,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "from anvil.harbor_agents import code_digest; print(code_digest())",
        ],
        text=True,
    ).strip()
    assert host == api
    sql = "SELECT json_build_object('provider_call_intents',(SELECT count(*) FROM anvil.harbor_agent_calls),'run_authorizations',(SELECT count(*) FROM anvil.workspace_admin_run_authorizations),'package_approvals',(SELECT count(*) FROM anvil.harbor_approvals))"
    counters = json.loads(
        subprocess.check_output(
            [
                *compose,
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "anvil_migration",
                "-d",
                "anvil",
                "-Atc",
                sql,
            ],
            text=True,
        )
    )
    assert all(value == 0 for value in counters.values())
    subprocess.run(["systemctl", "is-active", "--quiet", "anvil-qa-model-worker"], check=True)
    value = {
        "adapter_sha256": api,
        "host_api_match": True,
        "files": len(files),
        "counters": counters,
        "worker_active": True,
        "activation_created": False,
    }
    Path("/var/lib/anvil-overnight-qa/model-worker-admission-public.json").write_text(
        json.dumps(value)
    )
    print(json.dumps(value))


if __name__ == "__main__":
    main()
