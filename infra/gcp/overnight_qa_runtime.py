"""Additive private QA wiring. Pure rendering; no cloud or service execution."""

import re

from staging_compose import render_demo

WEB_ORIGIN = "https://anvil-qa.127.0.0.1.sslip.io:8443"
OIDC_ISSUER = "https://auth-anvil-qa.127.0.0.1.sslip.io:8443/realms/anvil-overnight-qa"


def render(images, source_sha256):
    if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("Exact environment execution source digest required")
    result = render_demo(images)
    root = "/var/lib/anvil-overnight-qa"
    services = result["services"]
    # Distinct paths and Docker network; production and historical demos excluded.
    for service in services.values():
        service["env_file"] = [
            path.replace("/var/lib/anvil-staging-demo", root) for path in service["env_file"]
        ]
        if "volumes" in service:
            service["volumes"] = [
                mount.replace("/var/lib/anvil-staging-demo", root)
                .replace("/opt/anvil/", "/opt/anvil-overnight-qa/")
                .replace("/import/anvil-staging-demo.json", "/import/anvil-overnight-qa.json")
                for mount in service["volumes"]
            ]
    result["name"] = "anvil-overnight-qa"
    result["networks"]["staging"]["name"] = "anvil-overnight-qa"
    services["caddy"]["ports"] = ["127.0.0.1:8443:8443"]
    services["caddy"]["networks"] = {"staging": {"aliases": ["anvil-qa.127.0.0.1.sslip.io", "auth-anvil-qa.127.0.0.1.sslip.io"]}}
    services["postgres"]["ports"] = ["127.0.0.1:55432:5432"]
    services["api"]["environment"].update(
        {
            "ANVIL_ENVIRONMENT_QA_ENABLED": "true",
            "ANVIL_ENVIRONMENT_QA_SOURCE_SHA256": source_sha256,
            "ANVIL_CREDENTIAL_STORE_PROFILE": "qa",
        }
    )
    # The Run worker executes on the host with separate locked interpreters and
    # the dedicated actor daemon. Neither API nor ordinary worker gets its socket.
    result["x-anvil-preparation"] = {
        "target": "anvil-overnight-qa",
        "run_worker": "host-systemd",
        "migration_contract": "all repository migrations through069 and LangGraph checkpoints",
        "paid_execution_enabled": False,
        "cloud_qualification": False,
        "source_sha256": source_sha256,
    }
    return result


def run_worker_unit(source_sha256):
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("Exact environment execution source digest required")
    return f"""[Unit]
Description=Anvil isolated QA durable Run worker
After=docker.service network-online.target
[Service]
Type=simple
User=anvilqa
Group=anvilqa
WorkingDirectory=/opt/anvil-overnight-qa/source
EnvironmentFile=/var/lib/anvil-overnight-qa/config/run-worker.env
ExecStart=/usr/bin/env -i PATH=/usr/bin:/bin ANVIL_ENV=cloud ANVIL_ROOT=/opt/anvil-overnight-qa/source WEB_ORIGIN={WEB_ORIGIN} OIDC_ISSUER={OIDC_ISSUER} ANVIL_SESSION_KEY=${{ANVIL_SESSION_KEY}} WORKER_DATABASE_URL=${{WORKER_DATABASE_URL}} ANVIL_ENVIRONMENT_QA_ENABLED=true ANVIL_ENVIRONMENT_QA_SOURCE_SHA256={source_sha256} ANVIL_LIVE_PROVIDERS_ENABLED=false ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED=false ANVIL_IMPORT_GENERATION_ENABLED=false ANVIL_GENERATION_ENABLED=false ANVIL_REAL_EMAIL_ENABLED=false ANVIL_ENVIRONMENT_NATIVE_ENABLED=true ANVIL_ENVIRONMENT_OPENENV_ENABLED=true ANVIL_ENVIRONMENT_HARBOR_PYTHON=/opt/anvil-overnight-qa/harbor/bin/python ANVIL_ENVIRONMENT_OPENENV_PYTHON=/opt/anvil-overnight-qa/openenv/bin/python ANVIL_HARBOR_DOCKER_HOST=unix:///run/anvil-qa-docker/docker.sock /opt/anvil-overnight-qa/backend/bin/python -m anvil.benchmark_run_worker
Restart=no
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/opt/anvil-overnight-qa/source/.data /opt/anvil-overnight-qa/source/.local /run/anvil-qa-docker
TimeoutStopSec=120
KillMode=control-group
[Install]
WantedBy=multi-user.target
"""
