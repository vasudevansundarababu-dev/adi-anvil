"""Expose only standard API documentation paths on the existing private QA host."""

import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 0
    root = Path("/var/lib/anvil-overnight-qa")
    path = root / "config/Caddyfile"
    body = path.read_text()
    old = " handle /api/* {"
    new = " @api path /api/* /docs /docs/* /redoc /openapi.json\n handle @api {"
    assert body.count(old) == 1 and "anvil-qa.127.0.0.1.sslip.io:8443" in body
    before = hashlib.sha256(body.encode()).hexdigest()
    body = body.replace(old, new)
    path.write_text(body)
    subprocess.run(["docker", "compose", "-f", str(root / "config/compose.json"), "up", "-d", "--force-recreate", "caddy"], check=True)
    result = {"routing_before_sha256": before, "routing_after_sha256": hashlib.sha256(body.encode()).hexdigest(), "docs": "/docs", "openapi": "/openapi.json", "private_host_only": True}
    (root / "api-docs-public.json").write_text(json.dumps(result))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
