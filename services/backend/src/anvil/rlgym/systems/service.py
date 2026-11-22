"""Systems under test (SPEC 07.3, SCREENS 3.40-3.44): keys, immutable model versions, probes, model sets.

Models never hold keys: a version names the key it uses; the secret lives in the existing encrypted local store
(workspace_secrets) and the database keeps only its reference and last four characters. Rotating a key changes no
model version. Locally only the controlled mock provider is called; any other provider is recorded and probed as
`live_disabled` until the owner approves an exact provider, model and budget.
"""

import datetime as dt
import os
import re

from psycopg.types.json import Jsonb

from anvil import workspace_secrets
from anvil.rlgym.common import GymError, audit, emit, new_id, require, sha
from anvil.rlgym.systems import mock_provider

PROVIDERS = {"huggingface", "openai", "google", "anthropic", "mistral", "vertex", "mock"}
FRONTIER = {"openai", "google", "anthropic", "mistral", "vertex"}
HEX40 = re.compile(r"^[0-9a-f]{40}$")
SLUG = re.compile(r"[^a-z0-9.-]+")


def live_enabled():
    return os.environ.get("ANVIL_LIVE_PROVIDERS_ENABLED", "false") == "true"


def _admin(ctx):
    ctx.actor.require_person()
    require(ctx.actor.profile == "admin", "FORBIDDEN", "Keys are managed by an Admin")


# --- keys ------------------------------------------------------------------------------------------------------


def _public_key(row, used_by=0):
    return {
        k: row[k]
        for k in (
            "id",
            "provider",
            "name",
            "kind",
            "scope",
            "is_default",
            "last4",
            "status",
            "status_note",
            "last_tested_at",
            "rotated_at",
            "rotated_by",
            "created_at",
        )
    } | {"used_by": used_by}


def list_keys(ctx, provider=None):
    sql, params = "SELECT * FROM systems.provider_keys WHERE workspace_id=%s", [ctx.ws]
    if provider:
        sql += " AND provider=%s"
        params.append(provider)
    out = []
    for row in ctx.c.execute(sql + " ORDER BY provider, is_default DESC, name", params).fetchall():
        used = ctx.c.execute(
            """SELECT count(DISTINCT v.system_id) n FROM systems.system_versions v
               WHERE v.workspace_id=%s AND v.key_id=%s AND v.version=(SELECT max(version) FROM systems.system_versions x
                 WHERE x.workspace_id=v.workspace_id AND x.system_id=v.system_id)""",
            (ctx.ws, row["id"]),
        ).fetchone()["n"]
        out.append(_public_key(row, used))
    return out


def _store_secret(ctx, key_id, secret):
    try:
        return "local-store:" + workspace_secrets.save(secret, f"rlgym:{ctx.ws}:{key_id}")
    except workspace_secrets.StoreUnavailable as exc:
        raise GymError("VALIDATION_FAILED", str(exc)) from None


def add_key(ctx, body):
    _admin(ctx)
    provider = body.get("provider")
    require(provider in PROVIDERS, "VALIDATION_FAILED", "Unknown provider", field="provider")
    name = (body.get("name") or "").strip()
    require(name, "VALIDATION_FAILED", "A name is required", field="name")
    scope = body.get("scope", "workspace_default")
    require(
        scope in ("workspace_default", "customer", "assist"),
        "VALIDATION_FAILED",
        "Unknown scope",
        field="scope",
    )
    kind = {"huggingface": "hf_token", "vertex": "service_account", "mock": "none"}.get(
        provider, "api_key"
    )
    key_id = (
        "key-" + SLUG.sub("-", f"{provider}-{name.lower()}").strip("-")[:40] + "-" + new_id()[:4]
    )
    if provider == "mock":
        secret_ref, last4, status = "mock:none", "mock", "valid"
    else:
        secret = body.get("secret") or ""
        require(
            isinstance(secret, str) and len(secret) >= 8,
            "VALIDATION_FAILED",
            "Key or token required (at least 8 characters)",
            field="secret",
        )
        secret_ref, last4, status = _store_secret(ctx, key_id, secret), secret[-4:], "untested"
    is_default = bool(body.get("is_default", scope == "workspace_default"))
    if is_default:
        ctx.c.execute(
            "UPDATE systems.provider_keys SET is_default=false WHERE workspace_id=%s AND provider=%s",
            (ctx.ws, provider),
        )
    row = ctx.c.execute(
        """INSERT INTO systems.provider_keys(id,workspace_id,provider,name,kind,scope,is_default,secret_ref,last4,status,rotated_by)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            key_id,
            ctx.ws,
            provider,
            name,
            kind,
            scope,
            is_default,
            secret_ref,
            last4,
            status,
            ctx.actor.id,
        ),
    ).fetchone()
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "key.added",
        key_id,
        details={"provider": provider, "scope": scope},
    )
    emit(ctx.c, ctx.ws, "key.added", key_id, {"key_id": key_id, "provider": provider})
    return _public_key(row)


def _key(ctx, key_id):
    row = ctx.c.execute(
        "SELECT * FROM systems.provider_keys WHERE workspace_id=%s AND id=%s", (ctx.ws, key_id)
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "Key not found")
    return row


def rotate_key(ctx, key_id, body):
    _admin(ctx)
    row = _key(ctx, key_id)
    require(
        row["provider"] != "mock",
        "VALIDATION_FAILED",
        "The controlled mock has no secret to rotate",
    )
    require(
        row["kind"] != "service_account",
        "VALIDATION_FAILED",
        "Service accounts are rotated in the cloud console",
    )
    require(row["status"] != "revoked", "VALIDATION_FAILED", "A revoked key cannot be rotated")
    secret = body.get("secret") or ""
    require(
        isinstance(secret, str) and len(secret) >= 8,
        "VALIDATION_FAILED",
        "Key or token required",
        field="secret",
    )
    ref = _store_secret(ctx, key_id, secret)
    ctx.c.execute(
        """UPDATE systems.provider_keys SET secret_ref=%s, last4=%s, status='untested', status_note=NULL, rotated_at=now(),
                     rotated_by=%s WHERE workspace_id=%s AND id=%s""",
        (ref, secret[-4:], ctx.actor.id, ctx.ws, key_id),
    )
    audit(ctx.c, ctx.ws, ctx.actor, "key.rotated", key_id)
    emit(ctx.c, ctx.ws, "key.rotated", key_id, {"key_id": key_id})
    return _public_key(_key(ctx, key_id))


def test_key(ctx, key_id):
    _admin(ctx)
    row = _key(ctx, key_id)
    if row["provider"] == "mock":
        status, note = "valid", "Controlled mock: no secret, no network"
    elif not live_enabled():
        status, note = (
            "untested",
            "Not tested: live provider calls are disabled locally; the key was not sent anywhere",
        )
    else:
        raise GymError(
            "ADMISSION_REFUSED",
            "Live key tests need the owner's approved provider, model and budget",
        )
    ctx.c.execute(
        "UPDATE systems.provider_keys SET status=%s, status_note=%s, last_tested_at=now() WHERE workspace_id=%s AND id=%s",
        (status, note, ctx.ws, key_id),
    )
    audit(ctx.c, ctx.ws, ctx.actor, "key.tested", key_id, details={"status": status})
    return _public_key(_key(ctx, key_id))


def revoke_key(ctx, key_id, body):
    _admin(ctx)
    require(
        (body.get("reason") or "").strip(),
        "VALIDATION_FAILED",
        "A reason is required",
        field="reason",
    )
    _key(ctx, key_id)
    using = [
        r["system_id"]
        for r in ctx.c.execute(
            """SELECT v.system_id FROM systems.system_versions v JOIN systems.systems s USING (workspace_id, system_id)
           WHERE v.workspace_id=%s AND v.key_id=%s AND s.enabled AND v.version=(SELECT max(version) FROM systems.system_versions x
             WHERE x.workspace_id=v.workspace_id AND x.system_id=v.system_id)""",
            (ctx.ws, key_id),
        ).fetchall()
    ]
    require(
        not using,
        "VALIDATION_FAILED",
        "Enabled models still use this key; give them another key first",
        models=using,
    )
    ctx.c.execute(
        "UPDATE systems.provider_keys SET status='revoked', is_default=false, status_note=%s WHERE workspace_id=%s AND id=%s",
        (body["reason"], ctx.ws, key_id),
    )
    audit(ctx.c, ctx.ws, ctx.actor, "key.revoked", key_id, body["reason"])
    return _public_key(_key(ctx, key_id))


# --- systems ---------------------------------------------------------------------------------------------------


def _num(params, name, minimum, required=False, exclusive=False):
    value = params.get(name)
    if value is None:
        require(not required, "VALIDATION_FAILED", f"{name} is required", field=name)
        return
    require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (value > minimum if exclusive else value >= minimum),
        "VALIDATION_FAILED",
        f"{name} must be a number {'>' if exclusive else '≥'} {minimum}",
        field=name,
    )


def _validate(ctx, body):
    kind = body.get("kind")
    require(
        kind in ("open_weight", "frontier", "fine_tuned"),
        "VALIDATION_FAILED",
        "Unknown type",
        field="kind",
    )
    require(
        kind != "fine_tuned",
        "VALIDATION_FAILED",
        "ADI fine-tuned models are coming later",
        field="kind",
    )
    provider = body.get("provider") or ("huggingface" if kind == "open_weight" else None)
    if kind == "open_weight":
        require(
            provider in ("huggingface", "mock"),
            "VALIDATION_FAILED",
            "Open-weight models come from Hugging Face",
            field="provider",
        )
        if provider == "huggingface":
            require(
                HEX40.match(body.get("hf_revision") or ""),
                "VALIDATION_FAILED",
                "Pin the Hugging Face revision to a 40-character commit hash",
                field="hf_revision",
            )
    else:
        require(
            provider in FRONTIER | {"mock"},
            "VALIDATION_FAILED",
            "Unknown frontier provider",
            field="provider",
        )
    model_id = (body.get("model_id") or "").strip()
    require(model_id, "VALIDATION_FAILED", "Model ID or repository is required", field="model_id")
    if provider == "mock":
        require(
            model_id in mock_provider.PROFILES,
            "VALIDATION_FAILED",
            "Unknown controlled-mock profile",
            field="model_id",
            profiles=list(mock_provider.PROFILES),
        )
    params = body.get("params") or {}
    limits = body.get("limits") or {}
    require(
        isinstance(params, dict) and isinstance(limits, dict),
        "VALIDATION_FAILED",
        "params and limits are objects",
    )
    _num(params, "temperature", 0)
    _num(params, "max_output_tokens", 1)
    _num(params, "timeout_s", 1)
    _num(limits, "rpm", 0, required=True, exclusive=True)
    _num(limits, "spend_per_episode_usd", 0, required=True, exclusive=True)
    key_id = body.get("key_id")
    if key_id:
        key = _key(ctx, key_id)
        require(
            key["provider"] == provider,
            "VALIDATION_FAILED",
            "The key belongs to another provider",
            field="key_id",
        )
    else:
        key = ctx.c.execute(
            "SELECT * FROM systems.provider_keys WHERE workspace_id=%s AND provider=%s AND is_default AND status<>'revoked'",
            (ctx.ws, provider),
        ).fetchone()
        if not key:
            raise GymError(
                "KEY_MISSING",
                f"No {provider} key in this workspace yet: add it in Keys first",
                {"provider": provider},
            )
    require(key["status"] != "revoked", "VALIDATION_FAILED", "The key is revoked", field="key_id")
    config = {
        "kind": kind,
        "provider": provider,
        "model_id": model_id,
        "hf_revision": body.get("hf_revision"),
        "serving": body.get("serving")
        or ({"mode": "controlled_mock"} if provider == "mock" else {"mode": "provider_api"}),
        "params": params,
        "limits": limits,
        "key_id": key["id"],
    }
    return config


def _status(ctx, system, version):
    if not system["enabled"]:
        return "Disabled"
    if system["setup_state"] == "pending":
        return "Setup pending"
    probe = ctx.c.execute(
        "SELECT * FROM systems.system_probes WHERE workspace_id=%s AND system_id=%s AND system_version=%s ORDER BY probed_at DESC LIMIT 1",
        (ctx.ws, system["system_id"], version),
    ).fetchone()
    if not probe:
        return "Not tested in 24 h"
    if probe["result"] == "live_disabled":
        return "Live calls disabled"
    if probe["result"] != "ok":
        return "Unreachable"
    if probe["probed_at"] < dt.datetime.now(dt.UTC) - dt.timedelta(hours=24):
        return "Not tested in 24 h"
    return "Ready"


def _insert_version(ctx, system_id, config, note):
    h = sha(config)
    same = ctx.c.execute(
        "SELECT * FROM systems.system_versions WHERE workspace_id=%s AND system_id=%s AND config_sha256=%s",
        (ctx.ws, system_id, h),
    ).fetchone()
    if same:
        return same, False
    latest = ctx.c.execute(
        "SELECT coalesce(max(version),0) v FROM systems.system_versions WHERE workspace_id=%s AND system_id=%s",
        (ctx.ws, system_id),
    ).fetchone()["v"]
    row = ctx.c.execute(
        """INSERT INTO systems.system_versions(workspace_id,system_id,version,kind,provider,model_id,hf_revision,key_id,serving,params,limits,
             config_sha256,created_by,change_note) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            ctx.ws,
            system_id,
            latest + 1,
            config["kind"],
            config["provider"],
            config["model_id"],
            config["hf_revision"],
            config["key_id"],
            Jsonb(config["serving"]),
            Jsonb(config["params"]),
            Jsonb(config["limits"]),
            h,
            ctx.actor.id,
            note or ("first version" if latest == 0 else None),
        ),
    ).fetchone()
    return row, True


def create_system(ctx, body):
    ctx.actor.require_person()
    config = _validate(ctx, body)
    name = (body.get("name") or config["model_id"]).strip()
    system_id = body.get("system_id") or SLUG.sub("-", name.lower()).strip("-")[:50]
    require(
        not ctx.c.execute(
            "SELECT 1 FROM systems.systems WHERE workspace_id=%s AND system_id=%s",
            (ctx.ws, system_id),
        ).fetchone(),
        "CONFLICT",
        f"Model {system_id} exists; edit it as a new version",
    )
    ctx.c.execute(
        "INSERT INTO systems.systems(workspace_id,system_id,name,kind,setup_state,synthetic) VALUES(%s,%s,%s,%s,'ready',%s)",
        (ctx.ws, system_id, name, config["kind"], config["provider"] == "mock"),
    )
    row, _ = _insert_version(ctx, system_id, config, body.get("change_note"))
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "system.created",
        f"{system_id}@{row['version']}",
        details={"config_sha256": row["config_sha256"]},
    )
    emit(
        ctx.c,
        ctx.ws,
        "system.version_created",
        f"{system_id}@{row['version']}",
        {"system_id": system_id, "version": row["version"]},
    )
    probe = probe_system(ctx, system_id, row["version"]) if body.get("test", True) else None
    return {"system": get_system(ctx, system_id), "probe": probe}


def new_version(ctx, system_id, body):
    ctx.actor.require_person()
    system = _system(ctx, system_id)
    require(
        body.get("kind", system["kind"]) == system["kind"],
        "VALIDATION_FAILED",
        "A model keeps its type",
    )
    config = _validate(ctx, {**body, "kind": system["kind"]})
    note = (body.get("change_note") or "").strip()
    row, created = _insert_version(ctx, system_id, config, note or "settings changed")
    if created:
        audit(
            ctx.c,
            ctx.ws,
            ctx.actor,
            "system.version_created",
            f"{system_id}@{row['version']}",
            note,
        )
        emit(
            ctx.c,
            ctx.ws,
            "system.version_created",
            f"{system_id}@{row['version']}",
            {"system_id": system_id, "version": row["version"]},
        )
    probe = (
        probe_system(ctx, system_id, row["version"]) if created and body.get("test", True) else None
    )
    return {
        "system": get_system(ctx, system_id),
        "created": created,
        "version": row["version"],
        "probe": probe,
    }


def _system(ctx, system_id):
    row = ctx.c.execute(
        "SELECT * FROM systems.systems WHERE workspace_id=%s AND system_id=%s", (ctx.ws, system_id)
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "Model not found")
    return row


def probe_system(ctx, system_id, version):
    """Connection test: a no-op echo episode. Only the controlled mock is ever called locally."""
    v = ctx.c.execute(
        "SELECT * FROM systems.system_versions WHERE workspace_id=%s AND system_id=%s AND version=%s",
        (ctx.ws, system_id, int(version)),
    ).fetchone()
    if not v:
        raise GymError("NOT_FOUND", "Model version not found")
    if v["provider"] == "mock":
        out, latency = mock_provider.respond(
            v["model_id"], {"probe": "echo", "system": system_id, "version": int(version)}
        )
        result, mode, details = "ok", "controlled_mock", {"echo_digest": out["digest"]}
    else:
        result, mode, latency = "live_disabled", "none", None
        details = {
            "note": "No request sent: live provider calls need the owner's approved provider, model, budget and local key"
        }
    row = ctx.c.execute(
        """INSERT INTO systems.system_probes(workspace_id,system_id,system_version,result,latency_ms,cost_usd,details,mode,probed_by)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            ctx.ws,
            system_id,
            int(version),
            result,
            latency,
            0 if v["provider"] == "mock" else None,
            Jsonb(details),
            mode,
            ctx.actor.id,
        ),
    ).fetchone()
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "system.probed",
        f"{system_id}@{version}",
        details={"result": result, "mode": mode},
    )
    return row


def set_enabled(ctx, system_id, enabled, reason=None):
    ctx.actor.require_person()
    _system(ctx, system_id)
    if not enabled:
        require(
            (reason or "").strip(),
            "VALIDATION_FAILED",
            "A reason is required to disable",
            field="reason",
        )
    ctx.c.execute(
        "UPDATE systems.systems SET enabled=%s, disabled_reason=%s WHERE workspace_id=%s AND system_id=%s",
        (enabled, None if enabled else reason, ctx.ws, system_id),
    )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "system.enabled" if enabled else "system.disabled",
        system_id,
        reason,
    )
    return get_system(ctx, system_id)


def get_system(ctx, system_id):
    system = _system(ctx, system_id)
    versions = ctx.c.execute(
        "SELECT * FROM systems.system_versions WHERE workspace_id=%s AND system_id=%s ORDER BY version DESC",
        (ctx.ws, system_id),
    ).fetchall()
    latest = versions[0]
    key = _key(ctx, latest["key_id"])
    probes = ctx.c.execute(
        "SELECT * FROM systems.system_probes WHERE workspace_id=%s AND system_id=%s ORDER BY probed_at DESC LIMIT 20",
        (ctx.ws, system_id),
    ).fetchall()
    return {
        **system,
        "latest": latest,
        "versions": versions,
        "status": _status(ctx, system, latest["version"]),
        "key": _public_key(key),
        "probes": probes,
        "runs": [],
        "runs_note": "Not used in a run yet (runs arrive with 2.7).",
    }


def list_systems(ctx, q=None, kind=None, status=None):
    rows = ctx.c.execute(
        "SELECT system_id FROM systems.systems WHERE workspace_id=%s ORDER BY name", (ctx.ws,)
    ).fetchall()
    out = []
    for r in rows:
        s = get_system(ctx, r["system_id"])
        if kind and s["kind"] != kind:
            continue
        if q and q.lower() not in (s["name"] + s["system_id"] + s["latest"]["model_id"]).lower():
            continue
        if status and s["status"] != status:
            continue
        s.pop("probes")
        s["versions"] = [
            {k: v[k] for k in ("version", "config_sha256", "created_at", "change_note")}
            for v in s["versions"]
        ]
        out.append(s)
    return out


def hf_latest(ctx, repo):
    if os.environ.get("RLGYM_HF_LOOKUP", "off") != "on":
        raise GymError(
            "VALIDATION_FAILED",
            "Hugging Face lookup is off locally (RLGYM_HF_LOOKUP); paste the 40-character commit hash",
            {"repo": repo},
        )
    raise GymError(
        "VALIDATION_FAILED", "Hugging Face lookup is not implemented in this local build"
    )


# --- model sets ------------------------------------------------------------------------------------------------


def list_model_sets(ctx):
    sets = ctx.c.execute(
        """SELECT DISTINCT ON (id) * FROM systems.model_sets WHERE workspace_id=%s ORDER BY id, version DESC""",
        (ctx.ws,),
    ).fetchall()
    for s in sets:
        s["members"] = _members(ctx, s["id"], s["version"])
        s["history"] = ctx.c.execute(
            "SELECT version, created_by, created_at, change_note FROM systems.model_sets WHERE workspace_id=%s AND id=%s ORDER BY version DESC",
            (ctx.ws, s["id"]),
        ).fetchall()
        s["used_in_runs"] = []
    return sets


def _members(ctx, set_id, version):
    return ctx.c.execute(
        """SELECT m.system_id, m.system_version, s.name FROM systems.model_set_members m JOIN systems.systems s USING (workspace_id, system_id)
           WHERE m.workspace_id=%s AND m.model_set_id=%s AND m.model_set_version=%s ORDER BY s.name""",
        (ctx.ws, set_id, version),
    ).fetchall()


def save_model_set(ctx, body):
    ctx.actor.require_person()
    name = (body.get("name") or "").strip()
    require(name, "VALIDATION_FAILED", "A name is required", field="name")
    members = body.get("members") or []
    require(
        isinstance(members, list) and members,
        "VALIDATION_FAILED",
        "Choose at least one model version",
        field="members",
    )
    pinned = sorted({(m["system_id"], int(m["system_version"])) for m in members})
    require(
        len({s for s, _ in pinned}) == len(pinned),
        "VALIDATION_FAILED",
        "One version per model",
        field="members",
    )
    for system_id, version in pinned:
        system = _system(ctx, system_id)
        require(system["enabled"], "VALIDATION_FAILED", f"{system_id} is disabled", field="members")
        require(
            ctx.c.execute(
                "SELECT 1 FROM systems.system_versions WHERE workspace_id=%s AND system_id=%s AND version=%s",
                (ctx.ws, system_id, version),
            ).fetchone(),
            "VALIDATION_FAILED",
            f"{system_id} v{version} does not exist",
        )
    set_id = body.get("id") or SLUG.sub("-", name.lower()).strip("-")[:50]
    h = sha({"name": name, "members": pinned})
    latest = ctx.c.execute(
        "SELECT * FROM systems.model_sets WHERE workspace_id=%s AND id=%s ORDER BY version DESC LIMIT 1",
        (ctx.ws, set_id),
    ).fetchone()
    if latest and latest["members_sha256"] == h:
        return {"id": set_id, "version": latest["version"], "created": False}
    version = (latest["version"] + 1) if latest else 1
    ctx.c.execute(
        "INSERT INTO systems.model_sets(workspace_id,id,version,name,created_by,change_note,members_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (ctx.ws, set_id, version, name, ctx.actor.id, body.get("change_note"), h),
    )
    for system_id, v in pinned:
        ctx.c.execute(
            "INSERT INTO systems.model_set_members(workspace_id,model_set_id,model_set_version,system_id,system_version) VALUES(%s,%s,%s,%s,%s)",
            (ctx.ws, set_id, version, system_id, v),
        )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "model_set.saved",
        f"{set_id}@{version}",
        details={"members": pinned},
    )
    emit(
        ctx.c, ctx.ws, "model_set.saved", f"{set_id}@{version}", {"id": set_id, "version": version}
    )
    return {"id": set_id, "version": version, "created": True}


# --- local seed ------------------------------------------------------------------------------------------------

MOCK_LINEUP = [
    ("mock-diligent", "Mock agent · diligent (synthetic)", "mock/diligent-v1"),
    ("mock-skips-screening", "Mock agent · skips screening (synthetic)", "mock/skips-screening-v1"),
    ("mock-erratic", "Mock agent · erratic (synthetic)", "mock/erratic-v1"),
]


def seed_mock_lineup(ctx):
    """Synthetic, clearly labelled controlled-mock models and a line-up, recorded as created by the local seed (a system
    actor, not a person). Idempotent."""
    if not ctx.c.execute(
        "SELECT 1 FROM systems.provider_keys WHERE workspace_id=%s AND provider='mock'", (ctx.ws,)
    ).fetchone():
        ctx.c.execute(
            """INSERT INTO systems.provider_keys(id,workspace_id,provider,name,kind,scope,is_default,secret_ref,last4,status,status_note,rotated_by)
               VALUES('key-mock-default',%s,'mock','Controlled mock (local, no secret)','none','workspace_default',true,'mock:none','mock','valid',
               'No secret and no network: deterministic synthetic responses','local-seed')""",
            (ctx.ws,),
        )
    members = []
    for system_id, name, model_id in MOCK_LINEUP:
        if not ctx.c.execute(
            "SELECT 1 FROM systems.systems WHERE workspace_id=%s AND system_id=%s",
            (ctx.ws, system_id),
        ).fetchone():
            ctx.c.execute(
                "INSERT INTO systems.systems(workspace_id,system_id,name,kind,setup_state,synthetic) VALUES(%s,%s,%s,'frontier','ready',true)",
                (ctx.ws, system_id, name),
            )
        config = {
            "kind": "frontier",
            "provider": "mock",
            "model_id": model_id,
            "hf_revision": None,
            "serving": {"mode": "controlled_mock"},
            "params": {"temperature": 0, "max_output_tokens": 4096, "timeout_s": 120},
            "limits": {"rpm": 600, "spend_per_episode_usd": 0.01},
            "key_id": "key-mock-default",
        }
        row, _ = _insert_version(ctx, system_id, config, "local seed: controlled mock profile")
        members.append({"system_id": system_id, "system_version": row["version"]})
    h = sha(
        {
            "name": "KYC line-up (mock)",
            "members": sorted((m["system_id"], m["system_version"]) for m in members),
        }
    )
    if not ctx.c.execute(
        "SELECT 1 FROM systems.model_sets WHERE workspace_id=%s AND id='kyc-line-up-mock'",
        (ctx.ws,),
    ).fetchone():
        ctx.c.execute(
            "INSERT INTO systems.model_sets(workspace_id,id,version,name,created_by,change_note,members_sha256) VALUES(%s,'kyc-line-up-mock',1,%s,'local-seed',%s,%s)",
            (ctx.ws, "KYC line-up (mock)", "local seed: three controlled-mock profiles", h),
        )
        for m in members:
            ctx.c.execute(
                "INSERT INTO systems.model_set_members(workspace_id,model_set_id,model_set_version,system_id,system_version) VALUES(%s,'kyc-line-up-mock',1,%s,%s)",
                (ctx.ws, m["system_id"], m["system_version"]),
            )
