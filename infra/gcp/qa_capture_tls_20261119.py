"""Explicit QA-only PostgreSQL TLS enable/reload with exact rollback.

No database/container replacement, HBA/role/grant changes, migration, model call
or qualification publication. Run only as the authorized root QA operator.
Certificates/private configuration remain on the VM; output is safe metadata.
"""

import hashlib
import ipaddress
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path("/var/lib/anvil-qa-v1")
CONFIG_SHA = "4d566c5faae44090d296360347729e4ac846ae12e5055aca35cd740ed0f18e84"
API = "ce3628a2e896a83bac90ea842dc25471f7694c147c8ee58d6ab7eb0da20c81f1"
POSTGRES = "anvil-qa-v1-postgres-1"
CA_DESTINATION = "/tmp/anvil-capture-ca-20261119.pem"


def run(*args, data=None):
    result = subprocess.run(args, input=data, capture_output=True, timeout=30)
    if result.returncode:
        # Do not reflect private configuration or credentials in exceptions.
        raise RuntimeError("QA TLS operator subprocess failed")
    return result.stdout


def sql(statement):
    return run("docker", "exec", "-i", POSTGRES, "sh", "-c",
               'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -A -t -v ON_ERROR_STOP=1',
               data=statement.encode()).decode().strip()


def main():
    if os.geteuid() != 0 or os.uname().nodename != "anvil-qa-v1":
        raise ValueError("Authorized QA root operator only")
    os.umask(0o077)
    config = ROOT / "config/compose-app.json"
    if hashlib.sha256(config.read_bytes()).hexdigest() != CONFIG_SHA:
        raise ValueError("Serving configuration changed; reconcile before TLS operation")
    api, pg = json.loads(run("docker", "inspect", API, POSTGRES))
    if not api["State"]["Running"] or not pg["State"]["Running"]:
        raise ValueError("Actual current serving API and database required")
    environment = dict(value.split("=", 1) for value in api["Config"]["Env"])
    host = urlsplit(environment["DATABASE_URL"]).hostname
    if host != "postgres":
        raise ValueError("Existing exact QA postgres identity required")
    networks = set(api["NetworkSettings"]["Networks"]) & set(pg["NetworkSettings"]["Networks"])
    if len(networks) != 1:
        raise ValueError("Exactly one existing shared QA network required")
    address = str(ipaddress.ip_address(pg["NetworkSettings"]["Networks"][networks.pop()]["IPAddress"]))
    volumes = [m for m in pg["Mounts"] if m["Destination"] == "/var/lib/postgresql/data"]
    if len(volumes) != 1 or volumes[0]["Source"] != str(ROOT / "postgres"):
        raise ValueError("Existing persistent database path required")
    if sql("SHOW ssl;") != "off" or sql("SELECT max(version) FROM anvil.schema_versions;") != "133":
        raise ValueError("Exact pre-TLS schema133 database state required")
    if sql("SELECT context FROM pg_settings WHERE name='ssl';") != "sighup":
        raise ValueError("TLS must support reload without restart")
    if sql("SHOW data_directory;") != "/var/lib/postgresql/data":
        raise ValueError("Exact actual PostgreSQL data directory required")
    original_min = sql("SHOW ssl_min_protocol_version;")
    original_postmaster = sql("SELECT pg_postmaster_start_time();")
    if run("docker", "exec", API, "test", "!", "-e", CA_DESTINATION):
        raise ValueError("Unexpected pre-existing public CA destination")
    backup = ROOT / "backups/capture-tls-20261119-v1"
    backup.mkdir(mode=0o700)
    os.chmod(backup, 0o700)
    auto = ROOT / "postgres/postgresql.auto.conf"
    shutil.copy2(auto, backup / "postgresql.auto.conf")
    os.chmod(backup / "postgresql.auto.conf", 0o600)
    original = auto.read_bytes()
    private = ROOT / "postgres/anvil-capture-tls-20261119"
    private.mkdir(mode=0o700)
    uid = int(run("docker", "exec", POSTGRES, "id", "-u", "postgres"))
    gid = int(run("docker", "exec", POSTGRES, "id", "-g", "postgres"))
    ca = backup / "ca.crt"
    key = backup / "ca.key"
    # Host-side key generation: no secret arguments/stdout, no global trust store.
    run("openssl", "req", "-new", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
        "-nodes", "-keyout", str(key), "-out", str(ca), "-days", "90", "-sha256",
        "-subj", "/CN=Forge QA capture database CA 20261119",
        "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    os.chmod(key, 0o600)
    run("openssl", "req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
        "-keyout", str(private / "server.key"), "-out", str(backup / "server.csr"), "-subj", "/CN=postgres")
    ext = backup / "server.extensions"
    ext.write_text("basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
                   "extendedKeyUsage=serverAuth\nsubjectAltName=DNS:postgres\n")
    run("openssl", "x509", "-req", "-in", str(backup / "server.csr"), "-CA", str(ca), "-CAkey", str(key),
        "-CAcreateserial", "-out", str(private / "server.crt"), "-days", "30", "-sha256", "-extfile", str(ext))
    for path in (private, private / "server.key", private / "server.crt"):
        os.chown(path, uid, gid)
    os.chmod(private / "server.key", 0o600)
    os.chmod(private / "server.crt", 0o644)
    os.chmod(ca, 0o644)
    # Parent backup remains0700. Public CA may be copied into a temporary client
    # path ONLY for transport verification; deployment needs a separate RO mount.
    run("docker", "cp", str(ca), API + ":" + CA_DESTINATION)
    intent = {"schema_version": "anvil.qa-capture-tls-intent.v1", "api_id": API, "postgres_id": pg["Id"],
              "before_config_sha256": CONFIG_SHA, "before_auto_sha256": hashlib.sha256(original).hexdigest(),
              "ca_sha256": hashlib.sha256(ca.read_bytes()).hexdigest(),
              "server_certificate_sha256": hashlib.sha256((private / "server.crt").read_bytes()).hexdigest(),
              "container_restart_authorized": False, "qualification_granted": False}
    (backup / "intent.json").write_text(json.dumps(intent, sort_keys=True))
    try:
        prefix = "/var/lib/postgresql/data/anvil-capture-tls-20261119/"
        # ALTER SYSTEM cannot be grouped in a transaction. Each effect is run
        # once; any failure restores the exact previous auto.conf, then reloads.
        sql("ALTER SYSTEM SET ssl_cert_file='" + prefix + "server.crt';")
        sql("ALTER SYSTEM SET ssl_key_file='" + prefix + "server.key';")
        sql("ALTER SYSTEM SET ssl_min_protocol_version='TLSv1.2';")
        sql("ALTER SYSTEM SET ssl='on';")
        if sql("SELECT pg_reload_conf();") != "t":
            raise ValueError("PostgreSQL TLS reload request failed")
        until = time.monotonic() + 10
        while sql("SHOW ssl;") != "on":
            if time.monotonic() >= until:
                raise ValueError("PostgreSQL did not accept TLS configuration")
            time.sleep(.1)
        if sql("SHOW ssl_min_protocol_version;") != "TLSv1.2":
            raise ValueError("TLS minimum protocol setting not accepted")
        code = (
            "import os,json,psycopg;from psycopg.conninfo import conninfo_to_dict;"
            "p=conninfo_to_dict(os.environ['DATABASE_URL']);"
            "p.update(hostaddr=" + repr(address) + ",sslmode='verify-full',gssencmode='disable',sslrootcert="
            + repr(CA_DESTINATION) + ",connect_timeout='5',application_name='forge-capture-tls-control');"
            "c=psycopg.connect(**p);c.execute('SET TRANSACTION READ ONLY');"
            "r=c.execute('SELECT ssl,version FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone();"
            "assert r and r[0] is True and r[1] in ('TLSv1.2','TLSv1.3');c.rollback();c.close();"
            "print(json.dumps({'authenticated_tls':r[0],'tls_version':r[1],'read_only_control':True}))"
        )
        observed = json.loads(run("docker", "exec", API, "/app/services/backend/.venv/bin/python", "-I", "-B", "-c", code))
        assert hashlib.sha256(config.read_bytes()).hexdigest() == CONFIG_SHA
        if sql("SELECT pg_postmaster_start_time();") != original_postmaster:
            raise ValueError("Database process changed during TLS provisioning")
        observed.update(intent, status="passed_transport_only", database_restarted=False,
                        before_auto_sha256=intent["before_auto_sha256"],
                        after_auto_sha256=hashlib.sha256(auto.read_bytes()).hexdigest())
        (backup / "result.json").write_text(json.dumps(observed, sort_keys=True))
        print(json.dumps(observed, sort_keys=True))
    except BaseException:
        # Preserve key/cert and failed attempt evidence; never delete volumes.
        restored = False
        try:
            auto.write_bytes(original)
            if sql("SELECT pg_reload_conf();") == "t":
                until = time.monotonic() + 10
                while time.monotonic() < until:
                    if (auto.read_bytes() == original and sql("SHOW ssl;") == "off"
                            and sql("SHOW ssl_min_protocol_version;") == original_min):
                        restored = True
                        break
                    time.sleep(.1)
        except BaseException:
            pass  # Persist explicit UNKNOWN rollback; never authorize a retry.
        (backup / "failed.json").write_text(json.dumps({"status": "failed", "rollback_requested": True,
                                                        "rollback_verified": restored}))
        if not restored:
            raise RuntimeError("TLS operation failed; rollback outcome is unknown, do not retry") from None
        raise RuntimeError("TLS operation failed; exact prior configuration and runtime settings restored") from None


if __name__ == "__main__":
    main()
