"""Fresh QA-only runtime configuration. Never prints generated secret values."""

import json
import os
import secrets
import socket
import subprocess
from pathlib import Path

DATA = Path("/var/lib/anvil-overnight-qa")
WEB = "https://anvil-qa.127.0.0.1.sslip.io:8443"
AUTH = "https://auth-anvil-qa.127.0.0.1.sslip.io:8443"
REALM = "anvil-overnight-qa"
TAGS = {
    "backend": "anvil-overnight-qa-combined:c08c168",
    "web": "anvil-overnight-qa-combined:c08c168",
    "postgres": "postgres:17.6-bookworm@sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3",
    "neo4j": "neo4j:5.26.12-community@sha256:9f75e8df4325a24f00fdd7a8c0bcce650a58375049b1058e496e8b43d6c36b37",
    "keycloak": "quay.io/keycloak/keycloak:26.3.5@sha256:357829ec7c4693397533035092ad13b0644bcc95ded311f33a3738c4d9e9bdba",
    "caddy": "caddy:2.10.2",
}


def generate():
    if socket.gethostname() != "anvil-overnight-qa-20261110" or os.getuid() != 0:
        raise ValueError("Exact owned QA host/root required")
    config = DATA / "config"
    config.mkdir(mode=0o700, exist_ok=False)
    passwords = {
        name: secrets.token_urlsafe(48)
        for name in ("owner", "app", "worker", "identity", "neo4j", "session", "client", "keycloak")
    }
    images = {}
    for name, tag in TAGS.items():
        image = json.loads(subprocess.check_output(["docker", "image", "inspect", tag]))[0]
        if image["Os"] != "linux" or image["Architecture"] != "amd64":
            raise ValueError("Exact native Linux image required")
        images[name] = image["Id"]

    def write(name, value):
        data = value if isinstance(value, str) else json.dumps(value)
        fd = os.open(config / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(data)

    def env(name, values):
        assert all("\n" not in str(v) for v in values.values())
        write(name + ".env", "".join(f"{k}={v}\n" for k, v in values.items()))

    def ds(role, secret):
        return f"postgresql://{role}:{passwords[secret]}@postgres:5432/anvil"

    common = {
        "ANVIL_ENV": "cloud",
        "ANVIL_ROOT": "/app",
        "WEB_ORIGIN": WEB,
        "OIDC_ISSUER": AUTH + "/realms/" + REALM,
        "ANVIL_SESSION_KEY": passwords["session"],
        "ANVIL_LIVE_PROVIDERS_ENABLED": "false",
        "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "false",
        "ANVIL_REAL_EMAIL_ENABLED": "false",
        "ANVIL_IMPORT_GENERATION_ENABLED": "false",
        "ANVIL_GENERATION_ENABLED": "false",
        "LANGSMITH_TRACING": "false",
    }
    env(
        "postgres",
        {
            "POSTGRES_USER": "anvil_migration",
            "POSTGRES_PASSWORD": passwords["owner"],
            "POSTGRES_DB": "anvil",
            "POSTGRES_INITDB_ARGS": "--auth-host=scram-sha-256",
            "KEYCLOAK_DB_PASSWORD": passwords["identity"],
        },
    )
    env(
        "migrate",
        {
            **common,
            "MIGRATION_DATABASE_URL": ds("anvil_migration", "owner"),
            "ANVIL_DB_APP_PASSWORD": passwords["app"],
            "ANVIL_DB_WORKER_PASSWORD": passwords["worker"],
        },
    )
    env(
        "app",
        {
            **common,
            "DATABASE_URL": ds("anvil_app", "app"),
            "OIDC_CLIENT_ID": "anvil-qa-web",
            "OIDC_CLIENT_SECRET": passwords["client"],
            "NEO4J_URI": "bolt://neo4j:7687",
            "ANVIL_NEO4J_PASSWORD": passwords["neo4j"],
            "ARTIFACT_ROOT": "/app/.data/artifacts",
            "ANVIL_BENCHMARK_VAULT_ROOT": "/app/.data/benchmark-vault",
            "ANVIL_CREDENTIAL_STORE_PROFILE": "qa",
        },
    )
    env(
        "worker",
        {
            **common,
            "DATABASE_URL": ds("anvil_worker", "worker"),
            "WORKER_DATABASE_URL": ds("anvil_worker", "worker"),
            "NEO4J_URI": "bolt://neo4j:7687",
            "ANVIL_NEO4J_PASSWORD": passwords["neo4j"],
            "ARTIFACT_ROOT": "/app/.data/artifacts",
        },
    )
    env("neo4j", {"NEO4J_AUTH": "neo4j/" + passwords["neo4j"]})
    env(
        "keycloak",
        {
            "KC_DB": "postgres",
            "KC_DB_URL": "jdbc:postgresql://postgres:5432/keycloak",
            "KC_DB_USERNAME": "keycloak",
            "KC_DB_PASSWORD": passwords["identity"],
            "KC_HOSTNAME": AUTH,
            "KC_HTTP_ENABLED": "true",
            "KC_PROXY_HEADERS": "xforwarded",
            "KC_BOOTSTRAP_ADMIN_USERNAME": "qa-bootstrap",
            "KC_BOOTSTRAP_ADMIN_PASSWORD": passwords["keycloak"],
        },
    )
    write(
        "realm.json",
        {
            "realm": REALM,
            "enabled": True,
            "registrationAllowed": False,
            "sslRequired": "all",
            "bruteForceProtected": True,
            "clients": [
                {
                    "clientId": "anvil-qa-web",
                    "secret": passwords["client"],
                    "enabled": True,
                    "publicClient": False,
                    "standardFlowEnabled": True,
                    "directAccessGrantsEnabled": False,
                    "serviceAccountsEnabled": False,
                    "redirectUris": [WEB + "/api/v1/auth/callback"],
                    "webOrigins": [WEB],
                    "attributes": {"pkce.code.challenge.method": "S256"},
                }
            ],
            "users": [],
        },
    )
    write(
        "postgres-init.sh",
        """#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v pw="$KEYCLOAK_DB_PASSWORD" <<'SQL'
CREATE ROLE keycloak LOGIN PASSWORD :'pw' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE keycloak OWNER keycloak;
SQL
""",
    )
    write(
        "Caddyfile",
        """{
 admin off
}
https://anvil-qa.127.0.0.1.sslip.io:8443 {
 tls internal
 handle /api/* {
  reverse_proxy api:8200
 }
 handle {
  reverse_proxy web:3202
 }
}
https://auth-anvil-qa.127.0.0.1.sslip.io:8443 {
 tls internal
 @private path /admin /admin/* /metrics* /health*
 respond @private 404
 reverse_proxy keycloak:8080
}
""",
    )
    os.chown(config / "realm.json", 1000, 1000)
    os.chmod(config / "postgres-init.sh", 0o644)
    mounts = {
        "postgres": [
            f"{DATA}/postgres:/var/lib/postgresql/data",
            f"{config}/postgres-init.sh:/docker-entrypoint-initdb.d/10-identity.sh:ro",
        ],
        "neo4j": [f"{DATA}/neo4j:/data"],
        "keycloak": [f"{config}/realm.json:/opt/keycloak/data/import/qa.json:ro"],
        "api": [
            f"{DATA}/artifacts:/app/.data/artifacts",
            f"{DATA}/benchmark-vault:/app/.data/benchmark-vault",
        ],
        "worker": [f"{DATA}/artifacts:/app/.data/artifacts"],
        "caddy": [f"{config}/Caddyfile:/etc/caddy/Caddyfile:ro", f"{DATA}/caddy:/data"],
    }
    services = {}
    for name, image, env_name in (
        ("postgres", "postgres", "postgres"),
        ("neo4j", "neo4j", "neo4j"),
        ("keycloak", "keycloak", "keycloak"),
        ("migrate", "backend", "migrate"),
        ("api", "backend", "app"),
        ("worker", "backend", "worker"),
        ("web", "web", None),
        ("caddy", "caddy", None),
    ):
        service = {
            "image": images[image],
            "pull_policy": "never",
            "restart": "no",
            "networks": ["qa"],
            "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}},
        }
        if env_name:
            service["env_file"] = [str(config / (env_name + ".env"))]
        if name in mounts:
            service["volumes"] = mounts[name]
        services[name] = service
    services["keycloak"]["command"] = ["start", "--import-realm"]
    services["migrate"]["command"] = ["python", "-m", "anvil.cli", "migrate"]
    services["api"]["command"] = [
        "python",
        "-m",
        "uvicorn",
        "anvil.api:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8200",
        "--no-access-log",
    ]
    services["worker"]["command"] = ["python", "-m", "anvil.worker"]
    services["web"].update(
        working_dir="/app/apps/web",
        command=["node_modules/.bin/next", "start", "--hostname", "0.0.0.0", "--port", "3202"],
        environment={"NODE_ENV": "production", "NEXT_TELEMETRY_DISABLED": "1"},
    )
    services["caddy"]["ports"] = ["127.0.0.1:8443:8443"]
    services["caddy"]["networks"] = {
        "qa": {"aliases": ["anvil-qa.127.0.0.1.sslip.io", "auth-anvil-qa.127.0.0.1.sslip.io"]}
    }
    services["postgres"]["ports"] = ["127.0.0.1:55432:5432"]
    for name in ("artifacts", "benchmark-vault"):
        path = DATA / name
        path.mkdir(mode=0o700)
        os.chown(path, 10001, 10001)
    write(
        "compose.json",
        {
            "name": "anvil-overnight-qa",
            "services": services,
            "networks": {"qa": {"name": "anvil-overnight-qa"}},
        },
    )
    (DATA / "runtime-public.json").write_text(
        json.dumps(
            {
                "images": images,
                "web_origin": WEB,
                "oidc_issuer": AUTH + "/realms/" + REALM,
                "provider_calls": 0,
                "identity_users": 0,
                "source": "c08c168",
                "credentials_activated": False,
            }
        )
    )
    print("Fresh private QA configuration generated; no identities or approvals fabricated.")


if __name__ == "__main__":
    generate()
