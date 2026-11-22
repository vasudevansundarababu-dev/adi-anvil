"""Metadata-only existence witness from an actual database owner connection.

No qualification, enrollment, approval, private answer or model operation.
Original stdout must be retained and independently reviewed before use.
"""

from uuid import UUID

from anvil.db import one
from anvil.praxis_generic_contract import canonical


def observe(c, project, group, foreign_project, foreign_group):
    from infra.gcp.task_method_qualification import require

    require(all(type(x) is UUID for x in (project, group, foreign_project, foreign_group))
            and project != foreign_project and group != foreign_group, "Disjoint exact metadata scopes required")
    require(one(c, "SHOW transaction_read_only")["transaction_read_only"] == "on",
            "Owner metadata observer requires read-only transaction")
    role = one(c, "SELECT session_user AS login,r.rolsuper AS superuser,"
               "pg_get_userbyid(d.datdba)=session_user AS database_owner "
               "FROM pg_roles r JOIN pg_database d ON d.datname=current_database() "
               "WHERE r.rolname=session_user")
    require(role and (role["database_owner"] or role["superuser"]), "Actual database owner session required")
    rows = []
    for p, g in ((project, group), (foreign_project, foreign_group)):
        row = one(c, "SELECT project_id,id,content_sha256 FROM anvil.benchmark_task_groups "
                  "WHERE project_id=%s AND id=%s", (p, g))
        require(row is not None, "Both actual captured groups must exist")
        rows.append(row)
    db = one(c, "SELECT current_database() AS database,d.oid::text AS database_oid,"
             "s.system_identifier::text AS system_identifier FROM pg_database d "
             "CROSS JOIN pg_control_system() s WHERE d.datname=current_database()")
    return {"schema_version": "anvil.task-method-owner-observation.v1",
            "origin": "actual_read_only_database_metadata", "database_identity": db,
            "observer": role, "observed_at": one(c, "SELECT statement_timestamp() AS t")["t"].isoformat(),
            "own_project_id": str(project), "own_group_id": str(group),
            "own_source_sha256": rows[0]["content_sha256"],
            "foreign_project_id": str(foreign_project), "foreign_group_id": str(foreign_group),
            "foreign_source_sha256": rows[1]["content_sha256"], "known_foreign_group_exists": True,
            "private_content_read": False, "qualification_granted": False, "provider_calls": 0}


def main():
    import argparse
    import os
    import signal
    import sys

    import psycopg
    from psycopg.rows import dict_row

    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("project", "group", "foreign-project", "foreign-group"):
        parser.add_argument("--" + field, type=UUID, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("Metadata observation deadline")))
    signal.alarm(30)
    with psycopg.connect(os.environ["ANVIL_METHOD_OWNER_OBSERVER_DATABASE_URL"], row_factory=dict_row,
                        connect_timeout=2, options="-c statement_timeout=5000 -c lock_timeout=1000") as c:
        c.execute("SET TRANSACTION READ ONLY")
        result = observe(c, args.project, args.group, args.foreign_project, args.foreign_group)
    signal.alarm(0)
    sys.stdout.buffer.write(canonical(result))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        __import__("sys").stderr.write("method_owner_metadata_observation_blocked\n")
        raise SystemExit(1) from None
