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
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4


class ControlDeadline(BaseException):
    """Do not let per-control failure capture consume the overall cutoff."""


def require(condition):
    if not condition:
        raise ValueError("Synthetic SQL control refused")


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
        "scheduler_dsn", "grader_dsn", "project_id", "user_id", "pack_id", "application_id",
        "snapshot_sha256", "golden_source_sha256", "broker_source_sha256", "runtime_image_sha256"})
    require(config["schema_version"] == "anvil.synthetic-sql-component-config.v1"
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
    params = {role: conninfo_to_dict(config[role + "_dsn"]) for role in ("scheduler", "grader")}
    for value in params.values():
        require(not set(value) - {"host", "port", "user", "password", "dbname", "sslmode"}
                and value.get("dbname") == config["database"])
    require(params["scheduler"].get("user") != params["grader"].get("user"))
    claimed = False

    @contextmanager
    def connections(role="scheduler", *, claim=False, foreign_project=None):
        nonlocal claimed
        with psycopg.connect(**params[role], connect_timeout=2, row_factory=dict_row,
                             options="-c statement_timeout=3000 -c lock_timeout=500") as connection:
            identity = connection.execute("SELECT current_database() AS database,session_user AS login").fetchone()
            require(identity["database"] == config["database"] and identity["login"] == params[role]["user"])
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
            enter(connection, "anvil_golden_" + role, foreign_project or config["project_id"])
            connection.execute("SELECT set_config('anvil.user',%s,true)", (config["user_id"],))
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
            results[name] = {"status": "failed", "exception_type": type(error).__name__}

    def isolation():
        for role, private in (("scheduler", "expectations"), ("grader", "scenarios")):
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
        return {"actual_disjoint_login_private_select_denials": 2, "foreign_project_rows": 0}

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
    output = {"schema_version": "anvil.synthetic-sql-component-observations.v1", "controls": results,
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "fixture_nonce_sha256": digest(config["fixture_nonce"]),
              "golden_source_sha256": config["golden_source_sha256"], "broker_source_sha256": config["broker_source_sha256"],
              "runtime_image_sha256": config["runtime_image_sha256"], "native_qualified": False,
              "qualification_written": False, "model_calls_authorized": 0, "actual_model_calls": None}
    print(json.dumps(output, sort_keys=True))
    return 0 if all(value["status"] == "passed" for value in results.values()) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, lambda *args: (_ for _ in ()).throw(ControlDeadline()))
    signal.alarm(120)
    try:
        raise SystemExit(run(read_config(args.config)))
    except (Exception, ControlDeadline) as error:
        print(json.dumps({"status": "blocked_or_unknown_no_replay", "exception_type": type(error).__name__,
                          "native_qualified": False, "model_calls_authorized": 0, "actual_model_calls": None}))
        raise SystemExit(1) from None
