"""Evaluation framework versions and evaluator configurations, owned by the RL Gym (option B, D19, D20).

A configuration's first version comes from Studio's S7 binding through A-06; the same binding twice is the same
version. A fix is a new version the RL Gym creates under the same evaluator contract (criterion id, evidence type,
verdict vocabulary), qualified by known-case tests. A version never changes; deprecate and revoke are the RL Gym's
own decisions, impact report first, and Studio is told by event.
"""

import datetime as dt

from psycopg.types.json import Jsonb

from anvil.rlgym.common import GymError, audit, emit, require, sha
from anvil.rlgym.scoring import sandbox

KNOWN_CASE_EXPECT = {"allowed": "pass", "disallowed": "fail", "missing_evidence": "blocked"}


def _framework(c, runtime_id, version):
    fw = c.execute(
        "SELECT * FROM catalog.framework_versions WHERE runtime_id=%s AND version=%s",
        (runtime_id, version),
    ).fetchone()
    if not fw:
        raise GymError(
            "VALIDATION_FAILED",
            f"Framework {runtime_id} {version} is not installed",
            {"field": "framework"},
        )
    return fw


def _config_hash(framework_id, evidence_type, verdicts, config, known_cases):
    return sha(
        {
            "framework": framework_id,
            "evidence_type": evidence_type,
            "verdicts": verdicts,
            "config": config,
            "known_cases": known_cases,
        }
    )


def _validate_known_cases(known_cases):
    require(
        isinstance(known_cases, dict),
        "VALIDATION_FAILED",
        "known_cases must be an object",
        field="known_cases",
    )
    for name in KNOWN_CASE_EXPECT:
        case = known_cases.get(name)
        require(
            isinstance(case, dict) and "evidence" in case and "reference" in case,
            "VALIDATION_FAILED",
            f"known case '{name}' needs evidence and reference",
            field=f"known_cases.{name}",
        )
    for name, case in known_cases.items():
        require(
            case.get("expect", KNOWN_CASE_EXPECT.get(name))
            in ("pass", "partial", "fail", "blocked"),
            "VALIDATION_FAILED",
            f"known case '{name}' needs an expected verdict",
            field=f"known_cases.{name}.expect",
        )


def _event(c, ws, kind, row, extra=None):
    payload = {
        "id": row["id"],
        "version": row["version"],
        "state": row["state"],
        "criterion": row["criterion_id"],
        "template_id": row["source_template_id"],
        "template_version": row["source_template_version"],
        **(extra or {}),
    }
    emit(c, ws, f"evaluator.{kind}", f"{row['id']}@{row['version']}", payload)
    emit(
        c,
        ws,
        "evaluator.event",
        f"{row['id']}@{row['version']}",
        {"_path": "/api/v1/rlgym-events", "type": f"evaluator.{kind}", **payload},
        destination="studio",
    )


def create_from_studio(c, ws, actor, body):
    """A-06 POST /evaluators."""
    require(
        body.get("schema") == "rlgym.evaluator-create.v1",
        "VALIDATION_FAILED",
        "schema must be rlgym.evaluator-create.v1",
    )
    for field in (
        "id",
        "criterion",
        "capability",
        "evidence_type",
        "config",
        "known_cases",
        "framework",
        "template",
    ):
        require(
            body.get(field) not in (None, ""),
            "VALIDATION_FAILED",
            f"{field} is required",
            field=field,
        )
    cid = body["id"]
    require(
        cid == f"{body['capability']}:{body['criterion']}",
        "VALIDATION_FAILED",
        "id must be <capability>:<criterion>",
        field="id",
    )
    _validate_known_cases(body["known_cases"])
    fw = _framework(c, body["framework"]["runtime_id"], body["framework"]["version"])
    require(
        fw["state"] not in ("deprecated", "revoked"),
        "VALIDATION_FAILED",
        f"Framework {fw['id']} is {fw['state']}; no new configuration may use it",
        field="framework",
    )
    verdicts = body.get("verdict_vocabulary") or ["pass", "partial", "fail", "blocked"]
    h = _config_hash(fw["id"], body["evidence_type"], verdicts, body["config"], body["known_cases"])
    same = c.execute(
        "SELECT * FROM catalog.evaluator_configurations WHERE workspace_id=%s AND id=%s AND config_sha256=%s",
        (ws, cid, h),
    ).fetchone()
    if same:
        return same, False
    previous = c.execute(
        "SELECT * FROM catalog.evaluator_configurations WHERE workspace_id=%s AND id=%s ORDER BY version DESC LIMIT 1",
        (ws, cid),
    ).fetchone()
    if previous:
        _same_contract(previous, body["criterion"], body["evidence_type"], verdicts)
    version = (previous["version"] + 1) if previous else 1
    t = body["template"]
    row = c.execute(
        """INSERT INTO catalog.evaluator_configurations(workspace_id,id,version,framework_version_id,capability,criterion_id,
             evidence_type,verdict_vocabulary,weight,config,config_sha256,known_cases,source_template_id,source_template_key,
             source_template_version,state,created_by)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'registered','studio') RETURNING *""",
        (
            ws,
            cid,
            version,
            fw["id"],
            body["capability"],
            body["criterion"],
            body["evidence_type"],
            verdicts,
            body.get("weight", 1),
            Jsonb(body["config"]),
            h,
            Jsonb(body["known_cases"]),
            t["id"],
            t.get("key", ""),
            int(t["version"]),
        ),
    ).fetchone()
    audit(
        c,
        ws,
        actor,
        "evaluator.registered",
        f"{cid}@{version}",
        details={"config_sha256": h, "via": "A-06"},
    )
    _event(c, ws, "registered", row)
    return row, True


def _same_contract(previous, criterion, evidence_type, verdicts):
    require(
        previous["criterion_id"] == criterion
        and previous["evidence_type"] == evidence_type
        and list(previous["verdict_vocabulary"]) == list(verdicts),
        "VALIDATION_FAILED",
        "A new version must keep the evaluator contract (criterion, evidence type, verdict vocabulary)",
        criterion=previous["criterion_id"],
        evidence_type=previous["evidence_type"],
    )


def get_version(c, ws, cid, version):
    row = c.execute(
        "SELECT * FROM catalog.evaluator_configurations WHERE workspace_id=%s AND id=%s AND version=%s",
        (ws, cid, int(version)),
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", f"{cid} v{version} not found")
    return row


def run_known_case_tests(c, ws, actor, cid, version):
    """A-06 POST /evaluators/{id}/test: allowed → pass, disallowed → fail, missing evidence → blocked (all distinct).
    Same configuration, same verdicts: the receipt hash covers inputs and verdicts."""
    row = get_version(c, ws, cid, version)
    require(
        row["state"] != "revoked",
        "VALIDATION_FAILED",
        "A revoked configuration is not tested again",
    )
    fw = c.execute(
        "SELECT * FROM catalog.framework_versions WHERE id=%s", (row["framework_version_id"],)
    ).fetchone()
    checks = []
    for name, case in row["known_cases"].items():
        expect = case.get("expect", KNOWN_CASE_EXPECT.get(name))
        out = sandbox.run(fw, row["config"], case["evidence"], case["reference"])
        checks.append(
            {
                "name": name,
                "case_id": case.get("case_id"),
                "expected": expect,
                "verdict": out["verdict"],
                "result": "pass" if out["verdict"] == expect else "fail",
                "detail": out.get("detail", []),
            }
        )
    distinct = len({ch["verdict"] for ch in checks if ch["name"] in KNOWN_CASE_EXPECT}) == 3
    passed = all(ch["result"] == "pass" for ch in checks) and distinct
    result = "qualified" if passed else "failed"
    receipt_body = {
        "subject": f"{cid}@{version}",
        "config_sha256": row["config_sha256"],
        "framework": fw["id"],
        "checks": [{k: ch[k] for k in ("name", "case_id", "expected", "verdict")} for ch in checks],
    }
    receipt_id = "kct-" + sha(receipt_body)[:12]
    c.execute(
        """INSERT INTO catalog.qualification_receipts(receipt_id,workspace_id,subject_kind,subject_id,subject_version,result,
             failure_class,mode,checks,receipt_sha256)
           VALUES(%s,%s,'evaluator_configuration',%s,%s,%s,%s,'sandboxed_python_subprocess',%s,%s)
           ON CONFLICT (receipt_id) DO NOTHING""",
        (
            receipt_id,
            ws,
            cid,
            str(version),
            result,
            None if passed else "evaluator_defect",
            Jsonb(checks),
            sha(receipt_body),
        ),
    )
    old_state = new_state = row["state"]
    if row["state"] in ("registered", "failed", "qualified"):
        new_state = "qualified" if passed else "failed"
    c.execute(
        """UPDATE catalog.evaluator_configurations SET known_case_receipt_id=%s, state=%s,
             state_changed_by=CASE WHEN state<>%s THEN %s ELSE state_changed_by END,
             state_changed_at=CASE WHEN state<>%s THEN now() ELSE state_changed_at END
           WHERE workspace_id=%s AND id=%s AND version=%s""",
        (receipt_id, new_state, new_state, actor.id, new_state, ws, cid, int(version)),
    )
    audit(
        c,
        ws,
        actor,
        "evaluator.known_case_tests",
        f"{cid}@{version}",
        details={"receipt_id": receipt_id, "result": result},
    )
    row = get_version(c, ws, cid, version)
    if new_state in ("qualified", "failed") and new_state != old_state:
        projects_moved = []
        if new_state == "qualified":
            from anvil.rlgym.projects import service as projects

            projects_moved = projects.reselect_all(
                c,
                ws,
                trigger={
                    "event": "evaluator.qualified",
                    "configuration": cid,
                    "version": int(version),
                },
            )
        _event(
            c,
            ws,
            new_state,
            row,
            {
                "receipt_id": receipt_id,
                "new_cohort_projects": [p for p in projects_moved if p.get("evaluator_changed")],
            },
        )
    return {
        "receipt_id": receipt_id,
        "result": result,
        "checks": checks,
        "id": cid,
        "version": int(version),
        "state": row["state"],
    }


def create_fix_version(c, ws, actor, cid, body):
    """POST /evaluators/{id}/versions: the RL Gym's own fix (D20). No Studio inbox item unless the S7 criterion changes."""
    actor.require_person()
    fix_of = body.get("fix_of")
    reason = (body.get("reason") or "").strip()
    require(reason, "VALIDATION_FAILED", "A reason is required for a fix version", field="reason")
    base = get_version(c, ws, cid, fix_of)
    require(
        base["state"] != "revoked" or body.get("allow_from_revoked") is True,
        "VALIDATION_FAILED",
        "Fix from a version that is not revoked, or confirm allow_from_revoked",
    )
    config = body.get("config") or base["config"]
    known_cases = {**base["known_cases"], **(body.get("known_cases") or {})}
    _validate_known_cases(known_cases)
    fw = c.execute(
        "SELECT * FROM catalog.framework_versions WHERE id=%s",
        (body.get("framework_version_id") or base["framework_version_id"],),
    ).fetchone()
    require(
        fw and fw["state"] not in ("deprecated", "revoked"),
        "VALIDATION_FAILED",
        "Framework is not usable for new versions",
    )
    h = _config_hash(
        fw["id"], base["evidence_type"], list(base["verdict_vocabulary"]), config, known_cases
    )
    require(
        not c.execute(
            "SELECT 1 FROM catalog.evaluator_configurations WHERE workspace_id=%s AND id=%s AND config_sha256=%s",
            (ws, cid, h),
        ).fetchone(),
        "CONFLICT",
        "An identical configuration version already exists",
    )
    latest = c.execute(
        "SELECT max(version) v FROM catalog.evaluator_configurations WHERE workspace_id=%s AND id=%s",
        (ws, cid),
    ).fetchone()["v"]
    row = c.execute(
        """INSERT INTO catalog.evaluator_configurations(workspace_id,id,version,framework_version_id,capability,criterion_id,
             evidence_type,verdict_vocabulary,weight,config,config_sha256,fix_of_version,fix_reason,fix_source,known_cases,
             source_template_id,source_template_key,source_template_version,state,created_by)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'registered','rlgym') RETURNING *""",
        (
            ws,
            cid,
            latest + 1,
            fw["id"],
            base["capability"],
            base["criterion_id"],
            base["evidence_type"],
            list(base["verdict_vocabulary"]),
            base["weight"],
            Jsonb(config),
            h,
            int(fix_of),
            reason,
            body.get("source"),
            Jsonb(known_cases),
            base["source_template_id"],
            base["source_template_key"],
            base["source_template_version"],
        ),
    ).fetchone()
    audit(
        c, ws, actor, "evaluator.fix_version", f"{cid}@{row['version']}", reason, {"fix_of": fix_of}
    )
    _event(c, ws, "registered", row, {"fix_of": fix_of})
    test = run_known_case_tests(c, ws, actor, cid, row["version"])
    return {"configuration": get_version(c, ws, cid, row["version"]), "known_case_test": test}


def deprecate(c, ws, actor, cid, version, reason):
    actor.require_person()
    require((reason or "").strip(), "VALIDATION_FAILED", "A reason is required", field="reason")
    row = get_version(c, ws, cid, version)
    require(
        row["state"] == "qualified",
        "VALIDATION_FAILED",
        "Only a qualified version can be deprecated",
    )
    c.execute(
        """UPDATE catalog.evaluator_configurations SET state='deprecated', state_reason=%s, state_changed_by=%s,
                 state_changed_at=now() WHERE workspace_id=%s AND id=%s AND version=%s""",
        (reason, actor.id, ws, cid, int(version)),
    )
    audit(c, ws, actor, "evaluator.deprecated", f"{cid}@{version}", reason)
    row = get_version(c, ws, cid, version)
    from anvil.rlgym.projects import service as projects

    projects.reselect_all(
        c,
        ws,
        trigger={"event": "evaluator.deprecated", "configuration": cid, "version": int(version)},
    )
    _event(c, ws, "deprecated", row, {"reason": reason})
    return row


def impact(c, ws, cid, version):
    row = get_version(c, ws, cid, version)
    replacement = c.execute(
        """SELECT e.version, e.state, e.known_case_receipt_id FROM catalog.evaluator_configurations e
           JOIN catalog.framework_versions f ON f.id=e.framework_version_id
           WHERE e.workspace_id=%s AND e.id=%s AND e.version<>%s AND e.state='qualified' AND f.state<>'revoked'
           ORDER BY e.version DESC LIMIT 1""",
        (ws, cid, int(version)),
    ).fetchone()
    templates = c.execute(
        """SELECT DISTINCT a.template_id, a.version, a.name FROM catalog.template_criteria t
           JOIN catalog.template_activations a USING (workspace_id, template_id, version)
           WHERE t.workspace_id=%s AND t.configuration_id=%s""",
        (ws, cid),
    ).fetchall()
    projects_on = c.execute(
        """SELECT p.project_id, p.name, r.kind, r.resolved_version, r.pinned_version FROM projects.evaluator_selection_rules r
           JOIN projects.projects p USING (workspace_id, project_id)
           WHERE r.workspace_id=%s AND r.configuration_id=%s AND r.valid_to IS NULL""",
        (ws, cid),
    ).fetchall()
    affected = [
        p
        for p in projects_on
        if p["resolved_version"] == int(version) or p["pinned_version"] == int(version)
    ]
    return {
        "subject": f"{cid} v{version}",
        "state": row["state"],
        "replacement": (
            {
                "version": replacement["version"],
                "state": "qualified",
                "known_case_receipt_id": replacement["known_case_receipt_id"],
            }
            if replacement
            else None
        ),
        "templates": templates,
        "projects": affected,
        "runs": {
            "completed_flagged": 0,
            "running": 0,
            "note": "Runs arrive with work package 2.7; completed runs are never changed, only flagged.",
        },
        "b4": replacement is None,
    }


def revoke(c, ws, actor, cid, version, reason):
    actor.require_person()
    require((reason or "").strip(), "VALIDATION_FAILED", "A reason is required", field="reason")
    row = get_version(c, ws, cid, version)
    require(
        row["state"] in ("qualified", "deprecated", "registered", "failed"),
        "VALIDATION_FAILED",
        "Already revoked",
    )
    report = impact(c, ws, cid, version)
    replacement = report["replacement"]["version"] if report["replacement"] else None
    c.execute(
        """UPDATE catalog.evaluator_configurations SET state='revoked', state_reason=%s, state_changed_by=%s,
                 state_changed_at=now(), replaced_by_version=%s WHERE workspace_id=%s AND id=%s AND version=%s""",
        (reason, actor.id, replacement, ws, cid, int(version)),
    )
    audit(c, ws, actor, "evaluator.revoked", f"{cid}@{version}", reason, {"impact": report})
    from anvil.rlgym.projects import service as projects

    projects.reselect_all(
        c, ws, trigger={"event": "evaluator.revoked", "configuration": cid, "version": int(version)}
    )
    row = get_version(c, ws, cid, version)
    _event(
        c,
        ws,
        "revoked",
        row,
        {
            "reason": reason,
            "replacement": replacement,
            "impact": {
                "templates": [f"{t['template_id']}@{t['version']}" for t in report["templates"]],
                "projects": [p["project_id"] for p in report["projects"]],
                "runs": 0,
            },
        },
    )
    return {"configuration": row, "impact": report}


# --- frameworks ------------------------------------------------------------------------------------------------


def framework_impact(c, ws, fid):
    fw = c.execute("SELECT * FROM catalog.framework_versions WHERE id=%s", (fid,)).fetchone()
    if not fw:
        raise GymError("NOT_FOUND", "Framework version not found")
    configs = c.execute(
        """SELECT id, version, state FROM catalog.evaluator_configurations WHERE workspace_id=%s AND framework_version_id=%s
           AND state<>'revoked' ORDER BY id, version""",
        (ws, fid),
    ).fetchall()
    return {
        "subject": f"{fw['runtime_id']} {fw['version']}",
        "framework": fw,
        "configurations": configs,
        "templates": sorted({c2["id"].split(":")[0] for c2 in configs}),
    }


def framework_state(c, ws, actor, fid, target, reason):
    actor.require_person()
    require((reason or "").strip(), "VALIDATION_FAILED", "A reason is required", field="reason")
    fw = c.execute(
        "SELECT * FROM catalog.framework_versions WHERE id=%s FOR UPDATE", (fid,)
    ).fetchone()
    if not fw:
        raise GymError("NOT_FOUND", "Framework version not found")
    if target == "deprecated":
        require(
            fw["state"] in ("qualified", "registered"),
            "VALIDATION_FAILED",
            f"Cannot deprecate a {fw['state']} framework",
        )
    else:
        require(
            fw["state"] == "deprecated",
            "VALIDATION_FAILED",
            "Deprecate a framework version before revoking it",
        )
    report = framework_impact(c, ws, fid)
    c.execute(
        "UPDATE catalog.framework_versions SET state=%s, state_reason=%s, state_changed_by=%s, state_changed_at=now() WHERE id=%s",
        (target, reason, actor.id, fid),
    )
    audit(c, ws, actor, f"framework.{target}", fid, reason, {"impact": report["configurations"]})
    if target == "revoked":
        from anvil.rlgym.projects import service as projects

        projects.reselect_all(c, ws, trigger={"event": "framework.revoked", "framework": fid})
    payload = {
        "id": fid,
        "reason": reason,
        "configurations": [f"{x['id']}@{x['version']}" for x in report["configurations"]],
    }
    emit(c, ws, f"framework.{target}", fid, payload)
    emit(
        c,
        ws,
        "evaluator.event",
        fid,
        {"_path": "/api/v1/rlgym-events", "type": f"framework.{target}", **payload},
        destination="studio",
    )
    return {
        "framework": c.execute(
            "SELECT * FROM catalog.framework_versions WHERE id=%s", (fid,)
        ).fetchone(),
        "impact": report,
    }


def list_configurations(c, ws, q=None, state=None):
    sql = """SELECT e.*, f.runtime_id, f.version AS framework_version,
               r.checks AS known_case_checks, r.result AS known_case_result, r.issued_at AS known_case_at
             FROM catalog.evaluator_configurations e JOIN catalog.framework_versions f ON f.id=e.framework_version_id
             LEFT JOIN catalog.qualification_receipts r ON r.receipt_id=e.known_case_receipt_id
             WHERE e.workspace_id=%s"""
    params = [ws]
    if q:
        sql += " AND (e.id ILIKE %s OR e.criterion_id ILIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    if state:
        sql += " AND e.state=%s"
        params.append(state)
    return c.execute(sql + " ORDER BY e.id, e.version DESC", params).fetchall()


def now_iso():
    return dt.datetime.now(dt.UTC).isoformat()
