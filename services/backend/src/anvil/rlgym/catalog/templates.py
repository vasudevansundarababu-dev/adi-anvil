"""Template activation (A-03): validate the execution part, run known-case tests, activate the exact hash.

Release steps 7 (validate), 8 (known-case tests) and 10 (activation). The release fixes evaluator contracts, not
configuration versions (D20); every run binds per rule at admission.
"""

from psycopg.types.json import Jsonb

from anvil.rlgym.catalog import evaluators, selection, verifier
from anvil.rlgym.common import GymError, audit, emit, require, sha


def _required(doc):
    for field in (
        "template_id",
        "key",
        "version",
        "name",
        "mode",
        "spec_sha256",
        "bindings",
        "criteria",
        "workflow",
        "case_dimensions",
        "pass_mark",
        "forge_template_id",
        "forge_version",
    ):
        require(
            doc.get(field) not in (None, ""),
            "VALIDATION_FAILED",
            f"{field} is required",
            field=field,
        )
    require(
        doc["mode"] in ("single_agent", "multi_agent"),
        "VALIDATION_FAILED",
        "Unknown mode",
        field="mode",
    )


def validate(c, ws, doc, allow_test=False):
    """`allow_test`: a test-channel activation may bind Studio's test-channel environment versions."""
    _required(doc)
    checks = []
    bound = []
    for b in doc["bindings"]:
        rule = {"contract_id": b["contract_id"], **b["rule"]}
        if rule["kind"] == "pinned":
            rule["pinned_version_id"] = rule.get("pinned_version_id")
        pick, code, reason = selection.resolve_environment(c, rule, allow_test=allow_test)
        if pick:
            bound.append(pick)
        checks.append(
            {
                "check": "environment_can_bind",
                "alias": b["alias"],
                "ok": pick is not None,
                "binds_now": pick["id"] if pick else None,
                "reason": None if pick else f"{code}: {reason}",
            }
        )
    for cr in doc["criteria"]:
        versions = selection.selectable_configurations(c, ws, cr["configuration_id"])
        ok = bool(versions) and versions[0]["evidence_type"] == cr["evidence_type"]
        checks.append(
            {
                "check": "criterion_can_bind",
                "criterion": cr["criterion_id"],
                "ok": ok,
                "binds_now": f"{cr['configuration_id']} v{versions[0]['version']}"
                if versions
                else None,
                "reason": None
                if ok
                else ("evidence type differs" if versions else "no qualified configuration"),
            }
        )
    checks += _verifier_checks(c, ws, doc, bound)
    checks += _edge_case_checks(doc)
    checks += _policy_binding_checks(doc)
    checks += _file_checks(doc)
    checks.append(
        {
            "check": "runtime_supports_mode",
            "ok": doc["mode"] == "single_agent",
            "reason": None
            if doc["mode"] == "single_agent"
            else "multi-agent runtime profiles are later (D-03)",
        }
    )
    return {"valid": all(ch["ok"] for ch in checks), "checks": checks}


def _verifier_checks(c, ws, doc, bound):
    """Verifier blocks (D21): every block must run on the environment version the template binds now (declared
    collections, fields and operations), with known rubrics and failure codes; and the criterion must bind a
    verifier-blocks configuration."""
    out = []
    source = doc.get("expected_values_from")
    taxonomy = doc.get("failure_taxonomy") or []
    for cr in doc["criteria"]:
        blocks = cr.get("verifier_blocks")
        if not blocks:
            continue
        reasons = []
        if not bound:
            reasons.append("no environment version binds now, so the blocks cannot be checked")
        for env in bound:
            row = c.execute(
                "SELECT * FROM catalog.environment_versions WHERE id=%s", (env["id"],)
            ).fetchone()
            if not (row and row.get("schema")):
                reasons.append(f"{env['id']} declares no collections (schema.collections)")
                continue
            reasons += verifier.check_blocks(verifier.legacy(blocks), row, source, taxonomy)
        reasons += verifier.plugin_reasons(c, blocks, taxonomy, doc.get("verifier_files"))
        versions = selection.selectable_configurations(c, ws, cr["configuration_id"])
        if versions and not verifier.is_blocks_config(versions[0]["config"]):
            reasons.append(
                f"{cr['configuration_id']} is not a verifier-blocks configuration (runner verifier_blocks)"
            )
        out.append(
            {
                "check": "verifier_blocks_valid",
                "criterion": cr["criterion_id"],
                "ok": not reasons,
                "blocks": len(blocks),
                "reason": "; ".join(reasons) or None,
                "reasons": reasons,
            }
        )
    return out


def _file_checks(doc):
    """`verifier_files` (A-03, item 21): each key is the SHA-256 of its file's RFC 8785 canonical JSON."""
    files = doc.get("verifier_files")
    if not files:
        return []
    from anvil.rlgym.plugins.contract import jcs_sha256

    bad = [k for k, v in files.items() if jcs_sha256(v) != k]
    return [
        {
            "check": "verifier_files_valid",
            "ok": not bad,
            "files": len(files),
            "reason": f"files whose content does not match their SHA-256: {', '.join(k[:12] for k in bad)}"
            if bad
            else None,
        }
    ]


def _edge_case_checks(doc):
    """S4 edge cases (2.12): each has a tag, a recipe, an expected outcome with a recommendation, a minimum, and slice
    tags from the template's S1 lists. The tags must be unique."""
    edges = doc.get("edge_cases")
    if not edges:
        return []
    lists = doc.get("slice_lists") or {}
    reasons, seen = [], set()
    for e in edges:
        tag = e.get("tag") or "?"
        if tag in seen:
            reasons.append(f"{tag}: duplicate edge-case tag")
        seen.add(tag)
        recipe = e.get("recipe")
        # Plain English, or Studio's structured conditions ([{collection, field, op, value | value_ref}, ...]).
        if not (recipe.strip() if isinstance(recipe, str) else recipe):
            reasons.append(f"{tag}: no generator recipe, so its data cannot be asked for")
        if not (e.get("expected_outcome") or {}).get("recommendation"):
            reasons.append(f"{tag}: expected outcome needs a recommendation")
        minimum = e.get("minimum")
        if not (isinstance(minimum, dict) and minimum) and not isinstance(minimum, int):
            reasons.append(f"{tag}: minimum cases (per product) is required")
        for key in ("complexity", "archetype"):
            allowed = lists.get(key)
            if e.get(key) and allowed and e[key] not in allowed:
                reasons.append(f"{tag}: {key} {e[key]!r} is not in the template's S1 list")
    return [
        {
            "check": "edge_cases_valid",
            "ok": not reasons,
            "edge_cases": len(edges),
            "reason": "; ".join(reasons) or None,
            "reasons": reasons,
        }
    ]


def _policy_binding_checks(doc):
    """E-002 (optional): the release's policy_bindings. Every check a clause names must be a criterion of this template
    and its blocks must be that criterion's verifier blocks, so a clause receipt's consumed_by is always real. No
    policy_bindings: no check, the template validates as before."""
    pb = doc.get("policy_bindings")
    if not pb:
        return []
    blocks = {
        cr["criterion_id"]: {b.get("id") for b in cr.get("verifier_blocks") or []}
        for cr in doc.get("criteria") or []
    }
    reasons = []
    if not pb.get("fact_catalog"):
        reasons.append("policy_bindings has no fact_catalog")
    for f in pb.get("facts") or []:
        if not (f.get("fact") and f.get("environment_fact")):
            reasons.append(f"fact binding {f!r} needs fact and environment_fact")
    entries = [
        (e.get("clause_id"), c)
        for e in pb.get("clauses") or []
        for c in ((e.get("needs") or {}).get("checks") or [])
    ] + [(o.get("clause_id"), o) for o in pb.get("obligation_checks") or []]
    for clause_id, chk in entries:
        cid = chk.get("criterion_id")
        if cid not in blocks:
            reasons.append(f"{clause_id}: criterion {cid} is not in this template")
            continue
        for b in chk.get("block_ids") or []:
            if b not in blocks[cid]:
                reasons.append(f"{clause_id}: block {b} is not a verifier block of {cid}")
    return [
        {
            "check": "policy_bindings_valid",
            "ok": not reasons,
            "clauses": len(pb.get("clauses") or []),
            "reason": "; ".join(reasons) or None,
            "reasons": reasons,
        }
    ]


def edge_minimum(edge):
    m = edge.get("minimum")
    return sum(int(v) for v in m.values()) if isinstance(m, dict) else int(m or 0)


def known_case_tests(c, ws, actor, body):
    """POST /templates/known-case-tests: the A-06 test of the current qualified configuration of every criterion."""
    template_id, version = body.get("template_id"), body.get("version")
    criteria = body.get("criteria")
    source = body.get("expected_values_from")
    if not criteria:
        criteria = c.execute(
            "SELECT criterion_id, configuration_id, verifier_blocks FROM catalog.template_criteria WHERE workspace_id=%s AND template_id=%s AND version=%s",
            (ws, template_id, version),
        ).fetchall()
        act = c.execute(
            "SELECT expected_values_from FROM catalog.template_activations WHERE workspace_id=%s AND template_id=%s AND version=%s",
            (ws, template_id, version),
        ).fetchone()
        source = source or (act and act["expected_values_from"])
    require(
        criteria, "VALIDATION_FAILED", "No criteria given and no activation found", field="criteria"
    )
    rows = []
    for cr in criteria:
        crit = cr.get("criterion_id") or cr.get("criterion")
        cfg = cr["configuration_id"]
        latest = c.execute(
            """SELECT version FROM catalog.evaluator_configurations WHERE workspace_id=%s AND id=%s AND state IN ('qualified','registered','failed')
               ORDER BY (state='qualified') DESC, version DESC LIMIT 1""",
            (ws, cfg),
        ).fetchone()
        if not latest:
            rows.append(
                {
                    "criterion": crit,
                    "configuration": cfg,
                    "version": None,
                    "result": "failed",
                    "receipt_id": None,
                    "reason": "no configuration",
                }
            )
            continue
        test = evaluators.run_known_case_tests(
            c,
            ws,
            actor,
            cfg,
            latest["version"],
            blocks=cr.get("verifier_blocks"),
            expected_values_from=source,
        )
        rows.append(
            {
                "criterion": crit,
                "configuration": cfg,
                "version": latest["version"],
                "result": test["result"],
                "receipt_id": test["receipt_id"],
            }
        )
    return {"passed": all(r["result"] == "qualified" for r in rows), "criteria": rows}


def forge_qualification(doc, record, checks):
    """The qualification record for ADI Forge. A template whose activation names ADI Forge's own published version
    (`forge_template_version_hash`, set by Studio's release) goes to ADI Forge's P-03 route in its exact shape — locally
    Studio's ADI Forge stub (RLGYM_FORGE_QUALIFICATION_URL, tenant RLGYM_FORGE_TENANT_ID). Other templates (the RL Gym's
    own stub releases) keep going to the RL Gym's ADI Forge stub as before."""
    import os

    url, tenant = (
        os.environ.get("RLGYM_FORGE_QUALIFICATION_URL"),
        os.environ.get("RLGYM_FORGE_TENANT_ID"),
    )
    if doc.get("channel") == "test":
        # The end-to-end test's activation: only test-only projects may export against it (Authoring must check).
        record = {**record, "channel": "test"}
    if not (doc.get("forge_template_version_hash") and url and tenant):
        return record
    return {
        **({"channel": "test"} if doc.get("channel") == "test" else {}),
        "_base": url,
        "_headers": {"X-Tenant-Id": tenant},
        "template_id": doc["forge_template_id"],
        "version": int(doc["forge_version"]),
        "template_version_hash": doc["forge_template_version_hash"],
        "status": "QUALIFIED",
        "receipt_id": record["receipt_id"],
        "receipt": {
            "rlgym_template_id": doc["template_id"],
            "rlgym_template_version": int(doc["version"]),
            "spec_sha256": doc["spec_sha256"],
            "checks": {k: v for k, v in checks.items() if k != "detail"},
            "event_sha256": record["event_sha256"],
        },
    }


SKILLS = ("tool_calling", "instruction_following", "reasoning", "decisioning", "safety")
HASH_EXCLUDED = (
    "forge_template_id",
    "forge_version",
    "forge_template_version_hash",
    "spec_sha256",
    "template_sha256",
    # How the template is activated (test channel), not what it is: the content hash is the same either way.
    "channel",
)


def content_sha256(doc):
    return sha({k: v for k, v in doc.items() if k not in HASH_EXCLUDED})


def activation_channel(doc):
    """None (a release) or "test" (the end-to-end test before a release: test-only projects only)."""
    ch = doc.get("channel")
    require(
        ch in (None, "test"),
        "VALIDATION_FAILED",
        "channel is test or absent",
        field="channel",
    )
    return ch


def check_existing(existing, doc, channel):
    """An activated version is final. A test-channel activation holds its version: a release of the same version is
    refused (release under a new version); a test activation of a released version is the release itself."""
    if existing.get("channel") == "test" and channel != "test":
        raise GymError(
            "CONFLICT",
            "This template version is activated on the test channel; release it under a new version",
        )
    require(
        existing["spec_sha256"] == doc["spec_sha256"],
        "CONFLICT",
        "A released template version is final; this version is active with another hash",
    )
    return True


def activate(c, ws, actor, doc):
    """POST /templates/activations: store the exact template hash and its rules; record qualification in ADI Forge."""
    _required(doc)
    channel = activation_channel(doc)
    for cr in doc.get("criteria") or []:
        require(
            cr.get("skill") in (None, *SKILLS),
            "VALIDATION_FAILED",
            f"Unknown skill {cr.get('skill')!r} on criterion {cr.get('criterion_id')}",
            field="skill",
        )
    expected = content_sha256(doc)
    require(
        doc["spec_sha256"] == expected,
        "HASH_MISMATCH",
        "spec_sha256 does not match the template content",
        expected=expected,
        got=doc["spec_sha256"],
    )
    existing = c.execute(
        "SELECT * FROM catalog.template_activations WHERE workspace_id=%s AND template_id=%s AND version=%s",
        (ws, doc["template_id"], int(doc["version"])),
    ).fetchone()
    if existing:
        check_existing(existing, doc, channel)
        return existing, False
    result = validate(c, ws, doc, allow_test=channel == "test")
    kct = known_case_tests(
        c,
        ws,
        actor,
        {
            "template_id": doc["template_id"],
            "version": doc["version"],
            "expected_values_from": doc.get("expected_values_from"),
            "criteria": [
                {
                    "criterion_id": cr["criterion_id"],
                    "configuration_id": cr["configuration_id"],
                    "verifier_blocks": cr.get("verifier_blocks"),
                }
                for cr in doc["criteria"]
            ],
        },
    )
    checks = {
        "fingerprints_match": True,
        "environments_can_bind": all(
            ch["ok"] for ch in result["checks"] if ch["check"] == "environment_can_bind"
        ),
        "criteria_can_bind": all(
            ch["ok"] for ch in result["checks"] if ch["check"] == "criterion_can_bind"
        ),
        "verifier_blocks_valid": all(
            ch["ok"] for ch in result["checks"] if ch["check"] == "verifier_blocks_valid"
        ),
        "verifier_files_valid": all(
            ch["ok"] for ch in result["checks"] if ch["check"] == "verifier_files_valid"
        ),
        "edge_cases_valid": all(
            ch["ok"] for ch in result["checks"] if ch["check"] == "edge_cases_valid"
        ),
        "known_case_tests_passed": kct["passed"],
        "known_case_tests": f"{sum(r['result'] == 'qualified' for r in kct['criteria'])} of {len(kct['criteria'])}",
        "detail": result["checks"],
    }
    state = "active" if result["valid"] and kct["passed"] else "blocked"
    row = c.execute(
        """INSERT INTO catalog.template_activations(workspace_id,template_id,version,template_key,name,mode,spec_sha256,template_sha256,
             forge_template_id,forge_version,studio_release,default_bindings,workflow,case_dimensions,pass_mark,checks,state,state_reason,
             activated_at,activated_by,forge_template_version_hash,expected_values_from,failure_taxonomy,edge_cases,slice_lists,verifier_files,
             policy_bindings,output_schema,channel)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            ws,
            doc["template_id"],
            int(doc["version"]),
            doc["key"],
            doc["name"],
            doc["mode"],
            doc["spec_sha256"],
            doc.get("template_sha256") or sha(doc),
            doc["forge_template_id"],
            int(doc["forge_version"]),
            doc.get("studio_release"),
            Jsonb(doc["bindings"]),
            Jsonb(doc["workflow"]),
            Jsonb(doc["case_dimensions"]),
            doc["pass_mark"],
            Jsonb(checks),
            state,
            None if state == "active" else "Activation checks failed",
            actor.id,
            doc.get("forge_template_version_hash"),
            doc.get("expected_values_from"),
            Jsonb(doc["failure_taxonomy"]) if doc.get("failure_taxonomy") else None,
            Jsonb(doc["edge_cases"]) if doc.get("edge_cases") else None,
            Jsonb(doc["slice_lists"]) if doc.get("slice_lists") else None,
            Jsonb(doc["verifier_files"]) if doc.get("verifier_files") else None,
            Jsonb(doc["policy_bindings"]) if doc.get("policy_bindings") else None,
            # KYC Judgment C4: the template's execution.output_schema, shown to the agent as "Output fields".
            Jsonb(doc["output_schema"]) if doc.get("output_schema") else None,
            channel,
        ),
    ).fetchone()
    for cr in doc["criteria"]:
        c.execute(
            """INSERT INTO catalog.template_criteria(workspace_id,template_id,version,criterion_id,capability,skill_group,weight,is_gate,
                 configuration_id,evidence_type,verdict_vocabulary,verifier_blocks,skill)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                ws,
                doc["template_id"],
                int(doc["version"]),
                cr["criterion_id"],
                cr["capability"],
                cr["skill_group"],
                cr["weight"],
                cr.get("is_gate", False),
                cr["configuration_id"],
                cr["evidence_type"],
                cr["verdict_vocabulary"],
                Jsonb(cr["verifier_blocks"]) if cr.get("verifier_blocks") else None,
                # E-011 / C4: the skill the criterion measures (template.v1's optional `skill`).
                cr.get("skill"),
            ),
        )
    audit(
        c,
        ws,
        actor,
        "template.activated",
        f"{doc['template_id']}@{doc['version']}",
        details={"state": state, "checks": checks},
    )
    emit(
        c,
        ws,
        "template.activated",
        f"{doc['template_id']}@{doc['version']}",
        {"template_id": doc["template_id"], "version": doc["version"], "state": state},
    )
    if state == "active":
        receipt_id = (
            "tq-"
            + sha({"t": doc["template_id"], "v": doc["version"], "h": doc["spec_sha256"]})[:12]
        )
        record = {
            "template_id": doc["template_id"],
            "version": int(doc["version"]),
            "template_version_hash": doc["spec_sha256"],
            "status": "QUALIFIED",
            "receipt_id": receipt_id,
        }
        record["event_sha256"] = sha(record)
        emit(
            c,
            ws,
            "forge.template_qualification",
            receipt_id,
            forge_qualification(doc, record, checks),
            destination="forge",
        )
    return row, True


def list_templates(c, ws, q=None, state=None):
    sql = """SELECT a.*, (SELECT count(*) FROM catalog.template_criteria t WHERE t.workspace_id=a.workspace_id
               AND t.template_id=a.template_id AND t.version=a.version) AS criteria_count
             FROM catalog.template_activations a WHERE a.workspace_id=%s"""
    params = [ws]
    if q:
        sql += " AND (a.name ILIKE %s OR a.template_id ILIKE %s OR a.template_key ILIKE %s)"
        params += [f"%{q}%"] * 3
    if state:
        sql += " AND a.state=%s"
        params.append(state)
    rows = c.execute(sql + " ORDER BY a.name, a.version DESC", params).fetchall()
    for row in rows:
        row["environments"] = []
        for b in row["default_bindings"]:
            pick, code, reason = selection.resolve_environment(
                c, {"contract_id": b["contract_id"], **b["rule"]}
            )
            row["environments"].append(
                {
                    "alias": b["alias"],
                    "rule": selection.rule_label(b["rule"]),
                    "binds_now": pick["id"] if pick else None,
                    "ok": pick is not None,
                    "reason": reason,
                }
            )
        row["used_by"] = c.execute(
            "SELECT project_id, name, state FROM projects.projects WHERE workspace_id=%s AND template_id=%s AND template_version=%s",
            (ws, row["template_id"], row["version"]),
        ).fetchall()
    return rows


def get_template(c, ws, template_id, version):
    rows = [
        r
        for r in list_templates(c, ws)
        if r["template_id"] == template_id and r["version"] == int(version)
    ]
    if not rows:
        raise GymError("NOT_FOUND", "Template version not activated in this workspace")
    row = rows[0]
    criteria = c.execute(
        "SELECT * FROM catalog.template_criteria WHERE workspace_id=%s AND template_id=%s AND version=%s ORDER BY criterion_id",
        (ws, template_id, int(version)),
    ).fetchall()
    for cr in criteria:
        pick, code, reason = selection.resolve_evaluator(
            c, ws, {"configuration_id": cr["configuration_id"], "kind": "latest_qualified"}
        )
        cr["binds_now"] = f"{cr['configuration_id']} v{pick['version']}" if pick else None
        cr["known_case_ok"] = bool(pick and pick["known_case_receipt_id"])
        cr["rule"] = "Latest qualified"
    from anvil.rlgym.catalog import inbox

    return {
        **row,
        "criteria": criteria,
        "inbox_items": inbox.list_items(c, ws, template_id=template_id),
    }
