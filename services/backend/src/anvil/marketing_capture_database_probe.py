"""Explicit operator no-model probe. Never called by inventory or API routes.

Only the injected capture API target is accepted. No target/query overrides,
credential issuance, case reads, writes, receipt publication or inference calls.
Unknown cancellation is a failure, never permission to retry the operation.
"""

import asyncio
from time import monotonic

from psycopg.rows import dict_row

from anvil.marketing_capture_database import DatabaseUnknown, _CaptureConnection, _cutoff, remaining
from anvil.marketing_capture_database_qualification import (
    CHECKS,
    runtime_identity,
    trusted_transport,
)
from anvil.marketing_capture_database_target import configuration
from anvil.praxis_generic_contract import digest


async def probe(*, absolute_deadline):
    """One original <=300s deadline includes both connections and cleanup."""
    original_seconds = remaining(absolute_deadline)
    if original_seconds > 300:
        raise ValueError("Capture qualification cutoff cannot exceed300seconds")
    parameters, target = configuration()
    identity = runtime_identity()
    trusted_transport(parameters)
    token = _cutoff.set(absolute_deadline)
    actor = observer = sleeper = None
    started = monotonic()
    try:
        async with asyncio.timeout(remaining(absolute_deadline)):
            # Observer is opened before cancellation, using the same fixed login
            # and original cutoff. No monitoring grant or elevated connection.
            observer = await _CaptureConnection.connect(row_factory=dict_row, **parameters)
            actor = await _CaptureConnection.connect(row_factory=dict_row, **parameters)
            for connection in (observer, actor):
                await connection.execute("SET TRANSACTION READ ONLY")
            measured = await (await actor.execute(
                "SELECT session_user::text AS login,current_user::text AS active,"
                "current_database() AS database,pg_backend_pid() AS pid,"
                "(SELECT backend_start FROM pg_stat_activity WHERE pid=pg_backend_pid()) AS backend_start,"
                "host(inet_server_addr()) AS address,inet_server_port() AS port,"
                "(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()) AS ssl,"
                "current_setting('transaction_read_only') AS read_only,"
                "NOT rolsuper AND NOT rolbypassrls AND NOT rolcreatedb AND NOT rolcreaterole "
                "AND NOT rolreplication AND rolcanlogin "
                "AND pg_has_role(session_user,'anvil_app','MEMBER') "
                "AND NOT pg_has_role(session_user,'anvil_worker','MEMBER') "
                "AND NOT pg_has_role(session_user,'anvil_golden_scheduler','MEMBER') "
                "AND NOT pg_has_role(session_user,'anvil_golden_grader','MEMBER') "
                "AND NOT pg_has_role(session_user,'anvil_capture_peer_writer','MEMBER') "
                "AND NOT pg_has_role(session_user,'anvil_capture_registrar','MEMBER') "
                "AND NOT pg_has_role(session_user,'anvil_capture_enrollment_owner','MEMBER') "
                "AND NOT pg_has_role(session_user,'anvil_private_grade_owner','MEMBER') "
                "AND (SELECT count(*)=2 AND bool_and(c.relrowsecurity IS TRUE AND c.relforcerowsecurity IS TRUE "
                "AND pg_catalog.has_table_privilege(session_user,c.oid,'SELECT') IS FALSE "
                "AND pg_catalog.has_any_column_privilege(session_user,c.oid,'SELECT') IS FALSE) "
                "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                "WHERE c.relkind='r' AND (n.nspname,c.relname) IN "
                "(('banking_private','expectations'),('campaign_private','references'))) AS restricted "
                "FROM pg_roles WHERE rolname=session_user"
            )).fetchone()
            if (not measured or measured["login"] != parameters["user"]
                    or measured["active"] != parameters["user"]
                    or measured["database"] != parameters["dbname"]
                    or measured["backend_start"] is None or measured["read_only"] != "on"
                    or measured["restricted"] is not True):
                raise ValueError("Actual scoped capture API identity required")
            if not parameters["host"].startswith("/") and (
                    measured["ssl"] is not True or measured["address"] != parameters["hostaddr"]
                    or measured["port"] != int(parameters["port"])):
                raise ValueError("Actual authenticated transport does not match target")
            original_pid, original_start = measured["pid"], measured["backend_start"]
            # Source-fixed harmless read-only query. Cancellation is requested
            # while time remains, using the ACTUAL production driver path.
            sleeper = asyncio.create_task(actor.execute("SELECT pg_sleep(300)"))
            await asyncio.sleep(min(.25, remaining(absolute_deadline) / 4))
            if sleeper.done():
                raise ValueError("Cancellation control did not execute")
            sleeper.cancel()
            try:
                await sleeper
            except DatabaseUnknown:
                pass
            else:
                raise ValueError("Cancellation control returned without unknown boundary")
            if not actor.capture_server_cancel_observed:
                raise ValueError("Actual server QueryCanceled acknowledgement required")
            while True:
                remaining(absolute_deadline)
                await observer.execute("SELECT pg_stat_clear_snapshot()")
                row = await (await observer.execute(
                    "SELECT NOT EXISTS(SELECT 1 FROM pg_stat_activity WHERE pid=%s AND backend_start=%s) AS gone",
                    (original_pid, original_start),
                )).fetchone()
                if row and row["gone"] is True:
                    break
                await asyncio.sleep(min(.05, remaining(absolute_deadline)))
            await observer.execute("ROLLBACK")
            await observer.close()
            if not observer.closed:
                raise DatabaseUnknown()
            remaining(absolute_deadline)
            # Nothing here publishes independent qualification. Independent QA
            # must review and retain this evidence before operator publication.
            target_observation = dict(measured)
            target_observation["backend_start"] = original_start.isoformat()
            role_profile = {"login": measured["login"], "restricted": True}
            controls = {key: {
                "check": key, "target_sha256": target, "observation": digest(target_observation),
                "server_cancel_acknowledged": actor.capture_server_cancel_observed,
                "exact_backend_gone": row["gone"], "observer_closed": observer.closed,
                "probe_source_sha256": identity["source_sha256"],
                "model_dispatch_scope": "this_fixed_probe_only",
            } for key in CHECKS}
            evidence = {
                "schema_version": "anvil.capture-database-probe-evidence.v1",
                "scope": "capture_api_database_target_only", "target_sha256": target,
                "runtime_identity": identity,
                "observed_target_sha256": digest(target_observation),
                "role_profile_sha256": digest(role_profile),
                # Retained only in the operator evidence, never the API
                # projection. Reviewers can recompute every reported hash.
                "target_observation": target_observation, "role_profile": role_profile,
                "control_observations": controls,
                "elapsed_seconds": monotonic() - started,
                "original_cutoff_seconds": original_seconds, "spending_authority": False,
                "checks": {key: {"status": "passed", "evidence_sha256": digest(controls[key])}
                           for key in CHECKS},
            }
            return evidence
    finally:
        # Do not leave background work after cancellation/timeout or swallow
        # uncertainty. Never reconnect/reissue the operation from cleanup.
        if sleeper is not None and not sleeper.done():
            sleeper.cancel()
        for connection in (actor, observer):
            if connection is not None:
                connection.pgconn.finish()
        if sleeper is not None and not sleeper.done():
            # Both sockets are now closed; join cancellation within the SAME
            # remaining cutoff, otherwise propagate unknown to the operator.
            try:
                async with asyncio.timeout(remaining(absolute_deadline)):
                    await sleeper
            except BaseException:
                pass
        _cutoff.reset(token)
