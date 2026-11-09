"""Generate fresh fictional-demo configuration only; never deploy or approve.

Secret material is supplied separately and written only to private files. No cloud,
Docker, SQL, user activation, key generation or filesystem ownership changes occur.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import quote
from uuid import UUID
from staging_compose import render_demo

SECRET_KEYS = {
    "db_owner", "db_app", "db_worker", "db_identity", "neo4j", "session",
    "oidc_client", "keycloak_admin", "invited_password", "evaluator_login",
}
IMAGE_KEYS = {"backend", "web", "postgres", "neo4j", "keycloak", "caddy"}
ROOT = "/opt/anvil"
DATA = "/var/lib/anvil-staging-demo"
NATIVE_IMAGE = "python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e"
OLD_HOSTS = {"anvil-34-36-217-66.sslip.io", "auth-34-36-217-66.sslip.io"}


def validate(c, secrets):
    if not isinstance(c, dict) or c.get("mode") != "fictional_demo_preparation":
        raise ValueError("Explicit fictional preparation contract required")
    if c.get("project") != "adi-anvil-mvp-2026" or c.get("root") != ROOT:
        raise ValueError("Only the reviewed new staging target/root is supported")
    if c.get("cloud_service_account") is not None or c.get("runtime_cloud_credentials") is not False:
        raise ValueError("Runtime cloud identity/credentials forbidden")
    if c.get("native_fixture_image") != NATIVE_IMAGE:
        raise ValueError("Exact separately approved native fixture image binding required")
    for key in ("web_host", "auth_host"):
        host = c.get(key)
        if not isinstance(host, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", host) or host in OLD_HOSTS or host.endswith(".localhost"):
            raise ValueError("Explicit distinct safe DNS hostnames required")
    if c["web_host"] == c["auth_host"]:
        raise ValueError("Application and identity hostnames must differ")
    if c.get("issuer") != f"https://{c['auth_host']}/realms/anvil-staging-demo":
        raise ValueError("Issuer must bind the new realm/hostname exactly")
    for key, length in (("source_sha", 40), ("source_manifest_sha256", 64), ("reviewed_invitation_sha256", 64)):
        if not re.fullmatch(rf"[0-9a-f]{{{length}}}", c.get(key, "")):
            raise ValueError("Exact source and invitation bindings required")
    images = c.get("images")
    if not isinstance(images, dict) or set(images) != IMAGE_KEYS or any(not re.fullmatch(r"[A-Za-z0-9./:_-]+@sha256:[0-9a-f]{64}", image) for image in images.values()):
        raise ValueError("Six exact immutable core image references required")
    identity = c.get("identity", {})
    if identity.get("origin") != "real_invited_oidc_identity":
        raise ValueError("Explicit real invited OIDC identity origin required")
    for key in ("user_id", "subject", "organization_id", "project_id"):
        if str(UUID(identity.get(key, ""))) != identity[key]:
            raise ValueError("Explicit canonical identity UUIDs required")
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+", identity.get("email", "")):
        raise ValueError("Explicit invited-user email required")
    if not isinstance(identity.get("name"), str) or not identity["name"].strip() or any(ch in identity["name"] for ch in "\r\n\x00"):
        raise ValueError("Explicit invited-user display name required")
    for key in ("organization_name", "project_name"):
        if not isinstance(identity.get(key), str) or not identity[key].strip() or any(ch in identity[key] for ch in "\r\n\x00"):
            raise ValueError("Explicit organization/project display names required")
    if type(c.get("fictional_benchmark_demo", False)) is not bool:
        raise ValueError("Demo switch must be an explicit boolean")
    if type(c.get("activate_invited_user", False)) is not bool:
        raise ValueError("Account activation must be an explicit boolean")
    if c.get("activate_invited_user", False) and not re.fullmatch(r"[0-9a-f]{64}", c.get("reviewed_account_activation_sha256", "")):
        raise ValueError("Separate reviewed account-activation reference required")
    if not isinstance(secrets, dict) or set(secrets) != SECRET_KEYS or any(not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", v) for v in secrets.values()):
        raise ValueError("Exactly ten separate safe secret values of at least32 characters required")
    if len(set(secrets.values())) != len(secrets):
        raise ValueError("Secret values must be distinct")
    refs = c.get("secret_references", {})
    if not isinstance(refs, dict) or set(refs) != SECRET_KEYS or any(not re.fullmatch(r"projects/adi-anvil-mvp-2026/secrets/anvil-staging-demo-[a-z0-9-]+", ref) for ref in refs.values()) or len(set(refs.values())) != len(refs):
        raise ValueError("Distinct new staging-only secret references required")


def generate(c, secrets, output):
    """Write a new owned private directory; return public status only."""
    validate(c, secrets)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be fresh; existing paths are never overwritten")
    for parent in output.parents:
        if parent.is_symlink():
            raise ValueError("Output parent paths cannot be symlinks")
    output.mkdir(mode=0o700)

    def write(name, data):
        if not isinstance(data, str):
            data = json.dumps(data, indent=2, sort_keys=True) + "\n"
        fd = os.open(output/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(data)

    def env(name, values):
        assert all("\n" not in str(v) and "\r" not in str(v) for v in values.values())
        write(name, "".join(f"{k}={v}\n" for k, v in values.items()))

    web = "https://" + c["web_host"]
    ds = lambda role, secret, host="postgres", port=5432: f"postgresql://{role}:{quote(secret,safe='')}@{host}:{port}/anvil"
    common = {"ANVIL_ROOT": "/app", "ANVIL_ENV": "cloud", "WEB_ORIGIN": web,
              "OIDC_ISSUER": c["issuer"], "ANVIL_SESSION_KEY": secrets["session"],
              "ANVIL_FIXTURE_MODE": "true", "ANVIL_LIVE_PROVIDERS_ENABLED": "false",
              "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "false", "ANVIL_IMPORT_GENERATION_ENABLED": "false",
              "ANVIL_REAL_EMAIL_ENABLED": "false", "ANVIL_SUPPORT_VERTEX_PROJECT": "",
              "ANVIL_SUPPORT_MODEL": "", "LANGSMITH_TRACING": "false",
              "ANVIL_TEST_HARBOR": "0", "ANVIL_BENCHMARK_OFFLINE_ENABLED": "false",
              "ANVIL_BENCHMARK_ENABLED": "false", "ANVIL_BENCHMARK_EVALUATION_ENABLED": "false"}
    api = {**common, "DATABASE_URL": ds("anvil_app", secrets["db_app"]),
           "OIDC_CLIENT_ID": "anvil-web-staging-demo", "OIDC_CLIENT_SECRET": secrets["oidc_client"],
           "NEO4J_URI": "bolt://neo4j:7687", "ANVIL_NEO4J_PASSWORD": secrets["neo4j"],
           "ARTIFACT_ROOT": "/app/.data/artifacts", "ANVIL_BENCHMARK_VAULT_ROOT": "/app/.data/benchmark-vault"}
    if c.get("fictional_benchmark_demo", False):
        for key in ("ANVIL_BENCHMARK_ENABLED", "ANVIL_BENCHMARK_EVALUATION_ENABLED", "ANVIL_BENCHMARK_OFFLINE_ENABLED"):
            api[key] = "true"
    env("app.env", api)
    worker_ds = ds("anvil_worker", secrets["db_worker"])
    env("worker.env", {**common, "DATABASE_URL": worker_ds, "WORKER_DATABASE_URL": worker_ds,
                       "ARTIFACT_ROOT": "/app/.data/artifacts", "NEO4J_URI": "bolt://neo4j:7687", "ANVIL_NEO4J_PASSWORD": secrets["neo4j"]})
    env("migrate.env", {**common, "MIGRATION_DATABASE_URL": ds("anvil_staging_migration", secrets["db_owner"]),
                        "ANVIL_DB_APP_PASSWORD": secrets["db_app"], "ANVIL_DB_WORKER_PASSWORD": secrets["db_worker"]})
    env("postgres.env", {"POSTGRES_DB": "anvil", "POSTGRES_USER": "anvil_staging_migration", "POSTGRES_PASSWORD": secrets["db_owner"], "POSTGRES_INITDB_ARGS": "--auth-host=scram-sha-256", "KEYCLOAK_DB_PASSWORD": secrets["db_identity"]})
    env("neo4j.env", {"NEO4J_AUTH": "neo4j/" + secrets["neo4j"]})
    env("keycloak.env", {"KC_DB": "postgres", "KC_DB_URL": "jdbc:postgresql://postgres:5432/anvil_staging_identity",
                         "KC_DB_USERNAME": "anvil_staging_identity", "KC_DB_PASSWORD": secrets["db_identity"],
                         "KC_HOSTNAME": "https://" + c["auth_host"], "KC_HOSTNAME_ADMIN": "http://127.0.0.1:8180",
                         "KC_HTTP_ENABLED": "true", "KC_PROXY_HEADERS": "xforwarded", "KC_HEALTH_ENABLED": "true",
                         "KC_BOOTSTRAP_ADMIN_USERNAME": "anvil-staging-bootstrap", "KC_BOOTSTRAP_ADMIN_PASSWORD": secrets["keycloak_admin"]})
    env("web.env", {"NODE_ENV": "production", "NEXT_TELEMETRY_DISABLED": "1"})
    env("caddy.env", {"ANVIL_WEB_HOST": c["web_host"], "ANVIL_AUTH_HOST": c["auth_host"]})
    write("compose.json", render_demo(c["images"], fictional_benchmark_demo=c.get("fictional_benchmark_demo", False)))
    identity = c["identity"]
    write("realm.json", {"realm": "anvil-staging-demo", "enabled": True, "registrationAllowed": False,
          "resetPasswordAllowed": False, "sslRequired": "external", "bruteForceProtected": True,
          "passwordPolicy": "length(16) and notUsername", "clients": [{"clientId": "anvil-web-staging-demo",
          "secret": secrets["oidc_client"], "enabled": True, "publicClient": False, "standardFlowEnabled": True,
          "directAccessGrantsEnabled": False, "serviceAccountsEnabled": False,
          "redirectUris": [web + "/api/v1/auth/callback"], "webOrigins": [web],
          "attributes": {"pkce.code.challenge.method": "S256", "post.logout.redirect.uris": web + "/"}}],
          "users": [{"id": identity["subject"], "username": identity["email"], "email": identity["email"],
                     "enabled": c.get("activate_invited_user", False), "emailVerified": False, "requiredActions": ["UPDATE_PASSWORD"],
                     "credentials": [{"type": "password", "value": secrets["invited_password"], "temporary": True}]}]})
    write("Caddyfile", """{
 auto_https off
 servers {
  trusted_proxies static 130.211.0.0/22 35.191.0.0/16
  client_ip_headers X-Forwarded-For
 }
}
http://%s {
 header Strict-Transport-Security "max-age=31536000"
 header -Server
 handle /api/* {
  reverse_proxy api:8200
 }
 handle {
  reverse_proxy web:3202
 }
}
http://%s {
 @private path /admin /admin/* /metrics* /health*
 respond @private 404
 reverse_proxy keycloak:8080
}
:80 {
 handle /healthz {
  rewrite * /api/v1/health
  reverse_proxy api:8200
 }
 respond 404
}
""" % (c["web_host"], c["auth_host"]))
    write("postgres-init.sh", """#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v pw="$KEYCLOAK_DB_PASSWORD" <<'SQL'
CREATE ROLE anvil_staging_identity LOGIN PASSWORD :'pw' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
CREATE DATABASE anvil_staging_identity OWNER anvil_staging_identity;
SQL
""")
    operator = {**common, "ANVIL_ROOT": ROOT, "DATABASE_URL": ds("anvil_app", secrets["db_app"], "127.0.0.1", 5432),
                "ARTIFACT_ROOT": ROOT + "/.data/artifacts", "ANVIL_BENCHMARK_VAULT_ROOT": ROOT + "/.local/benchmark-vault",
                "ANVIL_HARBOR_DOCKER_HOST": "unix://" + ROOT + "/.local/benchmark-docker/docker.sock",
                "ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL": ds("anvil_staging_benchmark_evaluator_login", secrets["evaluator_login"], "127.0.0.1", 5432) + "?options=-c%20role%3Danvil_benchmark_evaluator"}
    env("operator.env", operator)  # Native/offline switches remain off until explicit operator activation.
    write("identity-bootstrap-contract.json", {"schema": "anvil.staging.initial-admin.v1", "target": {"database": "anvil", "host": "127.0.0.1", "port": 5432, "migration_role": "anvil_staging_migration", "gcp_project": c["project"], "vm_name": "anvil-staging-demo", "vm_id": None, "new_disk_manifest_sha256": None, "postgres_system_identifier": None},
          "identity": {"user_id": identity["user_id"], "issuer": c["issuer"], "subject": identity["subject"], "name": identity["name"], "origin": identity["origin"]},
          "organization": {"id": identity["organization_id"], "name": identity["organization_name"]},
          "project": {"id": identity["project_id"], "name": identity["project_name"]},
          "reviewed_invitation_sha256": c["reviewed_invitation_sha256"]})
    write("deployment-identity-manifest.json", {"schema": "anvil.staging.deployment-identity.proposal.v1", "state": "expected_not_observed",
          "expected": {"gcp_project": c["project"], "zone": "us-west1-a", "vm_name": "anvil-staging-demo", "new_disk_names": ["anvil-staging-demo-boot", "anvil-staging-demo-data"], "database": "anvil", "host": "127.0.0.1", "port": 5432},
          "observed": {"vm_id": None, "new_disk_ids": [], "postgres_system_identifier": None, "creation_record_sha256": None},
          "trusted_metadata_and_SQL_observer_required": True, "deployment_authorized": False})
    write("deployment-guards.json", {"deployment_authorized": False, "architecture_amendment_approved": False,
          "source_sha": c["source_sha"], "source_manifest_sha256": c["source_manifest_sha256"], "images": c["images"], "native_fixture_image": NATIVE_IMAGE,
          "secret_references": c["secret_references"], "fictional_only": True,
          "identity_bootstrap": {"automatic_apply": False, "deployment_approval_receipt_separate": True, "review_assignments_or_approvals_created": False},
          "invited_account": {"activation_requested": c.get("activate_invited_user", False), "activation_approval_reference": c.get("reviewed_account_activation_sha256"), "trusted_activation_receipt_verified": False, "email_verification_asserted": False, "role_grants_created": False},
          "core_daemon": {"socket": "unix://" + DATA + "/core-docker/docker.sock", "data_root": DATA + "/core-docker/data", "API_or_worker_mount": False},
          "native_daemon": {"socket": operator["ANVIL_HARBOR_DOCKER_HOST"], "data_root": ROOT + "/.local/benchmark-docker/data", "API_or_worker_mount": False, "fallback_to_core": False},
          "ownership": {"host_operator_uid": 10001, "API_uid": 10001, "vault_mode": "0700", "secret_files": "0600", "realm_import_owner_uid": 1000, "postgres_init_script_owner_uid": 999, "local_chown_performed": False},
          "mounts": {"API_vault": {"host": ROOT + "/.local/benchmark-vault", "container": api["ANVIL_BENCHMARK_VAULT_ROOT"]}, "API_artifacts": {"host": ROOT + "/.data/artifacts", "container": api["ARTIFACT_ROOT"]}, "operator_vault_logical": operator["ANVIL_BENCHMARK_VAULT_ROOT"], "aliases_or_symlinks": False, "worker_vault": None, "migration_vault": None},
          "storage": {"boot_disk_gib": 30, "core_state_disk_gib": 50, "vault_artifacts_native_images_on_boot": True, "minimum_boot_free_gib_before_native_admission": 10, "stop_on_low_space": True, "admission_enforcement_implementation_required": True},
          "operator": {"automatic_start": False, "maximum_trials_per_invocation": 1, "exclusive_host_lock_required": True, "root_equivalent_trust_acceptance_required": True},
          "migration_owner": {"role": "anvil_staging_migration", "initial_POSTGRES_USER_is_superuser": True, "use": "initial_migrations_and_reviewed_identity_bootstrap_only", "never_API_worker_evaluator": True, "privilege_secret_isolation_retention_and_user_approval_required": True, "post_migration_hardening_proven": False, "automatic_role_hardening": False},
          "required_proofs": ["fresh_exact_host_and_no_cloud_identity", "DNS_TLS_and_invited_user", "trusted_VM_disk_cluster_observer_not_caller_claim", "new_staging_secret_material_provenance", "migration_owner_privilege_and_bootstrap_guard_compatibility", "runtime_owner_non_symlink_mounts", "evaluator_wrapper_current_user_SQL_proof", "no_native_daemon_fallback", "exclusive_trial_lock", "independent_boot_browser_native_checks", "deployment_and_architecture_approval"]})
    return {"generated": True, "deployment_authorized": False, "secret_values_printed": False, "files": sorted(p.name for p in output.iterdir())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--secrets-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        info = args.secrets_file.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or any(p.is_symlink() for p in [args.secrets_file, *args.secrets_file.absolute().parents]):
            raise ValueError("Secret input must be owner-only and non-symlink")
        result = generate(json.loads(args.contract.read_text()), json.loads(args.secrets_file.read_text()), args.output)
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"generated": False, "deployment_authorized": False, "error": "Invalid or incomplete private staging preparation contract"}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
