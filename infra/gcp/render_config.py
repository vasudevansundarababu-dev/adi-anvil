"""Render owner-only runtime files from secret values. Used on the VM and in local rehearsal.

Usage: render_config.py <config-dir> <web-host> <auth-host>
Secret values are read from environment variables named in SECRETS; nothing is printed.
"""

import json
import os
import sys
from pathlib import Path

SECRETS = [
    "ANVIL_DB_OWNER_PASSWORD",
    "ANVIL_DB_APP_PASSWORD",
    "ANVIL_DB_WORKER_PASSWORD",
    "ANVIL_NEO4J_PASSWORD",
    "ANVIL_SESSION_KEY",
    "OIDC_CLIENT_SECRET",
    "ANVIL_OIDC_ADMIN_PASSWORD",
    "KEYCLOAK_DB_PASSWORD",
]


def write(path: Path, text: str, uid=None):
    path.unlink(missing_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    if uid is not None:
        os.chown(path, uid, 0)


def env_file(values):
    for k, v in values.items():
        if "\n" in v or not v:
            raise SystemExit(f"Invalid value for {k}")
    return "".join(f"{k}={v}\n" for k, v in values.items())


def main():
    folder, web_host, auth_host = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    s = {name: os.environ[name] for name in SECRETS}
    web, issuer = f"https://{web_host}", f"https://{auth_host}/realms/anvil"
    db = "postgres:5432/anvil"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    write(
        folder / "app.env",
        env_file(
            {
                "ANVIL_ENV": "cloud",
                "ANVIL_FIXTURE_MODE": "true",
                "ANVIL_LIVE_PROVIDERS_ENABLED": "false",
                "ANVIL_REAL_EMAIL_ENABLED": "false",
                "WEB_ORIGIN": web,
                "OIDC_ISSUER": issuer,
                "OIDC_CLIENT_ID": "anvil-web",
                "OIDC_CLIENT_SECRET": s["OIDC_CLIENT_SECRET"],
                "ANVIL_SESSION_KEY": s["ANVIL_SESSION_KEY"],
                "DATABASE_URL": f"postgresql://anvil_app:{s['ANVIL_DB_APP_PASSWORD']}@{db}",
                "WORKER_DATABASE_URL": f"postgresql://anvil_worker:{s['ANVIL_DB_WORKER_PASSWORD']}@{db}",
                "NEO4J_URI": "bolt://neo4j:7687",
                "ANVIL_NEO4J_PASSWORD": s["ANVIL_NEO4J_PASSWORD"],
                "ARTIFACT_ROOT": ".data/artifacts",
                "LANGSMITH_TRACING": "false",
                # Support Bot (Claude on Vertex AI, like ADI Praxis); blank = local help pack.
                **(
                    {
                        "ANVIL_SUPPORT_VERTEX_PROJECT": os.environ["ANVIL_SUPPORT_VERTEX_PROJECT"],
                        "ANVIL_SUPPORT_VERTEX_REGION": "global",
                        "ANVIL_SUPPORT_MODEL": "claude-sonnet-5",
                    }
                    if os.environ.get("ANVIL_SUPPORT_VERTEX_PROJECT")
                    else {}
                ),
            }
        ),
    )
    write(
        folder / "migrate.env",
        env_file(
            {
                "MIGRATION_DATABASE_URL": f"postgresql://anvil_migration:{s['ANVIL_DB_OWNER_PASSWORD']}@{db}",
                "ANVIL_DB_APP_PASSWORD": s["ANVIL_DB_APP_PASSWORD"],
                "ANVIL_DB_WORKER_PASSWORD": s["ANVIL_DB_WORKER_PASSWORD"],
            }
        ),
    )
    write(
        folder / "ops.env",
        env_file(
            {
                "KEYCLOAK_ADMIN_URL": "http://keycloak:8080",
                "KEYCLOAK_ADMIN_USER": "anvil-bootstrap",
                "ANVIL_OIDC_ADMIN_PASSWORD": s["ANVIL_OIDC_ADMIN_PASSWORD"],
            }
        ),
    )
    write(
        folder / "postgres.env",
        env_file(
            {
                "POSTGRES_DB": "anvil",
                "POSTGRES_USER": "anvil_migration",
                "POSTGRES_PASSWORD": s["ANVIL_DB_OWNER_PASSWORD"],
                "KEYCLOAK_DB_PASSWORD": s["KEYCLOAK_DB_PASSWORD"],
            }
        ),
    )
    write(folder / "neo4j.env", env_file({"NEO4J_AUTH": f"neo4j/{s['ANVIL_NEO4J_PASSWORD']}"}))
    write(
        folder / "keycloak.env",
        env_file(
            {
                "KC_DB_PASSWORD": s["KEYCLOAK_DB_PASSWORD"],
                "KC_BOOTSTRAP_ADMIN_USERNAME": "anvil-bootstrap",
                "KC_BOOTSTRAP_ADMIN_PASSWORD": s["ANVIL_OIDC_ADMIN_PASSWORD"],
            }
        ),
    )
    realm = {
        "realm": "anvil",
        "enabled": True,
        "registrationAllowed": False,
        "resetPasswordAllowed": False,
        "sslRequired": "external",
        "loginWithEmailAllowed": True,
        "bruteForceProtected": True,
        "passwordPolicy": "length(12) and notUsername",
        "clients": [
            {
                "clientId": "anvil-web",
                "secret": s["OIDC_CLIENT_SECRET"],
                "enabled": True,
                "publicClient": False,
                "standardFlowEnabled": True,
                "directAccessGrantsEnabled": False,
                "redirectUris": [web + "/api/v1/auth/callback"],
                "webOrigins": [web],
                "attributes": {
                    "pkce.code.challenge.method": "S256",
                    "post.logout.redirect.uris": web + "/",
                },
            }
        ],
        "users": [],
    }
    # Keycloak runs as uid 1000; it alone needs to read the realm import.
    write(folder / "realm.json", json.dumps(realm), uid=1000 if os.geteuid() == 0 else None)


if __name__ == "__main__":
    main()
