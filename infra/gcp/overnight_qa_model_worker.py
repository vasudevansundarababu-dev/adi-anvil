"""Separate paid-off QA model-worker configuration; no activation or secrets export."""

import os
import re
import socket
from urllib.parse import urlsplit, urlunsplit

from overnight_qa_worker_launcher import environment as run_environment


def environment(values, source_sha256):
    result = run_environment(values, source_sha256)
    app = urlsplit(values["DATABASE_URL"])
    if (
        app.scheme != "postgresql"
        or app.username != "anvil_app"
        or app.hostname != "postgres"
        or app.port != 5432
        or app.path != "/anvil"
        or app.query
        or app.fragment
    ):
        raise ValueError("Only the scoped QA app identity is allowed for the guarded broker")
    result["DATABASE_URL"] = urlunsplit(
        app._replace(
            netloc=app.netloc.rsplit("@", 1)[0] + "@127.0.0.1:55432", query="connect_timeout=5"
        )
    )
    result.update(
        {
            "ARTIFACT_ROOT": "/opt/anvil-overnight-qa/source/.data/artifacts",
            "ANVIL_HARBOR_WORK_ROOT": "/var/lib/anvil-qa-native/structured-checks",
            "ANVIL_HARBOR_EXECUTABLE": "/opt/anvil-overnight-qa/harbor/bin/harbor",
            "ANVIL_HARBOR_AGENT_PATH": "/opt/anvil-overnight-qa/source/services/harbor/src",
            "ANVIL_HARBOR_WORKER_ENABLED": "synthetic-checks-only",
            "ANVIL_HARBOR_HOST_MEDIATED_STRUCTURED_ENABLED": "true",
            "ANVIL_CREDENTIAL_STORE_PROFILE": "qa",
            "ANVIL_CLOUD_SECRET_INDEX": "/opt/anvil-overnight-qa/source/.data/secret-index",
        }
    )
    resource = values.get("ANVIL_QA_SECRET_RESOURCE")
    if resource:
        if not re.fullmatch(r"projects/[0-9]+/secrets/anvil-qa-model-credentials", resource):
            raise ValueError("Only the separate QA project credential secret is allowed")
        result["ANVIL_QA_SECRET_RESOURCE"] = resource
    return result


def unit(source_sha256):
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("Exact execution source required")
    return f"""[Unit]
Description=Anvil isolated QA guarded structured model worker (paid off)
After=docker.service anvil-qa-actor-docker.service
[Service]
Type=simple
User=anvilqa
Group=anvilqa
WorkingDirectory=/opt/anvil-overnight-qa/source
EnvironmentFile=/var/lib/anvil-overnight-qa/config/worker.env
EnvironmentFile=/var/lib/anvil-overnight-qa/config/app.env
ExecStart=/opt/anvil-overnight-qa/backend/bin/python /opt/anvil-overnight-qa/model-worker.py {source_sha256}
BindPaths=/var/lib/anvil-overnight-qa/artifacts:/opt/anvil-overnight-qa/source/.data/artifacts
ReadWritePaths=/opt/anvil-overnight-qa/source/.data /var/lib/anvil-qa-native /run/anvil-qa-docker
UMask=0077
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
PrivateTmp=true
Restart=no
KillMode=control-group
TimeoutStopSec=180
[Install]
WantedBy=multi-user.target
"""


if __name__ == "__main__":
    import sys

    if socket.gethostname() != "anvil-overnight-qa-20261110" or os.getuid() != 10001:
        raise ValueError("Exact QA host worker identity required")
    executable = "/opt/anvil-overnight-qa/backend/bin/python"
    os.execve(
        executable, [executable, "-m", "anvil.harbor_worker"], environment(os.environ, sys.argv[1])
    )
