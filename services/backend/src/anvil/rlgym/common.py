"""Shared RL Gym v2 plumbing: errors, people and service actors, workspace scope, idempotency, outbox, audit.

Every request runs in one PostgreSQL transaction with `rlgym.workspace` set only after the caller has been
checked (an active member for people; a known client key for services). Row-level security on every
workspace table then keeps rows of other workspaces invisible (ARCHITECTURE 11).
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import uuid4

import psycopg
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from anvil import auth
from anvil.config import setting

STATUS = {
    "VALIDATION_FAILED": 422,
    "NOT_FOUND": 404,
    "HASH_MISMATCH": 422,
    "TEMPLATE_NOT_ACTIVE": 409,
    "BINDING_INCOMPATIBLE": 409,
    "ADMISSION_REFUSED": 409,
    "REGISTRY_UNAVAILABLE": 503,
    "FORGE_UNAVAILABLE": 503,
    "IDEMPOTENCY_CONFLICT": 409,
    "IDEMPOTENCY_KEY_REQUIRED": 428,
    "TENANT_SCOPE_VIOLATION": 403,
    "UNAUTHENTICATED": 401,
    "FORBIDDEN": 403,
    "CONFLICT": 409,
    "SIGNATURE_INVALID": 401,
    "KEY_MISSING": 422,
    "BUDGET_EXCEEDED": 409,
    "RATE_LIMITED": 429,
}


class GymError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}
        self.status = STATUS.get(code, 400)


def canonical(value):
    return json.dumps(
        jsonable_encoder(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def sha(value):
    """SHA-256 over sorted-key compact JSON (the JCS subset used by our integer/string payloads)."""
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def new_id(prefix=""):
    return prefix + uuid4().hex[:12]


@dataclass
class Actor:
    id: str
    kind: str  # person | service
    name: str
    profile: str | None = None
    binding_approver: bool = False

    def require_person(self):
        if self.kind != "person":
            raise GymError(
                "FORBIDDEN", "This action must be taken by a person, not a service client"
            )


@dataclass
class Ctx:
    c: psycopg.Connection
    workspace: dict
    actor: Actor

    @property
    def ws(self):
        return self.workspace["id"]


def _connect():
    return psycopg.connect(setting("DATABASE_URL"), row_factory=dict_row)


def _scope(c, ws_id):
    c.execute("SELECT set_config('rlgym.workspace', %s, true)", (str(ws_id),))


def workspace_row(c, slug):
    ws = c.execute(
        "SELECT id, slug, name, tier FROM admin.workspaces WHERE slug=%s", (slug,)
    ).fetchone()
    if not ws:
        raise GymError("NOT_FOUND", "Workspace not found")
    return ws


SERVICE_KEYS = {
    "adi-forge": "RLGYM_FORGE_CLIENT_KEY",
    "studio": "RLGYM_STUDIO_CLIENT_KEY",
}


def service_client(request: Request):
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    presented = header[7:].strip()
    for client, env_name in SERVICE_KEYS.items():
        expected = os.environ.get(env_name)
        if expected and secrets.compare_digest(presented, expected):
            return client
    raise GymError("UNAUTHENTICATED", "Unknown service client key")


@contextmanager
def scope(request: Request, slug: str, services=(), people=True):
    """Authenticate the caller, check workspace membership, open one scoped transaction."""
    client = service_client(request)
    if client is not None:
        if client not in services:
            raise GymError("FORBIDDEN", f"Client {client} may not call this route")
        with _connect() as c:
            ws = workspace_row(c, slug)
            _scope(c, ws["id"])
            yield Ctx(c, ws, Actor(client, "service", client))
        return
    if not people:
        raise GymError("UNAUTHENTICATED", "Service client key required")
    try:
        user = auth.identity(request)
    except Exception as exc:  # HTTPException from the legacy session layer
        status = getattr(exc, "status_code", 401)
        raise GymError(
            "UNAUTHENTICATED" if status == 401 else "FORBIDDEN",
            getattr(exc, "detail", "Sign in required"),
        ) from None
    with _connect() as c:
        ws = workspace_row(c, slug)
        member = c.execute(
            "SELECT * FROM admin.membership(%s,%s)", (ws["id"], user["id"])
        ).fetchone()
        if not member or member["status"] != "active":
            raise GymError("TENANT_SCOPE_VIOLATION", "Not in this workspace")
        _scope(c, ws["id"])
        c.execute(
            "UPDATE admin.users SET last_seen_at=now() WHERE workspace_id=%s AND id=%s",
            (ws["id"], user["id"]),
        )
        yield Ctx(
            c,
            ws,
            Actor(
                str(user["id"]),
                "person",
                user["name"],
                member["profile"],
                member["binding_approver"],
            ),
        )


@contextmanager
def system_scope(ws_id=None):
    """Transaction for internal consumers (registry events, dispatcher). Scope is set per workspace."""
    with _connect() as c:
        if ws_id:
            _scope(c, ws_id)
        yield c


def set_scope(c, ws_id):
    _scope(c, ws_id)


def all_workspaces(c):
    return c.execute("SELECT id, slug FROM admin.workspaces ORDER BY slug").fetchall()


def idempotent(ctx: Ctx, request: Request, body, fn):
    key = request.headers.get("idempotency-key")
    if not key or len(key) > 200:
        raise GymError(
            "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header required (maximum 200 characters)"
        )
    route = f"{ctx.workspace['slug']}:{request.method}:{request.url.path}"
    h = sha(body)
    old = ctx.c.execute(
        "SELECT * FROM infra.idempotency_keys WHERE client=%s AND route=%s AND key=%s FOR UPDATE",
        (ctx.actor.id, route, key),
    ).fetchone()
    if old:
        if old["request_sha256"] != h:
            raise GymError("IDEMPOTENCY_CONFLICT", "Idempotency-Key reused with a different body")
        return old["response"]
    result = jsonable_encoder(fn())
    ctx.c.execute(
        "INSERT INTO infra.idempotency_keys(client,key,route,request_sha256,response,status) VALUES(%s,%s,%s,%s,%s,200)",
        (ctx.actor.id, key, route, h, Jsonb(result)),
    )
    return result


def audit(c, ws, actor, action, subject, reason=None, details=None):
    kind = actor.kind if isinstance(actor, Actor) else "system"
    name = actor.id if isinstance(actor, Actor) else str(actor)
    c.execute(
        "INSERT INTO admin.audit_events(workspace_id,actor,actor_kind,action,subject,reason,details) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (ws, name, kind, action, subject, reason, Jsonb(jsonable_encoder(details or {}))),
    )


def emit(c, ws, topic, key, payload, destination="internal"):
    """State change and its event in one transaction (SPEC P3). Internal consumers (To do rules) run now;
    external destinations are delivered by the dispatcher after commit, with retries."""
    from anvil.rlgym.admin import todo

    event_id = str(uuid4())
    body = {
        "id": event_id,
        "type": topic,
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data": payload,
    }
    c.execute(
        "INSERT INTO infra.outbox(id,workspace_id,topic,key,payload,destination,published_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (
            event_id,
            ws,
            topic,
            key,
            Jsonb(jsonable_encoder(body)),
            destination,
            None
            if destination != "internal"
            else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        ),
    )
    if ws:
        todo.on_event(c, ws, topic, payload, event_id)
    return event_id


def sign(secret, timestamp, body: bytes):
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def verify_signature(request_headers, body: bytes, secret_env="RLGYM_REGISTRY_WEBHOOK_SECRET"):
    secret = os.environ.get(secret_env)
    ts = request_headers.get("x-adi-timestamp", "")
    sig = request_headers.get("x-adi-signature", "")
    if not secret or not ts.isdigit() or abs(time.time() - int(ts)) > 300:
        raise GymError("SIGNATURE_INVALID", "Missing or stale webhook signature")
    if not secrets.compare_digest(sign(secret, ts, body), sig):
        raise GymError("SIGNATURE_INVALID", "Webhook signature does not match")


def require(condition, code, message, **details):
    if not condition:
        raise GymError(code, message, details)
