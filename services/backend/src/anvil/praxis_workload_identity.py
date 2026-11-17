"""Keyless, audience-bound workload identity; no anonymous or static-key fallback.

Google signs the short-lived ID token. Anvil's durable project grant, current
sponsor access and pilot window still authorize each operation independently.
Metadata is available only to the already isolated API workload.
"""

import re
import time
from datetime import datetime, timezone
from threading import Lock

import httpx
from authlib.jose import JsonWebToken
from pydantic import SecretStr

ISSUER = "https://accounts.google.com"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ANVIL_AUDIENCE = "https://anvil-qa.adi-labs.ai"
PRAXIS_AUDIENCE = "https://praxis-api-742785092638.us-central1.run.app"
STOP = datetime(2026, 12, 11, 5, 48, 4, tzinfo=timezone.utc)
METADATA_URL = (
    "http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/identity"
)
_keys = None
_keys_until = 0
_lock = Lock()


class WorkloadIdentityError(RuntimeError):
    """Only fixed safe codes escape this boundary; never tokens or remote bodies."""


def bounded_get(url, *, headers=None, params=None, transport=None, maximum=65536):
    with httpx.Client(
        timeout=3, trust_env=False, follow_redirects=False, transport=transport
    ) as client:
        with client.stream("GET", url, headers=headers, params=params) as response:
            if response.status_code != 200:
                raise WorkloadIdentityError("workload_identity_transport_unavailable")
            value = bytearray()
            for chunk in response.iter_bytes(chunk_size=4096):
                value.extend(chunk)
                if len(value) > maximum:
                    raise WorkloadIdentityError("workload_identity_response_bound")
            return bytes(value), dict(response.headers)


def public_keys(*, transport=None):
    global _keys, _keys_until
    from anvil.praxis_generic_contract import load

    with _lock:
        # Mock transports never populate or consume the serving key cache.
        if transport is None and _keys is not None and time.monotonic() < _keys_until:
            return _keys
        raw, _ = bounded_get(JWKS_URL, transport=transport)
        value = load(raw)
        if (
            set(value) != {"keys"}
            or not isinstance(value["keys"], list)
            or not 1 <= len(value["keys"]) <= 10
        ):
            raise WorkloadIdentityError("workload_signing_keys_unavailable")
        if transport is None:
            _keys, _keys_until = value, time.monotonic() + 300
        return value


def verify(token, *, audience=ANVIL_AUDIENCE, now=None, transport=None):
    """Return authenticated numeric subject only after signature and claim checks."""
    instant = datetime.now(timezone.utc) if now is None else now
    if (
        audience != ANVIL_AUDIENCE
        or instant.tzinfo is None
        or instant >= STOP
        or type(token) is not str
        or not 100 <= len(token) <= 16384
        or not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token)
    ):
        raise WorkloadIdentityError("workload_identity_rejected")
    try:
        claims = JsonWebToken(["RS256"]).decode(
            token,
            public_keys(transport=transport),
            claims_options={
                "iss": {"essential": True, "value": ISSUER},
                "aud": {"essential": True, "value": audience},
                "sub": {"essential": True},
                "email": {"essential": True},
                "email_verified": {"essential": True},
                "iat": {"essential": True},
                "exp": {"essential": True},
            },
        )
        timestamp = int(instant.timestamp())
        claims.validate(now=timestamp, leeway=0)
        if (
            claims["aud"] != audience
            or claims["iss"] != ISSUER
            or type(claims["sub"]) is not str
            or not re.fullmatch(r"[0-9]{6,30}", claims["sub"])
            or type(claims["email"]) is not str
            or not re.fullmatch(
                r"[a-z0-9][a-z0-9._-]*@[a-z0-9][a-z0-9.-]*\.iam\.gserviceaccount\.com",
                claims["email"],
            )
            or claims["email_verified"] is not True
            or type(claims["iat"]) is not int
            or type(claims["exp"]) is not int
            or not 0 < claims["exp"] - claims["iat"] <= 3700
            or not claims["iat"] <= timestamp < claims["exp"]
        ):
            raise ValueError("claims")
        return {
            "issuer": ISSUER,
            "subject": claims["sub"],
            "account_email": claims["email"],
            "audience": audience,
        }
    except Exception:
        raise WorkloadIdentityError("workload_identity_rejected") from None


def metadata_token(*, audience=PRAXIS_AUDIENCE, transport=None):
    """Obtain an ephemeral token from the attached API identity, never a key file."""
    if audience != PRAXIS_AUDIENCE:
        raise WorkloadIdentityError("workload_audience_not_allowed")
    try:
        raw, headers = bounded_get(
            METADATA_URL,
            headers={"Metadata-Flavor": "Google"},
            params={"audience": audience, "format": "full"},
            transport=transport,
            maximum=16384,
        )
        if headers.get("metadata-flavor") != "Google":
            raise ValueError("metadata")
        value = raw.decode("ascii")
        if not 100 <= len(value) <= 16384 or not re.fullmatch(
            r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", value
        ):
            raise ValueError("token")
        return SecretStr(value)
    except Exception:
        raise WorkloadIdentityError("workload_metadata_unavailable") from None
