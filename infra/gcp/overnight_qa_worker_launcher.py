"""Host Run-worker entry: scoped config, no inherited provider/migration keys."""

import os
import re
import socket
import sys
from urllib.parse import urlsplit, urlunsplit


def environment(values, source_sha256):
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("Exact source digest required")
    dsn = urlsplit(values["WORKER_DATABASE_URL"])
    if (
        dsn.scheme != "postgresql"
        or dsn.username != "anvil_worker"
        or dsn.path != "/anvil"
        or dsn.hostname != "postgres"
        or dsn.port != 5432
    ):
        raise ValueError("Only the scoped QA worker identity is allowed")
    session = values["ANVIL_SESSION_KEY"]
    if len(session) < 32:
        raise ValueError("Qualified cloud session configuration required")
    userinfo = dsn.netloc.rsplit("@", 1)[0]
    result = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/home/anvilqa",
        "ANVIL_ENV": "cloud",
        "ANVIL_ROOT": "/opt/anvil-overnight-qa/source",
        "WEB_ORIGIN": "https://anvil-qa.127.0.0.1.sslip.io:8443",
        "OIDC_ISSUER": "https://auth-anvil-qa.127.0.0.1.sslip.io:8443/realms/anvil-overnight-qa",
        "ANVIL_SESSION_KEY": session,
        "WORKER_DATABASE_URL": urlunsplit(dsn._replace(netloc=userinfo + "@127.0.0.1:55432")),
        "ANVIL_ENVIRONMENT_QA_ENABLED": "true",
        "ANVIL_ENVIRONMENT_QA_SOURCE_SHA256": source_sha256,
        "ANVIL_ENVIRONMENT_NATIVE_ENABLED": "true",
        "ANVIL_ENVIRONMENT_OPENENV_ENABLED": "true",
        "ANVIL_ENVIRONMENT_HARBOR_PYTHON": "/opt/anvil-overnight-qa/harbor/bin/python",
        "ANVIL_ENVIRONMENT_OPENENV_PYTHON": "/opt/anvil-overnight-qa/openenv/bin/python",
        "ANVIL_HARBOR_DOCKER_HOST": "unix:///run/anvil-qa-docker/docker.sock",
        "ANVIL_ENVIRONMENT_NATIVE_TMP_ROOT": "/var/lib/anvil-qa-native",
    }
    for key in (
        "ANVIL_LIVE_PROVIDERS_ENABLED",
        "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED",
        "ANVIL_IMPORT_GENERATION_ENABLED",
        "ANVIL_GENERATION_ENABLED",
        "ANVIL_REAL_EMAIL_ENABLED",
    ):
        result[key] = "false"
    if values.get("ANVIL_QA_ACCEPTANCE_CONTROLS_ENABLED") == "true":
        result["ANVIL_QA_ACCEPTANCE_CONTROLS_ENABLED"] = "true"
    if values.get("ANVIL_BUSINESS_QA_ENABLED") == "true":
        bound = values.get("ANVIL_BUSINESS_QA_SOURCE_SHA256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", bound):
            raise ValueError("Exact fictional business QA source required")
        result.update(ANVIL_BUSINESS_QA_ENABLED="true", ANVIL_BUSINESS_QA_SOURCE_SHA256=bound)
    return result


if __name__ == "__main__":
    if socket.gethostname() != "anvil-overnight-qa-20261110" or os.getuid() != 10001:
        raise ValueError("Exact QA host worker identity required")
    executable = "/opt/anvil-overnight-qa/backend/bin/python"
    os.execve(
        executable,
        [executable, "-m", "anvil.benchmark_run_worker"],
        environment(os.environ, sys.argv[1]),
    )
