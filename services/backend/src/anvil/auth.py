import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebToken
from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from anvil.config import CLOUD, setting
from anvil.db import one, transaction

router = APIRouter(prefix="/api/v1")


def hashed(value):
    return hashlib.sha256(value.encode()).hexdigest()


def cipher():
    return Fernet(
        base64.urlsafe_b64encode(hashlib.sha256(setting("ANVIL_SESSION_KEY").encode()).digest())
    )


def identity(request: Request):
    token = request.cookies.get("anvil_session", "")
    with transaction() as c:
        user = one(
            c,
            """SELECT u.id,u.name,s.csrf_hash,s.issued_at FROM anvil.sessions s
                        JOIN anvil.users u ON u.id=s.user_id WHERE s.token_hash=%s
                        AND u.active AND s.revoked_at IS NULL AND s.expires_at>now()
                        AND s.last_seen_at>now()-interval '30 minutes' """,
            (hashed(token),),
        )
        if not user:
            raise HTTPException(401, "Sign in required")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("origin") != setting("WEB_ORIGIN") or not secrets.compare_digest(
                hashed(request.headers.get("x-csrf-token", "")), user["csrf_hash"]
            ):
                raise HTTPException(403, "CSRF validation failed")
        c.execute(
            "UPDATE anvil.sessions SET last_seen_at=now() WHERE token_hash=%s", (hashed(token),)
        )
    return user


def project_roles(c, project, user):
    rows = c.execute(
        "SELECT role FROM anvil.memberships WHERE project_id=%s AND user_id=%s AND active",
        (project, user),
    ).fetchall()
    if not rows:
        raise HTTPException(404, "Project not found")
    return {r["role"] for r in rows}


def require(roles, *allowed):
    # Legacy resource APIs still name old permission categories. They are not active
    # membership roles and are never returned by /me or accepted for invitations.
    admin_actions = {"admin", "product-owner", "sales"}
    engineering_actions = {
        "rl-engineer",
        "researcher",
        "data-engineer",
        "advisor",
        "reviewer",
        "adjudicator",
    }
    requested = set(allowed)
    permitted = (
        "admin" in roles and bool(requested.intersection(admin_actions | engineering_actions))
    ) or ("rl-engineer" in roles and bool(requested.intersection(engineering_actions)))
    if not permitted:
        raise HTTPException(403, "Role does not permit this action")


@router.get("/auth/login")
def login():
    state, nonce, verifier = [secrets.token_urlsafe(32) for _ in range(3)]
    with transaction() as c:
        c.execute(
            "INSERT INTO anvil.oidc_login_attempts(state_hash,nonce_hash,verifier_cipher) VALUES(%s,%s,%s)",
            (hashed(state), hashed(nonce), cipher().encrypt(verifier.encode()).decode()),
        )
    params = {
        "client_id": setting("OIDC_CLIENT_ID"),
        "response_type": "code",
        "scope": "openid profile",
        "redirect_uri": setting("WEB_ORIGIN") + "/api/v1/auth/callback",
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "prompt": "login",
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode(),
    }
    response = RedirectResponse(
        setting("OIDC_ISSUER") + "/protocol/openid-connect/auth?" + urlencode(params)
    )
    response.set_cookie(
        "anvil_login",
        state,
        httponly=True,
        secure=CLOUD,
        samesite="lax",
        max_age=300,
        path="/api/v1/auth",
    )
    return response


@router.get("/auth/callback")
def callback(request: Request, state: str = "", code: str = ""):
    if not state or not secrets.compare_digest(state, request.cookies.get("anvil_login", "")):
        raise HTTPException(401, "Invalid login state")
    with transaction() as c:
        attempt = one(
            c,
            """UPDATE anvil.oidc_login_attempts SET consumed_at=now()
                         WHERE state_hash=%s AND consumed_at IS NULL AND expires_at>now() RETURNING *""",
            (hashed(state),),
        )
    if not attempt:
        raise HTTPException(401, "Expired or reused login")
    try:
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            token = client.post(
                setting("OIDC_ISSUER") + "/protocol/openid-connect/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": setting("OIDC_CLIENT_ID"),
                    "client_secret": setting("OIDC_CLIENT_SECRET"),
                    "redirect_uri": setting("WEB_ORIGIN") + "/api/v1/auth/callback",
                    "code_verifier": cipher().decrypt(attempt["verifier_cipher"].encode()).decode(),
                },
            )
            token.raise_for_status()
            jwks = client.get(setting("OIDC_ISSUER") + "/protocol/openid-connect/certs")
            jwks.raise_for_status()
            claims = JsonWebToken(["RS256"]).decode(
                token.json()["id_token"],
                jwks.json(),
                claims_options={
                    "iss": {"essential": True, "value": setting("OIDC_ISSUER")},
                    "aud": {"essential": True, "value": setting("OIDC_CLIENT_ID")},
                    "exp": {"essential": True},
                    "sub": {"essential": True},
                    "nonce": {"essential": True},
                },
            )
            claims.validate(leeway=5)
            if not secrets.compare_digest(hashed(claims["nonce"]), attempt["nonce_hash"]):
                raise ValueError("nonce")
    except Exception:
        raise HTTPException(401, "OIDC verification failed") from None
    session, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    with transaction() as c:
        user = one(
            c,
            "SELECT id FROM anvil.users WHERE issuer=%s AND subject=%s AND active",
            (claims["iss"], claims["sub"]),
        )
        if not user:
            raise HTTPException(403, "Invitation required")
        c.execute(
            "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
            (hashed(session), user["id"], hashed(csrf)),
        )
    response = RedirectResponse("/")
    response.delete_cookie("anvil_login", path="/api/v1/auth", secure=CLOUD)
    response.set_cookie(
        "anvil_session", session, httponly=True, secure=CLOUD, samesite="lax", max_age=28800
    )
    response.set_cookie(
        "anvil_csrf", csrf, httponly=False, secure=CLOUD, samesite="lax", max_age=28800
    )
    return response


@router.post("/auth/logout")
def logout(request: Request):
    identity(request)
    with transaction() as c:
        c.execute(
            "UPDATE anvil.sessions SET revoked_at=now() WHERE token_hash=%s",
            (hashed(request.cookies.get("anvil_session", "")),),
        )
    response = JSONResponse({"data": {"signed_out": True}})
    response.delete_cookie("anvil_session", secure=CLOUD)
    response.delete_cookie("anvil_csrf", secure=CLOUD)
    return response


@router.get("/me")
def me(request: Request):
    from anvil.workspace_access import project_access

    user = identity(request)
    with transaction(user=user["id"]) as c:
        projects = c.execute(
            """SELECT p.id,p.name,array_agg(m.role) roles FROM anvil.projects p
                             JOIN anvil.memberships m ON m.project_id=p.id
                             WHERE m.user_id=%s AND m.active GROUP BY p.id,p.name ORDER BY p.name""",
            (user["id"],),
        ).fetchall()
        for project in projects:
            c.execute("SELECT set_config('anvil.project',%s,true)", (str(project["id"]),))
            project["workspace_access"] = project_access(
                c, project["id"], user["id"], project["roles"]
            )
    return {"data": {"id": user["id"], "name": user["name"], "projects": projects}}
