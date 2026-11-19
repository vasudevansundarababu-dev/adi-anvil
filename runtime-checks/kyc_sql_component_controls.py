"""One-shot installed synthetic SQL/OpenEnv/MCP controls; never qualification.

Operator supplies an already migrated, separately seeded disposable database,
disjoint restricted runtime logins and an expiring one-shot marker. Never use a
serving database. Secrets remain in an owner-only config; stdout is hashes only.
"""
import argparse
import hashlib
import json
import os
import signal
import stat
import sys
from collections import deque
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4


class ControlDeadline(BaseException):
    """Do not let per-control failure capture consume the overall cutoff."""


def require(condition):
    if not condition:
        raise ValueError("Synthetic SQL control refused")


def safe_exception_frames(error):
    """Bounded location metadata only; never format exceptions or read source."""
    frames = deque(maxlen=8)
    current = error.__traceback__
    inspected = 0
    while current is not None and inspected < 256:
        code = current.tb_frame.f_code

        def label(value):
            return "".join(char if char.isascii() and (char.isalnum() or char in "_.-<>")
                           else "_" for char in value[:96])

        frames.append({"file": label(Path(code.co_filename).name),
                       "line": current.tb_lineno, "function": label(code.co_name)})
        current = current.tb_next
        inspected += 1
    return list(frames)


def validate_unix_params(value, database):
    require(not set(value) - {"host", "port", "user", "password", "dbname", "sslmode"}
            and value.get("dbname") == database)
    host = Path(value.get("host", ""))
    require(host.is_absolute() and host.resolve() == host and host.is_dir()
            and value.get("port", "5432") == "5432" and (host / ".s.PGSQL.5432").is_socket())


def read_config(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and not info.st_mode & 0o077 and info.st_nlink == 1 and info.st_size <= 16384)
        raw = stream.read(16385)
    config = json.loads(raw)
    require(set(config) == {"schema_version", "fixture_nonce", "fixture_label", "database",
        "scheduler_dsn", "grader_dsn", "app_dsn", "project_id", "user_id", "pack_id", "application_id",
        "snapshot_sha256", "golden_source_sha256", "broker_source_sha256", "runtime_image_sha256"})
    require(config["schema_version"] == "anvil.synthetic-sql-component-config.v2"
            and config["database"].startswith("anvil_golden_kyc_component_")
            and len(config["database"]) <= 63 and config["fixture_label"] == "synthetic-component-control-not-performance")
    for name in ("fixture_nonce", "snapshot_sha256", "golden_source_sha256", "broker_source_sha256", "runtime_image_sha256"):
        require(type(config[name]) is str and len(config[name]) == 64
                and all(char in "0123456789abcdef" for char in config[name]))
    for name in ("project_id", "user_id"):
        require(str(UUID(config[name])) == config[name])
    return config


def run(config):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    from psycopg.rows import dict_row

    from anvil.golden_kyc_anvil import source_hash
    from anvil.golden_kyc_identity import enter
    from anvil.harbor_agents import code_digest
    from anvil.praxis_generic_contract import digest

    require(sys.flags.isolated and sys.dont_write_bytecode)
    require(source_hash() == config["golden_source_sha256"]
            and code_digest() == config["broker_source_sha256"]
            and os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST") == config["runtime_image_sha256"])
    params = {role: conninfo_to_dict(config[role + "_dsn"]) for role in ("scheduler", "grader", "app")}
    for value in params.values():
        validate_unix_params(value, config["database"])
    require(len({value.get("user") for value in params.values()}) == 3)
    claimed = False

    @contextmanager
    def connections(role="scheduler", *, claim=False, foreign_project=None):
        nonlocal claimed
        with psycopg.connect(**params[role], connect_timeout=2, row_factory=dict_row,
                             options="-c statement_timeout=3000 -c lock_timeout=500") as connection:
            identity = connection.execute("SELECT current_database() AS database,session_user AS login,inet_server_addr() AS address").fetchone()
            require(identity["database"] == config["database"] and identity["login"] == params[role]["user"] and identity["address"] is None)
            marker = connection.execute(
                "SELECT fixture_label,project_id,consumed_at,created_at>clock_timestamp()-interval '30 minutes' "
                "AND created_at<=clock_timestamp() AS fresh FROM anvil.component_control_fixture WHERE fixture_nonce=%s",
                (config["fixture_nonce"],)).fetchone()
            require(marker and marker["fixture_label"] == config["fixture_label"]
                    and str(marker["project_id"]) == config["project_id"] and marker["fresh"])
            if claim:
                require(not claimed and marker["consumed_at"] is None)
                row = connection.execute("UPDATE anvil.component_control_fixture SET consumed_at=clock_timestamp() "
                    "WHERE fixture_nonce=%s AND consumed_at IS NULL RETURNING fixture_nonce", (config["fixture_nonce"],)).fetchone()
                require(row is not None)
            else:
                require(claimed and marker["consumed_at"] is not None)
            if role == "app":
                actual = connection.execute("SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolcanlogin FROM pg_roles WHERE rolname=session_user").fetchone()
                parents = connection.execute("SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles u ON u.oid=m.member WHERE u.rolname=session_user").fetchall()
                require(actual and actual["rolcanlogin"] and not any(actual[key] for key in (
                    "rolsuper", "rolbypassrls", "rolcreatedb", "rolcreaterole", "rolreplication"))
                    and [row["rolname"] for row in parents] == ["anvil_app"])
                connection.execute("SET LOCAL ROLE anvil_app")
                connection.execute("SELECT set_config('anvil.project',%s,true)", (foreign_project or config["project_id"],))
            else:
                enter(connection, "anvil_golden_" + role, foreign_project or config["project_id"])
            connection.execute("SELECT set_config('anvil.user',%s,true)", (config["user_id"],))
            if role == "scheduler" and foreign_project is None:
                require(connection.execute("SELECT anvil.golden_scheduler_project_fence(%s) AS allowed",
                    (config["project_id"],)).fetchone()["allowed"] is True)
            yield connection
        if claim:
            claimed = True

    # Consume before effects. Any subsequent error requires a new isolated
    # fixture/marker; the script never retries an ambiguous dispatch.
    with connections(claim=True):
        pass
    results = {}

    def control(name, operation):
        try:
            result = operation()
            results[name] = {"status": "passed", "observation_sha256": digest(result)}
        except Exception as error:
            results[name] = {"status": "failed", "exception_type": type(error).__name__,
                             "exception_frames": safe_exception_frames(error)}

    def isolation():
        for role, private in (("scheduler", "expectations"), ("grader", "scenarios"), ("app", "expectations"), ("app", "scenarios")):
            with connections(role) as connection:
                denied = False
                try:
                    with connection.transaction():
                        connection.execute("SELECT * FROM banking_private." + private + " LIMIT 1")
                except psycopg.errors.InsufficientPrivilege:
                    denied = True
                require(denied)
        with connections(foreign_project=str(uuid4())) as connection:
            require(not connection.execute("SELECT id FROM banking.applications WHERE project_id=%s", (config["project_id"],)).fetchall())
        return {"actual_disjoint_login_private_select_denials": 4, "foreign_project_rows": 0}

    control("restricted_logins_private_and_project_isolation", isolation)

    def openenv_mcp():
        from anvil.golden_kyc_engine import Denied
        from anvil.golden_kyc_openenv import GoldenAction, GoldenEnvironment
        from anvil.golden_kyc_runtime import create_trial, step
        from anvil.golden_mcp_client import McpEpisode

        with connections() as connection:
            snapshot = connection.execute("SELECT snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s AND id=%s",
                (config["project_id"], config["pack_id"], config["application_id"])).fetchone()
            require(snapshot and snapshot["snapshot_sha256"] == config["snapshot_sha256"])
            trial = create_trial(connection, config["project_id"], config["user_id"], config["pack_id"],
                                 config["application_id"], "synthetic-installed-control-" + config["fixture_nonce"], 1)
        environment = GoldenEnvironment(connections, config["project_id"], config["user_id"], trial["trial_id"])
        try:
            environment.reset()
            original = environment.credentials.copy()
            with McpEpisode(environment, {"generation": original["generation"], "fixture": config["fixture_nonce"]}, lambda: True) as mediator:
                observed = mediator.step(GoldenAction(operation="application.read", arguments={}, expected_generation=original["generation"]))
                require(observed.result["status"] == "completed")
                count_before = len(mediator.calls)
                for arguments, meta in (({}, {"anvil_session": "wrong", "scope_sha256": mediator.scope_hash}),
                                        ({}, {"anvil_session": mediator.session_capability, "scope_sha256": "0" * 64}),
                                        ({"unexpected": True}, mediator.meta)):
                    async def rejected(arguments=arguments, meta=meta):
                        return await mediator.session.call_tool("application.read", arguments, meta=meta)
                    require(mediator.portal.call(rejected).isError)
                require(len(mediator.calls) == count_before)
                environment.reset()
                require(environment.credentials["generation"] > original["generation"])
                refused = False
                try:
                    mediator.step(GoldenAction(operation="application.read", arguments={}, expected_generation=original["generation"]))
                except ValueError:
                    refused = True
                require(refused)
                receipt = mediator.public_receipt()
            with connections() as connection:
                refused = False
                try:
                    step(connection, config["project_id"], config["user_id"], trial["trial_id"], original["generation"],
                         original["trial_token"], "application.read", {})
                except Denied:
                    refused = True
                require(refused)
            return {"transport": receipt, "reset_generation": environment.credentials["generation"], "stale_sql_token": "denied"}
        finally:
            environment.close()

    control("actual_openenv_mcp_sql_reset", openenv_mcp)

    def products():
        from fastapi import HTTPException

        from anvil.golden_kyc_anvil import PRODUCT_NAMES, register, validate
        from anvil.golden_kyc_engine import Denied
        from anvil.golden_kyc_evaluators import CRITERIA

        with connections("app") as connection:
            before = connection.execute("SELECT id,snapshot,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id",
                                        (config["project_id"], config["pack_id"])).fetchall()
            require(len(before) == 200 and len({row["id"] for row in before}) == 200
                    and all(digest(row["snapshot"]) == row["snapshot_sha256"] for row in before))
            imported = register(connection, config["project_id"], config["user_id"], config["pack_id"], application_types=True)
            row = connection.execute("SELECT * FROM banking.anvil_imports WHERE id=%s", (imported["id"],)).fetchone()
            validate(connection, row)
            assignments = row["manifest"]["case_assignments"]
            original = {item["id"]: item for item in before}
            require(len(assignments) == 200 and {item["application_id"] for item in assignments} == set(original)
                    and all(item["application_sha256"] == original[item["application_id"]]["snapshot_sha256"]
                            and item["product"] == original[item["application_id"]]["snapshot"]["product"]
                            and item["task_id"] == "KYC-" + item["product"] for item in assignments))
            require({item["product"] for item in assignments} == set(PRODUCT_NAMES))
            evaluators = row["manifest"]["evaluators"]
            require(len(evaluators) == 50 and len({e["configuration_id"] for e in evaluators}) == 50)
            group = connection.execute("SELECT content FROM anvil.benchmark_task_groups WHERE id=%s", (row["task_group_id"],)).fetchone()["content"]
            require(len(group["tasks"]) == 4 and all(len(task["rubric"]["criteria"]) == 20
                    and {criterion["id"] for criterion in task["rubric"]["criteria"]} == set(CRITERIA)
                    and task["rubric"] == group["tasks"][0]["rubric"] for task in group["tasks"]))
            snapshots = connection.execute("SELECT snapshot FROM anvil.environment_task_bindings WHERE environment_id=%s", (row["environment_id"],)).fetchall()
            require(len(snapshots) == 4 and all(item["snapshot"]["evaluators"] == evaluators for item in snapshots))
            after = connection.execute("SELECT id,snapshot,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id",
                                       (config["project_id"], config["pack_id"])).fetchall()
            require(before == after)
            changed = deepcopy(row)
            changed["manifest"]["case_assignments"][0]["task_id"] = "KYC-wrong-product"
            changed["manifest_sha256"] = digest(changed["manifest"])
            refused = False
            try:
                validate(connection, changed)
            except HTTPException as error:
                refused = error.status_code == 409
            require(refused)
            connection.execute("SAVEPOINT synthetic_evaluator_revoke")
            try:
                connection.execute("INSERT INTO anvil.evaluator_revocations(id,project_id,configuration_id,created_by) VALUES(%s,%s,%s,%s)",
                    (str(uuid4()), config["project_id"], evaluators[0]["configuration_id"], config["user_id"]))
                refused = False
                try:
                    validate(connection, row)
                except HTTPException as error:
                    refused = error.status_code == 409 and "revoked or changed" in str(error.detail)
                require(refused)
            finally:
                connection.execute("ROLLBACK TO SAVEPOINT synthetic_evaluator_revoke")
                connection.execute("RELEASE SAVEPOINT synthetic_evaluator_revoke")
            validate(connection, row)
        with connections("app", foreign_project=str(uuid4())) as connection:
            require(not connection.execute("SELECT id FROM banking.anvil_imports WHERE id=%s", (imported["id"],)).fetchall())
            refused = False
            try:
                validate(connection, row)
            except (Denied, HTTPException):
                refused = True
            require(refused)
        return {"synthetic_rows": 200, "products": 4, "one_exact_assignment_per_row": True,
                "row_population_sha256": digest([{key: item[key] for key in ("id", "snapshot_sha256")} for item in before]),
                "shared_evaluator_configurations": 50, "rubric_criteria_per_task": 20,
                "wrong_assignment_foreign_project_revocation": "denied",
                "per_application_policy_registry": "not_exercised",
                "legal_acceptance": False, "model_performance": False}

    control("actual_four_product_registration_conservation_bindings", products)

    def checkpoint():
        from anvil.golden_phase_checkpoints import execute
        job = {"project_id": config["project_id"], "id": str(uuid4()), "plan_id": str(uuid4()), "lease_token": "synthetic-" + config["fixture_nonce"]}
        calls = []

        def interrupted():
            with connections() as connection:
                rows = connection.execute("SELECT checkpoint FROM anvil_golden_checkpoints.checkpoints WHERE thread_id LIKE %s", (config["project_id"] + ":" + job["id"] + ":%",)).fetchall()
                require(any(row["checkpoint"].get("channel_values", {}).get("phase") == "native_attempt_started" for row in rows))
            calls.append(True)
            raise RuntimeError("synthetic_control_interruption")

        try:
            execute(connections, job, interrupted)
        except RuntimeError as error:
            require(str(error) == "synthetic_control_interruption")
        else:
            raise ValueError("Interruption did not propagate")
        try:
            execute(connections, job, interrupted)
        except RuntimeError as error:
            require(str(error) == "golden_phase_attempt_already_recorded_no_replay")
        else:
            raise ValueError("Checkpoint replay accepted")
        require(calls == [True])
        return {"committed_before_effect": True, "fresh_saver_replay_denied": True, "synthetic_effect_count": len(calls)}

    control("actual_sql_checkpoint_interruption_no_replay", checkpoint)
    output = {"schema_version": "anvil.synthetic-sql-component-observations.v2", "controls": results,
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "fixture_nonce_sha256": digest(config["fixture_nonce"]),
              "golden_source_sha256": config["golden_source_sha256"], "broker_source_sha256": config["broker_source_sha256"],
              "runtime_image_sha256": config["runtime_image_sha256"], "native_qualified": False,
              "qualification_written": False, "model_calls_authorized": 0, "actual_model_calls": None,
              "missing_controls": ["per_application_policy_registry", "private_python_scoring", "physical_harbor_trial", "independent_model_request_absence"],
              "overall_budget_seconds": 180}
    print(json.dumps(output, sort_keys=True))
    return 0 if all(value["status"] == "passed" for value in results.values()) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, lambda *args: (_ for _ in ()).throw(ControlDeadline()))
    signal.alarm(180)
    try:
        raise SystemExit(run(read_config(args.config)))
    except (Exception, ControlDeadline) as error:
        print(json.dumps({"status": "blocked_or_unknown_no_replay", "exception_type": type(error).__name__,
                          "exception_frames": safe_exception_frames(error),
                          "native_qualified": False, "model_calls_authorized": 0, "actual_model_calls": None}))
        raise SystemExit(1) from None
