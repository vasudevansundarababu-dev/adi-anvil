"""Verifier plug-in versions (shared/VERIFIER-PLUGINS.md section 2; D22): install, known-case qualification, list,
and the events Studio reads. Deprecate and revoke reuse the framework lifecycle (impact report first).

A plug-in version is a row in `catalog.framework_versions` with its manifest. It is qualified only when every known
case in its manifest gives its expected verdict through the generic runner. Studio is told with `framework.qualified`
(carrying `settings_schema`), and `GET /evaluators/plugins` lists qualified versions only.
"""

from psycopg.types.json import Jsonb

from anvil.rlgym.common import GymError, audit, require
from anvil.rlgym.plugins import contract, runner
from anvil.rlgym.runs import images


def row_id(manifest):
    return f"plugin-{manifest['id']}-{manifest['version']}"


def image_present(image):
    ref = image if image.startswith("sha256:") else image
    try:
        proc = images._run(["image", "inspect", "--format", "{{.Id}}", ref], timeout=15)
    except Exception:
        return False
    if proc.returncode != 0:
        return False
    return (not image.startswith("sha256:")) or proc.stdout.decode().strip() == image


def run_known_cases(manifest, invoke=None):
    checks = []
    for case in manifest["known_cases"]:
        out = runner.run(manifest, case["job"], invoke=invoke)
        verdicts = {r["verdict"] for r in out["results"]}
        ok = verdicts == {case["expect"]}
        if ok and case["expect"] == "fail" and case.get("expect_on_fail"):
            ok = case["expect_on_fail"] in {
                r.get("on_fail") for r in out["results"] if r["verdict"] == "fail"
            }
        checks.append(
            {
                "name": case.get("name"),
                "expected": case["expect"],
                "verdicts": sorted(verdicts),
                "result": "pass" if ok else "fail",
                "lines": out["results"],
            }
        )
    return checks


def _event(ctx, row, kind, extra=None):
    from anvil.rlgym.catalog.evaluators import _to_studio

    m = row["manifest"]
    _to_studio(
        ctx.c,
        ctx.ws,
        row["id"],
        f"framework.{kind}",
        {
            "id": m["id"],
            "version": m["version"],
            "name": m.get("name"),
            "settings_schema": m["settings_schema"],
            "reads": m["reads"],
            "calls_model": m["calls_model"],
            "image": m["image"],
            "upstream": m.get("upstream"),
            **(extra or {}),
        },
    )


def _qualify(ctx, row, invoke=None):
    checks = run_known_cases(row["manifest"], invoke=invoke)
    passed = all(c["result"] == "pass" for c in checks)
    state = "qualified" if passed else "failed"
    row = ctx.c.execute(
        """UPDATE catalog.framework_versions SET state=%s, state_reason=%s, known_case_results=%s,
             state_changed_by=%s, state_changed_at=now() WHERE id=%s RETURNING *""",
        (
            state,
            None if passed else "known-case tests failed",
            Jsonb([{k: c[k] for k in ("name", "expected", "verdicts", "result")} for c in checks]),
            ctx.actor.id,
            row["id"],
        ),
    ).fetchone()
    audit(ctx.c, ctx.ws, ctx.actor, "plugin.known_case_tests", row["id"], details={"state": state})
    if passed:
        _event(ctx, row, "qualified")
    else:
        _event(
            ctx,
            row,
            "failed",
            {"checks": [{k: c[k] for k in ("name", "expected", "verdicts")} for c in checks]},
        )
    return {**public(row), "checks": checks}


def install(ctx, manifest, invoke=None):
    """Admin → Evaluators → Install plug-in version: the manifest, its pinned image present locally, then the known
    cases. The same manifest again returns the installed version; a different one under the same id and version is
    refused (a version never changes)."""
    ctx.actor.require_person()
    require(ctx.actor.profile == "admin", "FORBIDDEN", "Only an Admin installs a plug-in version")
    contract.check_manifest(manifest)
    require(
        not manifest["calls_model"],
        "VALIDATION_FAILED",
        "Plug-ins that call a model need the gateway network, which is not built yet",
    )
    require(
        invoke is not None or image_present(manifest["image"]),
        "VALIDATION_FAILED",
        "The plug-in image is not in local Docker (nothing is pulled)",
        image=manifest["image"],
    )
    digest = contract.jcs_sha256(manifest)
    existing = ctx.c.execute(
        "SELECT * FROM catalog.framework_versions WHERE runtime_id=%s AND version=%s",
        (manifest["id"], manifest["version"]),
    ).fetchone()
    if existing:
        require(
            existing["manifest_sha256"] == digest,
            "CONFLICT",
            "This plug-in version is installed with another manifest; a fix is a new version",
        )
        return {**public(existing), "created": False}
    row = ctx.c.execute(
        """INSERT INTO catalog.framework_versions(id,runtime_id,version,image_digest,evidence_types,installed_locally,
             install_note,state,created_by,manifest,manifest_sha256,settings_schema,reads,calls_model)
           VALUES(%s,%s,%s,%s,%s,true,%s,'registered',%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            row_id(manifest),
            manifest["id"],
            manifest["version"],
            manifest["image"],
            ["plugin"],
            f"{manifest.get('name')} · upstream {manifest.get('upstream')}",
            ctx.actor.id,
            Jsonb(manifest),
            digest,
            Jsonb(manifest["settings_schema"]),
            manifest["reads"],
            manifest["calls_model"],
        ),
    ).fetchone()
    audit(
        ctx.c, ctx.ws, ctx.actor, "plugin.installed", row["id"], details={"manifest_sha256": digest}
    )
    return {**_qualify(ctx, row, invoke=invoke), "created": True}


def test(ctx, plugin_id, version, invoke=None):
    ctx.actor.require_person()
    row = get_row(ctx.c, plugin_id, version)
    require(
        row["state"] != "revoked",
        "VALIDATION_FAILED",
        "A revoked plug-in version is not tested again",
    )
    return _qualify(ctx, row, invoke=invoke)


def get_row(c, plugin_id, version):
    row = c.execute(
        "SELECT * FROM catalog.framework_versions WHERE runtime_id=%s AND version=%s AND manifest IS NOT NULL",
        (plugin_id, version),
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", f"Plug-in {plugin_id} {version} is not installed")
    return row


def judge_choices(c, ws):
    """mock-judge plus every model the owner approved for use `judge` in this workspace (active approvals)."""
    if c is None or ws is None:
        return ["mock-judge"]
    rows = c.execute(
        """SELECT DISTINCT model_id FROM systems.live_approvals WHERE workspace_id=%s AND 'judge' = ANY(uses)
             AND revoked_at IS NULL AND expires_at > now() ORDER BY model_id""",
        (ws,),
    ).fetchall()
    return ["mock-judge", *[r["model_id"] for r in rows]]


def schema_for(schema, c=None, ws=None):
    """The settings schema as Studio and validation see it: `x-enum-from: judge-approvals` becomes an enum."""
    import copy

    out = copy.deepcopy(schema or {})
    for prop in (out.get("properties") or {}).values():
        if isinstance(prop, dict) and prop.get("x-enum-from") == "judge-approvals":
            prop["enum"] = judge_choices(c, ws)
    return out


def public(row, c=None, ws=None):
    m = row["manifest"] or {}
    return {
        "id": row["runtime_id"],
        "version": row["version"],
        "name": m.get("name"),
        "settings_schema": schema_for(row["settings_schema"], c, ws),
        "reads": row["reads"],
        "calls_model": row["calls_model"],
        "state": row["state"],
        "image": row["image_digest"],
        "upstream": m.get("upstream"),
        "license": m.get("license"),
        "framework_version_id": row["id"],
        "known_case_results": row["known_case_results"],
    }


def list_plugins(c, qualified_only=True, ws=None):
    sql = "SELECT * FROM catalog.framework_versions WHERE manifest IS NOT NULL"
    if qualified_only:
        sql += " AND state='qualified'"
    return [
        public(r, c, ws)
        for r in c.execute(sql + " ORDER BY runtime_id, created_at DESC").fetchall()
    ]


def resolve(c, plugin):
    """The plug-in version a block binds now: `latest_qualified` (default) or `pinned` (`version`)."""
    rule = plugin.get("version_rule") or "latest_qualified"
    if rule == "pinned":
        row = c.execute(
            "SELECT * FROM catalog.framework_versions WHERE runtime_id=%s AND version=%s AND manifest IS NOT NULL",
            (plugin["id"], plugin.get("version")),
        ).fetchone()
        return row if row and row["state"] in ("qualified", "deprecated") else None
    rows = c.execute(
        """SELECT * FROM catalog.framework_versions WHERE runtime_id=%s AND manifest IS NOT NULL AND state='qualified'""",
        (plugin["id"],),
    ).fetchall()
    if not rows:
        return None
    return max(rows, key=lambda r: tuple(int(x) for x in r["version"].split(".")))
