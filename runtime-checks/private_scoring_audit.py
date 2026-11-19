"""Read-only owner audit of a fresh synthetic private-scoring cluster."""

import argparse
import json
import os
from pathlib import Path


def read(path):
    path = Path(path)
    info = path.lstat()
    if path.resolve() != path or info.st_uid != 0 or info.st_mode & 0o077 or info.st_size > 32768:
        raise ValueError("Exact private root audit configuration required")
    return json.loads(path.read_bytes())


def main(owner_path, jobs_path):
    import psycopg
    from psycopg.rows import dict_row

    owner, jobs = read(owner_path), read(jobs_path)
    if os.geteuid() != 0 or not owner["new_database"].startswith("anvil_golden_kyc_component_") or len(jobs["job_ids"]) != 6:
        raise ValueError("Exact disposable six-job fixture required")
    with psycopg.connect(host=owner["host"], dbname=owner["new_database"], user="postgres", password=owner["password"],
            row_factory=dict_row, connect_timeout=2, options="-c default_transaction_read_only=on -c statement_timeout=5000") as c:
        identity = c.execute("SELECT current_database() AS database,inet_server_addr() AS address").fetchone()
        if identity != {"database": owner["new_database"], "address": None}:
            raise ValueError("Actual isolated Unix SQL identity required")
        counts = {table: c.execute("SELECT count(*) AS n FROM anvil." + table).fetchone()["n"] for table in (
            "project_binding_qualifications", "praxis_template_qualifications", "praxis_template_publications")}
        if any(counts.values()):
            raise ValueError("Synthetic control manufactured production qualification")
        rows = c.execute("SELECT id::text,project_id::text,state,request_sha256,result_sha256,request->>'schema_version' AS request_schema,"
            "result->>'schema_version' AS result_schema,result->>'status' AS result_status FROM banking_private.python_grading_jobs "
            "WHERE id::text=ANY(%s) ORDER BY id", (jobs["job_ids"],)).fetchall()
        if len(rows) != 6 or any(row["project_id"] != jobs["project_id"] or row["state"] not in {"completed", "error"} for row in rows):
            raise ValueError("Actual exact terminal private SQL rows required")
    print(json.dumps({"schema_version": "anvil.private-scoring-readonly-sql-audit.v1", "jobs": rows,
        "production_qualification_rows": counts, "read_only": True, "qualification_granted": False}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--jobs", required=True)
    args = parser.parse_args()
    main(args.owner, args.jobs)
