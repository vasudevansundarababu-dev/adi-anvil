"""Dedicated scheduler persistence. Never imported by agent API routes.

Requires a separately provisioned scheduler connection. The ordinary application
and worker roles cannot seed/reset or read private controls/expectations. For
local qualification only the isolated migration connection is used. No Docker.
"""

import secrets
from copy import deepcopy

from psycopg.types.json import Jsonb

from anvil.db import digest, uid
from anvil.golden_kyc_data import VERSION, generate
from anvil.golden_kyc_engine import Denied, advance, execute, initial
from anvil.golden_kyc_evaluators import opa_guard


def binding(c, project, pack):
    from anvil.golden_kyc_policy import library

    row = c.execute(
        "SELECT manifest FROM banking.packs WHERE project_id=%s AND id=%s", (project, pack)
    ).fetchone()
    if (
        not row
        or row["manifest"].get("version") != VERSION
        or row["manifest"].get("policy_sha256") != digest(library())
    ):
        raise Denied("Frozen environment/policy binding changed")
    return row["manifest"]


def seed(c, project, user, *, include_expectations=False):
    c.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("golden-seed:" + str(project),)
    )
    manifest, applications, controls = generate()
    existing = c.execute(
        "SELECT id,manifest FROM banking.packs WHERE project_id=%s AND manifest->>'version'=%s AND manifest->>'origin'='original_constraint_generator'",
        (project, VERSION),
    ).fetchone()
    if existing:
        if existing["manifest"] != manifest:
            raise ValueError("Existing immutable pack differs")
        return {"pack_id": str(existing["id"]), "manifest": manifest}
    identifier = uid()
    c.execute(
        "INSERT INTO banking.packs(id,project_id,manifest,created_by) VALUES(%s,%s,%s,%s)",
        (identifier, project, Jsonb(manifest), user),
    )
    for app, control in zip(applications, controls, strict=True):
        c.execute(
            "INSERT INTO banking.applications VALUES(%s,%s,%s,%s,%s)",
            (app["id"], project, identifier, Jsonb(app), digest(app)),
        )
        expectation = {
            k: control[k] for k in ("intended_decision", "independent_expectation_review")
        }
        service = {k: v for k, v in control.items() if k not in expectation}
        c.execute(
            "INSERT INTO banking_private.scenarios VALUES(%s,%s,%s,%s)",
            (project, identifier, app["id"], Jsonb(service)),
        )
        if include_expectations:
            c.execute(
                "INSERT INTO banking_private.expectations VALUES(%s,%s,%s,%s)",
                (project, identifier, app["id"], Jsonb(expectation)),
            )
    return {"pack_id": identifier, "manifest": manifest}


def create_trial(c, project, user, pack, application, model_label, repetition):
    pack_manifest = binding(c, project, pack)
    if (
        not isinstance(model_label, str)
        or not 1 <= len(model_label) <= 100
        or type(repetition) is not int
        or not 1 <= repetition <= 10
    ):
        raise Denied("Invalid trial labels")
    row = c.execute(
        "SELECT snapshot FROM banking.applications WHERE project_id=%s AND pack_id=%s AND id=%s",
        (project, pack, application),
    ).fetchone()
    if not row:
        raise Denied("Resource not found")
    identifier, token = uid(), secrets.token_urlsafe(32)
    state = initial(row["snapshot"])
    c.execute(
        "INSERT INTO banking.trials(id,project_id,pack_id,application_id,assigned_user,model_label,repetition,state,credential_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            pack,
            application,
            user,
            model_label,
            repetition,
            Jsonb(state),
            digest(token),
        ),
    )
    event(
        c,
        project,
        identifier,
        0,
        "reset",
        {
            "seed": pack_manifest.get("seed"),
            "snapshot_sha256": digest(row["snapshot"]),
            "state_sha256": digest(state),
        },
    )
    # Token is returned once through the authenticated scheduler result. Stored
    # command result is scoped to its submitting user, never included in exports.
    return {"trial_id": identifier, "generation": 0, "trial_token": token, "model_execution": False}


def event(c, project, trial, generation, action, record):
    sequence = c.execute(
        "SELECT coalesce(max(sequence),0)+1 AS n FROM banking.events WHERE trial_id=%s AND generation=%s",
        (trial, generation),
    ).fetchone()["n"]
    c.execute(
        "INSERT INTO banking.events(id,project_id,trial_id,generation,sequence,action,record) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (uid(), project, trial, generation, sequence, action, Jsonb(record)),
    )


def locked(c, project, user, identifier):
    row = c.execute(
        "SELECT * FROM banking.trials WHERE id=%s AND project_id=%s AND assigned_user=%s FOR UPDATE",
        (identifier, project, user),
    ).fetchone()
    if not row:
        raise Denied("Resource not found")
    return row


def step(c, project, user, identifier, generation, token, action, arguments, *, absolute_deadline=None):
    row = locked(c, project, user, identifier)
    binding(c, project, row["pack_id"])
    if not c.execute(
        "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active AND m.role IN ('admin','rl-engineer')",
        (project, user),
    ).fetchone():
        raise Denied("Current assignment membership revoked")
    if (
        type(generation) is not int
        or row["generation"] != generation
        or not secrets.compare_digest(row["credential_sha256"], digest(token))
    ):
        raise Denied("Stale generation or credentials")
    if row["closed"]:
        raise Denied("Trial closed")
    controls = c.execute(
        "SELECT controls FROM banking_private.scenarios WHERE project_id=%s AND pack_id=%s AND application_id=%s",
        (project, row["pack_id"], row["application_id"]),
    ).fetchone()["controls"]
    state = deepcopy(row["state"])
    try:
        allowed = {
            "application.read",
            "documents.list",
            "document.read",
            "document.compare",
            "policy.read",
            "operation.lookup",
            "operation.read",
            "information.request",
            "information.read",
            "finding.write",
            "finding.resolve",
            "specialist.refer",
            "specialist.read",
            "search",
            "search.read",
            "recommend",
        }
        allowed.update(
            f"{kind}.check"
            for kind in ("identity", "document", "address", "screening", "authority")
        )
        policy = opa_guard(
            {
                "assigned_case": str(row["assigned_user"]) == str(user),
                "document_fields": not set(arguments) & {"sql", "shell", "headers"},
                "role": True,
                "protected_writes": action in allowed,
                "public_query": action != "search" or isinstance(arguments.get("query"), str),
                "destinations": not set(arguments) & {"url", "destination", "email", "host"},
                "disclosure": not set(arguments) & {"recipient", "export_customer"},
                "decision_authority": action in allowed,
                "private_evaluator": action in allowed,
                "request_bounds": len(str(arguments)) <= 20000,
            }
        )
        if not policy["allow"]:
            state["counters"]["calls"] = min(100, state["counters"]["calls"] + 1)
            raise Denied(
                "Policy enforcement denied action"
                if policy["outcome"] != "error"
                else "Qualified OPA unavailable; fail closed"
            )
        policy_document = None
        if (action == "document.read" and isinstance(arguments.get("id"), str)
                and arguments["id"].startswith("policy-doc-v2:")):
            from anvil.golden_kyc_state_checks import materialized

            # Charge and enforce the unchanged episode deadline/call limit before
            # the privileged read. The placeholder never leaves this transaction.
            execute(state, controls, action, arguments,
                    policy_document={"document_id": arguments["id"]})
            try:
                policy_document = materialized(
                    c, project, identifier, generation, state["application"]["governing_state"],
                    user=user, absolute_deadline=absolute_deadline, document_id=arguments["id"],
                )
            except ValueError:
                raise Denied("Bound policy document unavailable") from None
            if not isinstance(policy_document, dict) or policy_document.get("document_id") != arguments["id"]:
                raise Denied("Bound policy document unavailable")
            result = policy_document
        else:
            result = execute(state, controls, action, arguments)
        if action == "policy.read":
            from anvil.golden_kyc_state_checks import materialized

            public_rules = materialized(
                c, project, identifier, generation, state["application"]["governing_state"],
                user=user, absolute_deadline=absolute_deadline,
            )
            if public_rules:
                result = result | public_rules
                state["reads"] += [
                    rule["id"] + "@" + rule["version"]
                    for rule in public_rules.get("bound_common_rules", []) + public_rules.get("bound_state_rules", [])
                ]
        from anvil.golden_kyc_source import source_hash
        from anvil.task_safety_runtime import inject

        result = inject(c, project, identifier, generation, action, result, source_hash)
        status = "completed"
    except Denied as exc:
        # Preserve denied calls/counters without partial business mutations.
        charged = state["counters"]["calls"]
        state = deepcopy(row["state"])
        state["counters"]["calls"] = charged
        result, status = {"error": str(exc)}, "denied"
    from anvil.golden_kyc_source import source_hash
    from anvil.task_safety_runtime import observe_effect

    observe_effect(
        c, project, identifier, generation, action, arguments, status, result, source_hash
    )
    c.execute(
        "UPDATE banking.trials SET state=%s,closed=%s WHERE id=%s",
        (Jsonb(state), state["final"] is not None, identifier),
    )
    event(
        c,
        project,
        identifier,
        generation,
        action,
        {
            "status": status,
            "arguments_sha256": digest(arguments),
            "result": result,
            "policy": policy,
            "state_sha256": digest(state),
        },
    )
    if state["final"] is not None:
        seal(c, project, identifier, generation, state)
        c.execute(
            "INSERT INTO banking.recommendations(id,project_id,trial_id,generation,content) VALUES(%s,%s,%s,%s,%s)",
            (uid(), project, identifier, generation, Jsonb(state["final"])),
        )
    return {"status": status, "result": result}


def reset(c, project, user, identifier):
    """Scheduler-only reset; old events/recommendations/results never deleted."""
    row = locked(c, project, user, identifier)
    binding(c, project, row["pack_id"])
    seal(c, project, identifier, row["generation"], row["state"])
    snapshot = c.execute(
        "SELECT snapshot FROM banking.applications WHERE project_id=%s AND pack_id=%s AND id=%s",
        (project, row["pack_id"], row["application_id"]),
    ).fetchone()["snapshot"]
    generation, token = row["generation"] + 1, secrets.token_urlsafe(32)
    state = initial(snapshot)
    c.execute(
        "UPDATE banking.trials SET state=%s,generation=%s,credential_sha256=%s,closed=false WHERE id=%s",
        (Jsonb(state), generation, digest(token), identifier),
    )
    event(
        c,
        project,
        identifier,
        generation,
        "reset",
        {
            "seed": binding(c, project, row["pack_id"]).get("seed"),
            "snapshot_sha256": digest(snapshot),
            "state_sha256": digest(state),
        },
    )
    return {"trial_id": str(identifier), "generation": generation, "trial_token": token}


def seal(c, project, trial, generation, state):
    c.execute(
        "INSERT INTO banking.seals(project_id,trial_id,generation,state,state_sha256) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(trial_id,generation) DO NOTHING",
        (project, trial, generation, Jsonb(state), digest(state)),
    )


def tick(c, project, user, identifier, **kwargs):
    row = locked(c, project, user, identifier)
    if row["closed"]:
        raise Denied("Trial closed")
    controls = c.execute(
        "SELECT controls FROM banking_private.scenarios WHERE project_id=%s AND pack_id=%s AND application_id=%s",
        (project, row["pack_id"], row["application_id"]),
    ).fetchone()["controls"]
    state = deepcopy(row["state"])
    advance(state, controls, **kwargs)
    c.execute("UPDATE banking.trials SET state=%s WHERE id=%s", (Jsonb(state), identifier))
    event(
        c,
        project,
        identifier,
        row["generation"],
        "scheduler.tick",
        {"clock": state["clock"], "active_seconds": state["active_seconds"]},
    )


def process_one(c):
    """Single committed command; caller owns transaction. No retry after error."""
    command = c.execute(
        "SELECT * FROM banking.commands WHERE status='queued' ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1"
    ).fetchone()
    if not command:
        return None
    project, user, args = command["project_id"], command["requested_by"], command["arguments"]
    roles = [
        r["role"]
        for r in c.execute(
            "SELECT m.role FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active",
            (project, user),
        ).fetchall()
    ]
    try:
        with c.transaction():
            if command["kind"] in ("seed", "trial", "run") and "admin" not in roles:
                raise Denied("Current project Admin required")
            if command["kind"] == "seed":
                result = seed(c, project, user)
            elif command["kind"] == "trial":
                result = create_trial(
                    c,
                    project,
                    user,
                    args["pack_id"],
                    args["application_id"],
                    args["model_label"],
                    args["repetition"],
                )
            elif command["kind"] == "run":
                result = prepare_run(c, project, user, args["pack_id"], args["repetitions"])
            else:
                if not set(roles) & {"admin", "rl-engineer"}:
                    raise Denied("Current engineer membership required")
                result = step(
                    c,
                    project,
                    user,
                    args["trial_id"],
                    args["generation"],
                    args["trial_token"],
                    args["action"],
                    args["arguments"],
                )
        status = "denied" if result.get("status") == "denied" else "completed"
    except Denied as exc:
        result, status = {"error": str(exc)}, "denied"
    except Exception:
        result, status = (
            {"error": "Scheduler failed; retained command, no automatic retry"},
            "error",
        )
    c.execute(
        "UPDATE banking.commands SET status=%s,result=%s WHERE id=%s",
        (status, Jsonb(result), command["id"]),
    )
    return {"command_id": str(command["id"]), "status": status}


def prepare_run(c, project, user, pack, repetitions, *, case_ids=None):
    """Versioned cases × software control × repetition; no provider dispatch."""
    if type(repetitions) is not int or not 1 <= repetitions <= 10:
        raise Denied("Repetition count out of bounds")
    manifest = binding(c, project, pack)
    applications = c.execute(
        "SELECT id,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id",
        (project, pack),
    ).fetchall()
    if case_ids is None and len(applications) != 200:
        raise Denied("Exact200-application pack required")
    if case_ids is not None and (
        not 5 <= len(case_ids) <= 10000
        or len(set(case_ids)) != len(case_ids)
        or set(case_ids) != {a["id"] for a in applications}
    ):
        raise Denied("Exact immutable case membership required")
    case_count = len(applications)
    identifier = uid()
    profile = {
        "schema_version": "anvil.golden-kyc-run.v1",
        "environment_version": VERSION,
        "environment_manifest_sha256": digest(manifest),
        "applications": applications,
        "models": [{"id": "software-control", "kind": "software_only_no_model"}],
        "repetitions": repetitions,
        "planned_cells": case_count * repetitions,
        "reset_before_each_cell": True,
        "paid_calls": False,
        "model_performance": False,
        "runtime_qualification": manifest["environment"]["qualification"],
    }
    c.execute(
        "INSERT INTO banking.runs(id,project_id,pack_id,created_by,profile,profile_sha256) VALUES(%s,%s,%s,%s,%s,%s)",
        (identifier, project, pack, user, Jsonb(profile), digest(profile)),
    )
    for application in applications:
        for repetition in range(1, repetitions + 1):
            trial = create_trial(
                c, project, user, pack, application["id"], "software-control", repetition
            )
            c.execute(
                "INSERT INTO banking.run_cells VALUES(%s,%s,%s,'software-control',%s,%s)",
                (project, identifier, application["id"], repetition, trial["trial_id"]),
            )
    return {
        "run_id": identifier,
        "planned_cells": case_count * repetitions,
        "status": "prepared_not_executed",
        "model_performance": False,
    }
