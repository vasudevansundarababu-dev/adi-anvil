"""Unqualified synthetic metadata for the real private queue; no approval rows.

Run only against an owner-created fresh component database. Source/package and
draft execution metadata exist solely to exercise actual frozen selection/FKs.
No template publication, conformance, production qualification, paid capture,
rights or human expectation approvals are manufactured here.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from anvil.db import Jsonb, digest
from anvil.golden_kyc_runtime import create_trial
from anvil.native_image_profile import IMAGE_ID
from anvil.private_scoring_control import CONTEXT_SCHEMA, PURPOSE, ControlReference

REVIEWED = {"arithmetic.py": "7e0785d67fab37b8e1c7d339000cd3190b667961cbd2af2a79712fdb02780dc7",
            "cases.json": "ea5467e5a1419e6d278a2b99807d40e789c9b48a86b18631df7994362e0dee6b",
            "technical-review.json": "186be4ec9729428b91ad95fb7c85562167643bd09822db9845d46b07d3333c20"}


def reviewed_files(folder):
    import os
    import stat

    if not folder.is_absolute() or folder.resolve() != folder:
        raise ValueError("Canonical independently reviewed fixture path required")
    files = {}
    for name, expected_sha in REVIEWED.items():
        path = folder / name
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o022
                    or info.st_uid not in {0, os.geteuid()} or info.st_size > 65536):
                raise ValueError("Fixed bounded fixture custody required")
            files[name] = stream.read(65537)
        if hashlib.sha256(files[name]).hexdigest() != expected_sha:
            raise ValueError("Independently pinned technical review and fixture bytes required")
    code, raw_cases, raw_review = (files[name] for name in ("arithmetic.py", "cases.json", "technical-review.json"))
    cases, review = json.loads(raw_cases), json.loads(raw_review)
    if (review["schema_version"] != "anvil.synthetic-private-scoring-review.v1"
            or review["scope"] != "synthetic_arithmetic_engineering_only"
            or review["origin"] != "independent_agent_read_only_review" or review["findings"]
            or review["code_sha256"] != hashlib.sha256(code).hexdigest()
            or review["cases_sha256"] != hashlib.sha256(raw_cases).hexdigest()
            or review["observed_cases"] != {case["id"]: case["expected_status"] for case in cases["cases"]}
            or review["legal_sme_rights_approval"] is not False or review["qualification_granted"] is not False):
        raise ValueError("Exact independently reviewed synthetic files required")
    return code.decode(), cases, hashlib.sha256(raw_review).hexdigest()


def prepare(c, config, code, reference, case, review_sha256):
    database = c.execute("SELECT current_database() AS name").fetchone()["name"]
    if not database.startswith("anvil_golden_kyc_component_"):
        raise ValueError("Disposable component database only")
    marker = c.execute("SELECT fixture_nonce,project_id,fixture_label FROM anvil.component_control_fixture "
                       "WHERE created_at>clock_timestamp()-interval '30 minutes'").fetchall()
    if (len(marker) != 1 or marker[0]["fixture_nonce"] != config["fixture_nonce"]
            or str(marker[0]["project_id"]) != config["project_id"]
            or marker[0]["fixture_label"] != "synthetic-component-control-not-performance"):
        raise ValueError("Exact fresh synthetic fixture marker required")
    project, user = config["project_id"], config["user_id"]
    ids = {name: uuid4() for name in ("artifact", "template", "resolution", "resolved", "source", "package",
        "framework", "preset", "preparation", "execution", "task_group", "binding", "evaluator", "admission", "job")}
    value = {"purpose": PURPOSE, "synthetic_control_case": case["id"], "qualified": False}
    sha = digest(value)
    c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (project, user))
    c.execute("INSERT INTO anvil.artifacts(id,project_id,object_key,sha256,byte_size,mime_type,classification,scan_status,origin) "
              "VALUES(%s,%s,%s,%s,0,'application/octet-stream','hidden_reference','quarantined','synthetic-unqualified-control')",
              (ids["artifact"], project, str(ids["artifact"]), hashlib.sha256(b"").hexdigest()))
    c.execute("INSERT INTO anvil.praxis_template_versions(id,project_id,template_key,version,spec,spec_sha256,part_hashes,catalogue_sha256,created_by) "
              "VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s)", (ids["template"], project, str(ids["template"]), Jsonb(value), sha, Jsonb({}), sha, user))
    c.execute("INSERT INTO anvil.praxis_export_resolutions(id,project_id,package_key,version,package_sha256,batch_key,part_index,part_count,private_archive_id,receipt,receipt_sha256,created_by) "
              "VALUES(%s,%s,%s,'synthetic-unqualified',%s,%s,0,1,%s,%s,%s,%s)",
              (ids["resolution"], project, str(ids["resolution"]), sha, str(ids["resolution"]), ids["artifact"], Jsonb(value), sha, user))
    identity = {"task_id": "synthetic-arithmetic-" + case["id"], "task_version": "technical-v1", "payload_sha256": digest(reference)}
    c.execute("INSERT INTO anvil.praxis_resolved_tasks(id,project_id,resolution_id,template_id,task_key,revision,actor,actor_sha256,private_reference_sha256,binding,binding_sha256,created_by) "
              "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
              (ids["resolved"], project, ids["resolution"], ids["template"], identity["task_id"], identity["task_version"],
               Jsonb(value), sha, identity["payload_sha256"], Jsonb(value), sha, user))
    c.execute("INSERT INTO anvil.praxis_sources(id,project_id,task_id,task_version,revision_id,source_sha256,source_artifact_id,actor_spec,created_by) "
              "VALUES(%s,%s,%s,'technical-v1','technical-v1',%s,%s,%s,%s)",
              (ids["source"], project, identity["task_id"], sha, ids["artifact"], Jsonb(value), user))
    c.execute("INSERT INTO anvil.harbor_packages(id,project_id,source_id,package_sha256,package_artifact_id,manifest,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
              (ids["package"], project, ids["source"], sha, ids["artifact"], Jsonb(value), user))
    c.execute("INSERT INTO anvil.workspace_framework_profiles(id,project_id,name,framework,config,config_hash,created_by) VALUES(%s,%s,'Synthetic technical only','harbor',%s,%s,%s)",
              (ids["framework"], project, Jsonb(value), sha, user))
    c.execute("INSERT INTO anvil.workspace_execution_presets(id,project_id,name,runner_profile_id,snapshot,subject_hash,created_by) VALUES(%s,%s,'Unqualified software control',%s,%s,%s,%s)",
              (ids["preset"], project, ids["framework"], Jsonb(value), sha, user))
    c.execute("INSERT INTO anvil.workspace_run_preparations(id,project_id,preset_id,package_id,snapshot,subject_hash,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
              (ids["preparation"], project, ids["preset"], ids["package"], Jsonb(value), sha, user))
    content = {"purpose": PURPOSE, "tasks": [identity | {"title": "Synthetic arithmetic", "rubric": {"criteria": [{"id": "profile"}]}}]}
    c.execute("INSERT INTO anvil.benchmark_task_groups(id,project_id,source_project_id,source_version,name,content,content_sha256,created_by) VALUES(%s,%s,%s,'technical-v1','Synthetic arithmetic',%s,%s,%s)",
              (ids["task_group"], project, str(ids["task_group"]), Jsonb(content), digest(content), user))
    code_sha = hashlib.sha256(code.encode()).hexdigest()
    target = "criterion:" + digest(identity | {"criterion_id": "profile"})
    snapshot = {"source_sha256": config["golden_source_sha256"], "rubric": [{"kind": "custom_python", "id": str(ids["evaluator"]), "sha256": code_sha, "target": target}],
                "policy": [], "safety_categories": [], "purpose": PURPOSE}
    c.execute("INSERT INTO anvil.project_binding_versions(id,project_id,task_group_id,version,snapshot,snapshot_sha256,created_by) VALUES(%s,%s,%s,1,%s,%s,%s)",
              (ids["binding"], project, ids["task_group"], Jsonb(snapshot), digest(snapshot), user))
    c.execute("INSERT INTO anvil.custom_python_evaluators(id,project_id,name,code,code_sha256,created_by) VALUES(%s,%s,'Reviewed synthetic arithmetic',%s,%s,%s)",
              (ids["evaluator"], project, code, code_sha, user))
    execution = {"preparation": {"project_binding": {"task_group_id": str(ids["task_group"]), "id": str(ids["binding"]), "snapshot_sha256": digest(snapshot)}}, "purpose": PURPOSE}
    c.execute("INSERT INTO anvil.workspace_execution_groups(id,project_id,preparation_id,created_by,snapshot,subject_hash) VALUES(%s,%s,%s,%s,%s,%s)",
              (ids["execution"], project, ids["preparation"], user, Jsonb(execution), digest(execution)))
    trial = create_trial(c, project, user, config["pack_id"], config["application_id"], "synthetic-private-" + str(ids["admission"]), 1)
    expectation = {"independent_expectation_review": "synthetic_technical_control_only", "technical_review_sha256": review_sha256,
                   "criterion_references": {"profile": reference}}
    state, checks = {"final": case["final"]}, {"profile": True}
    private_input = {"actual": {"criterion": "profile", "observed": True, "citation_complete": None, "final": case["final"], "policy": None},
                     "expected": {"intended_decision": None, "criterion_reference": reference}}
    from anvil.custom_python_grading import source_hash

    context = {"schema_version": CONTEXT_SCHEMA, "purpose": PURPOSE, "database": database, "fixture_nonce": config["fixture_nonce"],
        "project_id": project, "job_id": str(ids["job"]), "trial_id": str(trial["trial_id"]), "generation": trial["generation"],
        "binding_id": str(ids["binding"]), "binding_sha256": digest(snapshot), "evaluator_id": str(ids["evaluator"]), "code_sha256": code_sha,
        "criterion": "profile", "target": target, "group_id": str(ids["execution"]), "resolved_task_id": str(ids["resolved"]),
        "task_key": identity["task_id"], "task_revision": identity["task_version"], "private_reference_sha256": identity["payload_sha256"],
        "grader_source_sha256": source_hash(), "golden_source_sha256": config["golden_source_sha256"],
        "runtime_image_sha256": config["runtime_image_sha256"], "executor_image_id": IMAGE_ID, "review_receipt_sha256": review_sha256,
        "expectation_sha256": digest(expectation), "state_sha256": digest(state), "checks_sha256": digest(checks), "private_input": private_input}
    c.execute("INSERT INTO banking_private.python_control_admissions(id,project_id,job_id,trial_id,generation,binding_id,evaluator_id,criterion,fixture_nonce,context,context_sha256,expires_at) "
              "VALUES(%s,%s,%s,%s,%s,%s,%s,'profile',%s,%s,%s,%s)",
              (ids["admission"], project, ids["job"], trial["trial_id"], trial["generation"], ids["binding"], ids["evaluator"], config["fixture_nonce"],
               Jsonb(context), digest(context), datetime.now(timezone.utc) + timedelta(minutes=15)))
    return {"reference": ControlReference(ids["admission"], digest(context)), "execution": {"group_id": str(ids["execution"]), "resolved_task_id": str(ids["resolved"])},
            "context": context, "trial": {key: trial[key] for key in ("trial_id", "generation")}, "expectation": expectation, "state": state, "checks": checks}


def main():
    import argparse
    import os
    import stat
    import sys
    from pathlib import Path

    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    from psycopg.rows import dict_row

    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("owner-config", "fixture-config", "fixture-files", "output", "bridge-root"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError("Root isolated fixture preparation required")

    def read(path):
        path = Path(path)
        info = path.lstat()
        if path.resolve() != path or info.st_uid != 0 or info.st_mode & 0o077 or not stat.S_ISREG(info.st_mode) or info.st_size > 32768:
            raise ValueError("Private fixture configuration required")
        return json.loads(path.read_bytes())

    config, owner = read(args.fixture_config), read(args.owner_config)
    params = conninfo_to_dict(config["grader_dsn"])
    host = Path(params["host"])
    if (not host.is_absolute() or host.resolve() != host or not (host / ".s.PGSQL.5432").is_socket()
            or params["dbname"] != config["database"] or config["database"] != owner["new_database"]
            or str(host) != owner["host"] or not config["database"].startswith("anvil_golden_kyc_component_")
            or owner["user"] != "postgres" or config["runtime_image_sha256"] != os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST")):
        raise ValueError("Exact isolated owner target required")
    code, cases, review_sha = reviewed_files(Path(args.fixture_files))
    entries = []
    with psycopg.connect(host=str(host), dbname=config["database"], user="postgres", password=owner["password"],
                         connect_timeout=2, row_factory=dict_row) as c:
        databases = c.execute("SELECT datname FROM pg_database WHERE NOT datistemplate AND datname<>'postgres'").fetchall()
        if databases != [{"datname": config["database"]}]:
            raise ValueError("Entirely separate single-purpose database cluster required")
        claimed = c.execute("UPDATE anvil.component_control_fixture SET consumed_at=clock_timestamp() WHERE fixture_nonce=%s AND consumed_at IS NULL RETURNING fixture_nonce", (config["fixture_nonce"],)).fetchone()
        if not claimed:
            raise ValueError("Fresh fixture cannot be replayed")
        for case in cases["cases"]:
            item = prepare(c, config, code, cases["reference"], case, review_sha)
            item["reference"] = item["reference"].wire()
            entries.append({**item, "id": case["id"], "expected_status": case["expected_status"]})
        for table in ("project_binding_qualifications", "praxis_template_qualifications", "praxis_template_publications"):
            if c.execute("SELECT count(*) AS n FROM anvil." + table).fetchone()["n"] != 0:
                raise ValueError("Technical fixture must not manufacture production approval")
    output = Path(args.output)
    if not output.is_absolute() or output.parent.resolve() != output.parent:
        raise ValueError("Canonical private grader output required")
    record = {"schema_version": "anvil.synthetic-private-scoring-driver.v1", "project_id": config["project_id"],
              "user_id": config["user_id"], "grader_dsn": config["grader_dsn"], "bridge_root": args.bridge_root, "cases": entries}
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "w") as stream:
        json.dump(record, stream, default=str, sort_keys=True)
    print(json.dumps({"status": "synthetic_control_admitted_not_qualified", "cases": len(entries),
                      "review_sha256": review_sha, "production_qualification_rows": 0, "model_calls_authorized": 0}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback
        from pathlib import Path

        print(json.dumps({"status": "blocked_no_replay", "error_type": type(error).__name__,
            "frames": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                       for frame in traceback.extract_tb(error.__traceback__)[-8:]]}))
        raise SystemExit(1) from None
