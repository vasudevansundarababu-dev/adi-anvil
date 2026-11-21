"""Restricted operator stages a private review packet, never approves it."""

import argparse
import os
import stat
import sys
from pathlib import Path
from uuid import UUID

from anvil.db import one
from anvil.kyc_expectation_reviews import Packet, stage_private
from anvil.praxis_generic_contract import canonical, load


def enter(c, project):
    row = one(c, "SELECT session_user AS login,rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=session_user")
    if not row or not row["rolcanlogin"] or any(row[key] for key in ("rolsuper", "rolbypassrls", "rolcreatedb", "rolcreaterole", "rolreplication")):
        raise ValueError("Dedicated restricted private loader LOGIN required")
    roles = c.execute("SELECT rolname FROM pg_roles WHERE pg_has_role(session_user,oid,'MEMBER') AND rolname<>session_user").fetchall()
    if {r["rolname"] for r in roles} != {"anvil_kyc_expectation_loader"}:
        raise ValueError("Disjoint private expectation loader membership required")
    c.execute("SET LOCAL ROLE anvil_kyc_expectation_loader")
    principal = one(c, "SELECT user_id FROM anvil.kyc_policy_operator_principals WHERE login_role=session_user AND project_id=%s", (project,))
    if not principal:
        raise ValueError("Actual project operator enrollment required")
    user = principal["user_id"]
    c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (str(project), str(user)))
    if not one(c, "SELECT anvil.kyc_policy_operator_scope(%s) AS allowed", (project,))["allowed"]:
        raise ValueError("Current project operator authority required")
    return user


def read_packet(path):
    path = Path(path)
    info = path.lstat()
    if (not path.is_absolute() or path.resolve() != path or not stat.S_ISREG(info.st_mode)
            or info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o077 or info.st_nlink != 1
            or not 0 < info.st_size <= 16777216):
        raise ValueError("Canonical bounded owner-only private review packet required")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError("Private packet changed during open")
        raw = stream.read(16777217)
        after = os.fstat(stream.fileno())
        if len(raw) != info.st_size or (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (info.st_size, info.st_mtime_ns, info.st_ctime_ns):
            raise ValueError("Private packet changed during read")
    packet = Packet.model_validate_json(canonical(load(raw)))
    if raw != canonical(packet.model_dump(mode="json")):
        raise ValueError("Review the exact canonical normalized packet bytes before staging")
    return packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=UUID, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    args = parser.parse_args()
    packet = read_packet(args.packet)
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(os.environ["ANVIL_KYC_EXPECTATION_LOADER_DATABASE_URL"], row_factory=dict_row,
                          connect_timeout=2, options="-c statement_timeout=5000 -c lock_timeout=1000") as c:
        user = enter(c, args.project)
        result = stage_private(c, args.project, user, packet)
    print(canonical(result | {"commit_observed": True}).decode())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("private_expectation_staging_blocked_no_review_or_run_authority_granted\n")
        raise SystemExit(1) from None
