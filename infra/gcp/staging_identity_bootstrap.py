"""Prepare one real invited initial staging admin; no local seed or approvals.

Default is offline dry-run. Execution requires a separately reviewed deployment
approval receipt, exact staging target and an empty, migrated database. This does
not provision OIDC accounts, evaluator roles, rights, duties, reviews or runs.
"""

import argparse
import hashlib
import http.client
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit
from uuid import UUID

MIGRATION_ROLE = "anvil_staging_migration"
DEPLOYMENT_IDENTITY = Path("/etc/anvil-staging-demo/deployment-identity.json")
METADATA_ROOT = "/computeMetadata/v1/"


def metadata_get(path):
    """Fixed nonsecret GCE endpoints only; no redirects, proxies or tokens.

    Contract: https://docs.cloud.google.com/compute/docs/metadata/querying-metadata
    """
    if path not in {
        "project/project-id",
        "instance/id",
        "instance/name",
        "instance/disks/",
    } and not re.fullmatch(r"instance/disks/(?:[0-9]|1[0-5])/device-name", path):
        raise ValueError("Unapproved metadata endpoint")
    connection = http.client.HTTPConnection("169.254.169.254", 80, timeout=2)
    try:
        connection.request("GET", METADATA_ROOT + path, headers={"Metadata-Flavor": "Google"})
        response = connection.getresponse()
        if response.status != 200 or response.getheader("Metadata-Flavor") != "Google":
            raise RuntimeError("Trusted GCE metadata response required")
        data = response.read(4097)
        if len(data) > 4096:
            raise ValueError("Metadata response exceeds bound")
        return data.decode("ascii").strip()
    finally:
        connection.close()


def root_deployment_identity(path):
    path = Path(path)
    if path != DEPLOYMENT_IDENTITY:
        raise ValueError("Fixed root-owned deployment identity path required")
    for parent in [path.parent, *path.parent.parents]:
        metadata = parent.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise ValueError("Root-owned nonsymlink deployment identity ancestors required")
    parent = path.parent.stat()
    if stat.S_IMODE(parent.st_mode) != 0o700:
        raise ValueError("Deployment identity parent must be root-only0700")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > 16384
        ):
            raise ValueError("Root-only0600 single regular deployment identity required")
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError("Deployment identity exceeds bound")
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


class GceTargetObserver:
    """Correlates live metadata, root-owned creation record and actual PG cluster.

    Metadata exposes device names, not numeric disk IDs. Disk IDs are trusted
    from the root-owned Cloud SDK creation record; this is not signed attestation.
    A fake getter in unit tests never constitutes actual GCP verification.
    """

    def __init__(self, getter=metadata_get):
        self.getter = getter

    def preflight(self, target):
        identity, manifest_sha256 = root_deployment_identity(DEPLOYMENT_IDENTITY)
        required = {
            "schema",
            "gcp_project",
            "vm_name",
            "vm_id",
            "disks",
            "postgres_system_identifier",
            "creation_manifest_sha256",
        }
        if (
            set(identity) != required
            or identity["schema"] != "anvil.staging.deployment-identity.v1"
            or manifest_sha256 != target["new_disk_manifest_sha256"]
            or not re.fullmatch(r"[a-f0-9]{64}", identity["creation_manifest_sha256"])
        ):
            raise ValueError("Exact reviewed deployment identity required")
        for key in ("gcp_project", "vm_name", "vm_id", "postgres_system_identifier"):
            if identity[key] != target[key]:
                raise ValueError("Deployment identity differs from reviewed target")
        observed = {
            "gcp_project": self.getter("project/project-id"),
            "vm_name": self.getter("instance/name"),
            "vm_id": self.getter("instance/id"),
        }
        if any(observed[key] != target[key] for key in observed):
            raise RuntimeError("This is not the approved new staging VM")
        indices = self.getter("instance/disks/").splitlines()
        if (
            not 1 <= len(indices) <= 16
            or len(set(indices)) != len(indices)
            or any(not re.fullmatch(r"(?:[0-9]|1[0-5])/", index) for index in indices)
        ):
            raise ValueError("Bounded attached disk metadata required")
        devices = [self.getter("instance/disks/" + index + "device-name") for index in indices]
        disks = identity["disks"]
        if (
            not isinstance(disks, list)
            or not 1 <= len(disks) <= 16
            or any(
                set(disk) != {"device_name", "disk_id"}
                or not re.fullmatch(r"anvil-staging-demo(?:-[a-z0-9-]{1,50})?", disk["device_name"])
                or not re.fullmatch(r"[1-9][0-9]{0,19}", disk["disk_id"])
                for disk in disks
            )
            or len({disk["disk_id"] for disk in disks}) != len(disks)
            or len(set(devices)) != len(devices)
            or set(devices) != {disk["device_name"] for disk in disks}
            or len(disks) != len(devices)
        ):
            raise RuntimeError("Attached disk devices do not match fresh staging creation record")
        return {
            "manifest_sha256": manifest_sha256,
            "metadata": observed,
            "devices": sorted(devices),
            "disk_id_source": "trusted_root_creation_record_not_metadata_attestation",
        }

    def verify(self, target, connection):
        observed = self.preflight(target)
        if connection.info.host != "127.0.0.1" or connection.info.port != 5432:
            raise RuntimeError("Fixed loopback staging database required")
        actual = connection.execute(
            "SELECT current_database() db,current_user role,session_user session_role,system_identifier::text cluster_id FROM pg_control_system()"
        ).fetchone()
        if (
            actual["db"] != "anvil"
            or actual["role"] != MIGRATION_ROLE
            or actual["session_role"] != MIGRATION_ROLE
            or actual["cluster_id"] != target["postgres_system_identifier"]
        ):
            raise RuntimeError(
                "Actual migration login or cluster differs from fresh deployment record"
            )
        return {
            "target_identity_sha256": digest(target),
            "postgres_system_identifier": actual["cluster_id"],
            "observation_receipt_sha256": digest({**observed, "cluster_id": actual["cluster_id"]}),
        }


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def _text(value, limit=200):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("Explicit bounded identity fields required")
    return value


def _uuid(value):
    parsed = UUID(str(value))
    if parsed.int == 0:
        raise ValueError("Nonzero reviewed UUID required")
    return str(parsed)


def validate(contract):
    if (
        set(contract)
        != {"schema", "target", "identity", "organization", "project", "reviewed_invitation_sha256"}
        or contract["schema"] != "anvil.staging.initial-admin.v1"
    ):
        raise ValueError("Exact initial-admin staging contract required")
    target, identity = contract["target"], contract["identity"]
    if (
        set(target)
        != {
            "database",
            "host",
            "port",
            "migration_role",
            "gcp_project",
            "vm_name",
            "vm_id",
            "new_disk_manifest_sha256",
            "postgres_system_identifier",
        }
        or target["database"] != "anvil"
        or target["host"] != "127.0.0.1"
        or target["port"] != 5432
        or type(target["port"]) is not int
        or target["migration_role"] != MIGRATION_ROLE
        or target["gcp_project"] != "adi-anvil-mvp-2026"
        or target["vm_name"] != "anvil-staging-demo"
        or not re.fullmatch(r"[1-9][0-9]{0,19}", target["vm_id"])
        or not re.fullmatch(r"[1-9][0-9]{0,19}", target["postgres_system_identifier"])
        or not re.fullmatch(r"[a-f0-9]{64}", target["new_disk_manifest_sha256"])
    ):
        raise ValueError("Dedicated staging target and migration identity required")
    if (
        set(identity) != {"user_id", "issuer", "subject", "name", "origin"}
        or identity["origin"] != "real_invited_oidc_identity"
    ):
        raise ValueError("Only explicitly reviewed real invited identity is supported")
    _uuid(identity["user_id"])
    _uuid(identity["subject"])
    _text(identity["name"])
    issuer = urlsplit(identity["issuer"])
    if (
        issuer.scheme != "https"
        or not issuer.hostname
        or issuer.hostname in {"localhost", "127.0.0.1", "::1"}
        or issuer.username
        or issuer.password
        or issuer.query
        or issuer.fragment
        or issuer.path != "/realms/anvil-staging-demo"
        or issuer.port not in {None, 443}
    ):
        raise ValueError("Exact externally reviewed staging OIDC issuer required")
    identifiers = [identity["user_id"]]
    for kind in ("organization", "project"):
        if set(contract[kind]) != {"id", "name"}:
            raise ValueError("Explicit organization/project required")
        identifiers.append(_uuid(contract[kind]["id"]))
        _text(contract[kind]["name"])
    if len(set(identifiers)) != 3 or not re.fullmatch(
        r"[a-f0-9]{64}", contract["reviewed_invitation_sha256"]
    ):
        raise ValueError("Distinct IDs and reviewed invitation evidence hash required")
    return digest(contract)


def validate_approval(approval, subject, now=None):
    now = now or datetime.now(timezone.utc)
    if (
        set(approval) != {"action", "contract_sha256", "approval_record_sha256", "expires_at"}
        or approval["action"] != "execute_initial_staging_admin_bootstrap"
        or approval["contract_sha256"] != subject
        or not re.fullmatch(r"[a-f0-9]{64}", approval["approval_record_sha256"])
    ):
        raise ValueError("Separate deployment approval bound to exact contract required")
    expiry = datetime.fromisoformat(approval["expires_at"].replace("Z", "+00:00"))
    if expiry.tzinfo is None or not 0 < (expiry - now).total_seconds() <= 86400:
        raise ValueError("Current bounded deployment approval required")


def validate_dsn(value, target):
    url = urlsplit(value)
    parameters = parse_qsl(url.query, keep_blank_values=True)
    if (
        url.scheme not in {"postgres", "postgresql"}
        or url.hostname != target["host"]
        or (url.port or 5432) != target["port"]
        or unquote(url.path.lstrip("/")) != target["database"]
        or unquote(url.username or "") != target["migration_role"]
        or len({key for key, _ in parameters}) != len(parameters)
        or any(
            key not in {"sslmode", "sslrootcert", "connect_timeout", "application_name"}
            for key, _ in parameters
        )
    ):
        raise ValueError("Migration connection must match exact reviewed staging target")


def apply(connection, contract, approval, *, trusted_target_observer):
    """One atomic transaction. Caller must use a fresh dedicated migration login.

    No SQL execution is performed by dry-run; this path still needs independent
    fresh-database testing and the separately reviewed deployment approval.
    """
    subject = validate(contract)
    validate_approval(approval, subject)
    target, identity = contract["target"], contract["identity"]
    # This interface is an operator-owned live observer, not a JSON boolean.
    if not callable(getattr(trusted_target_observer, "verify", None)):
        raise RuntimeError("Operator-owned trusted target observer required, not caller flags")
    observed = trusted_target_observer.verify(target, connection)
    if (
        not isinstance(observed, dict)
        or set(observed)
        != {"target_identity_sha256", "postgres_system_identifier", "observation_receipt_sha256"}
        or observed["target_identity_sha256"] != digest(target)
        or observed["postgres_system_identifier"] != target["postgres_system_identifier"]
        or not re.fullmatch(r"[a-f0-9]{64}", observed["observation_receipt_sha256"])
    ):
        raise RuntimeError("Trusted new staging VM/disk/cluster observation required")
    if connection.info.host != target["host"] or connection.info.port != target["port"]:
        raise RuntimeError("Actual connection is not the reviewed staging endpoint")
    with connection.transaction():
        connection.execute("SET LOCAL lock_timeout='5s'")
        connection.execute("SET LOCAL statement_timeout='10s'")
        actual = connection.execute("""SELECT current_database() db,current_user role,session_user session_role,
          pg_get_userbyid(d.datdba) database_owner,pg_get_userbyid(n.nspowner) schema_owner,
          r.rolsuper,r.rolbypassrls,r.rolcreaterole,r.rolcreatedb,r.rolreplication,r.rolcanlogin
          FROM pg_database d,pg_namespace n,pg_roles r
          WHERE d.datname=current_database() AND n.nspname='anvil' AND r.rolname=current_user""").fetchone()
        if (
            actual is None
            or any(
                actual[key] != target["migration_role"]
                for key in ("role", "session_role", "database_owner", "schema_owner")
            )
            or actual["db"] != target["database"]
            or not actual["rolcanlogin"]
            or not actual["rolsuper"]
        ):
            raise RuntimeError("Actual isolated migration identity is not qualified")
        runtime_roles = connection.execute(
            """SELECT r.rolname,r.rolsuper,r.rolbypassrls,r.rolcreaterole,r.rolcreatedb,r.rolreplication,r.rolcanlogin,
          pg_has_role(r.oid,owner.oid,'MEMBER') owner_membership FROM pg_roles r,pg_roles owner
          WHERE r.rolname=ANY(%s) AND owner.rolname=%s""",
            (["anvil_app", "anvil_worker", "anvil_benchmark_evaluator"], MIGRATION_ROLE),
        ).fetchall()
        if {role["rolname"] for role in runtime_roles} != {
            "anvil_app",
            "anvil_worker",
            "anvil_benchmark_evaluator",
        } or any(
            any(
                role[key]
                for key in (
                    "rolsuper",
                    "rolbypassrls",
                    "rolcreaterole",
                    "rolcreatedb",
                    "rolreplication",
                    "owner_membership",
                )
            )
            or (role["rolname"] == "anvil_benchmark_evaluator" and role["rolcanlogin"])
            for role in runtime_roles
        ):
            raise RuntimeError(
                "Runtime roles must remain unprivileged and evaluator protected NOLOGIN"
            )
        versions = connection.execute(
            "SELECT version FROM anvil.schema_versions ORDER BY version"
        ).fetchall()
        head = connection.execute("SELECT version_num FROM anvil.alembic_version").fetchall()
        if [row["version"] for row in versions] != list(range(1, 59)) or [
            row["version_num"] for row in head
        ] != ["058"]:
            raise RuntimeError("Exact canonical schema58 is required")
        # Only the verified fresh-instance SUPER migration owner performs this
        # global emptiness check. Runtime roles never gain RLS bypass or grants.
        from psycopg import sql

        tables = connection.execute(
            "SELECT schemaname,tablename FROM pg_tables WHERE schemaname=ANY(%s) ORDER BY schemaname,tablename",
            (["anvil", "anvil_checkpoints"],),
        ).fetchall()
        metadata_tables = {
            ("anvil", "schema_versions"),
            ("anvil", "alembic_version"),
            ("anvil_checkpoints", "checkpoint_migrations"),
        }
        history = [
            (row["schemaname"], row["tablename"])
            for row in tables
            if (row["schemaname"], row["tablename"]) not in metadata_tables
        ]
        if not {
            ("anvil", "organizations"),
            ("anvil", "users"),
            ("anvil", "projects"),
            ("anvil", "memberships"),
            ("anvil", "audit_events"),
        } <= set(history):
            raise RuntimeError("Canonical identity/history tables unavailable")
        connection.execute(
            sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(
                sql.SQL(",").join(sql.Identifier(schema, table) for schema, table in history)
            )
        )
        for schema, table in history:
            nonempty = connection.execute(
                sql.SQL("SELECT EXISTS(SELECT 1 FROM {}) occupied").format(
                    sql.Identifier(schema, table)
                )
            ).fetchone()
            if nonempty["occupied"]:
                raise RuntimeError(
                    "Initial bootstrap refuses existing identity, project or history"
                )
        project, organization = contract["project"], contract["organization"]
        connection.execute(
            "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
            (project["id"], identity["user_id"]),
        )
        connection.execute(
            "INSERT INTO anvil.organizations(id,name) VALUES(%s,%s)",
            (organization["id"], organization["name"]),
        )
        connection.execute(
            "INSERT INTO anvil.users(id,org_id,issuer,subject,name,active) VALUES(%s,%s,%s,%s,%s,true)",
            (
                identity["user_id"],
                organization["id"],
                identity["issuer"],
                identity["subject"],
                identity["name"],
            ),
        )
        connection.execute(
            "INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,%s)",
            (project["id"], organization["id"], project["name"]),
        )
        connection.execute(
            "INSERT INTO anvil.memberships(project_id,user_id,role,active) VALUES(%s,%s,'admin',true)",
            (project["id"], identity["user_id"]),
        )
        metadata = {
            "contract_sha256": subject,
            "reviewed_invitation_sha256": contract["reviewed_invitation_sha256"],
            "deployment_approval_record_sha256": approval["approval_record_sha256"],
            "target_observation_receipt_sha256": observed["observation_receipt_sha256"],
            "privileged_migration_owner_only": True,
            "migration_owner_privileges": {
                key: actual[key]
                for key in (
                    "rolsuper",
                    "rolbypassrls",
                    "rolcreaterole",
                    "rolcreatedb",
                    "rolreplication",
                )
            },
            "synthetic_identity": False,
            "rights_or_reviews_seeded": False,
        }
        connection.execute(
            "INSERT INTO anvil.audit_events(project_id,actor_id,action,target_id,metadata) VALUES(%s,%s,'staging.initial_admin_bootstrap',%s,%s::jsonb)",
            (project["id"], identity["user_id"], identity["user_id"], json.dumps(metadata)),
        )
    return {
        "status": "initial_real_admin_created",
        "contract_sha256": subject,
        "rights_or_reviews_seeded": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--deployment-approval", type=Path)
    args = parser.parse_args()
    try:
        contract = json.loads(args.contract.read_text())
        subject = validate(contract)
        if not args.execute:
            result = {
                "status": "dry_run_no_connection_or_changes",
                "contract_sha256": subject,
                "deployment_approval_required": True,
                "execution_available_after_verified_approval_and_target": True,
                "planned_rows": {
                    "organizations": 1,
                    "users": 1,
                    "projects": 1,
                    "admin_memberships": 1,
                    "audit_events": 1,
                },
                "remaining_gates": [
                    "actual invited OIDC account verified independently",
                    "separate application deployment approval including privileged migration-owner secret isolation",
                    "root-only creation identity plus live exact staging VM/device/PG cluster verification",
                    "exact schema58 fresh staging database and SUPER migration-owner provisioning isolated from runtime",
                    "independent fresh SQL verification pending",
                    "no rights/reviewer/evaluator approvals seeded",
                ],
            }
        else:
            if args.deployment_approval is None:
                raise ValueError("Deployment approval receipt required")
            approval = json.loads(args.deployment_approval.read_text())
            validate_approval(approval, subject)
            dsn = os.environ.get("MIGRATION_DATABASE_URL", "")
            validate_dsn(dsn, contract["target"])
            observer = GceTargetObserver()
            observer.preflight(contract["target"])
            import psycopg
            from psycopg.rows import dict_row

            with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5) as connection:
                result = apply(connection, contract, approval, trusted_target_observer=observer)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        # Database exceptions can contain connection credentials or identity data.
        print(json.dumps({"status": "bootstrap_blocked", "details_redacted": True}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
