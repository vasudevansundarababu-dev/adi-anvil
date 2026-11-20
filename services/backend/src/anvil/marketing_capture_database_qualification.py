"""Operator-owned qualification of ONE capture API database target.

Inventory reads never connect. This receipt cannot qualify a peer, registrar,
scheduler, project, Marketing graph or paid dispatch. Probe evidence and its
independent review must exist before an operator installs this read-only file.
"""

import hashlib
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path

from psycopg import capabilities, pq

from anvil.config import ROOT
from anvil.praxis_generic_contract import digest, load

SCHEMA = "anvil.capture-database-runtime-qualification.v1"
SCOPE = "capture_api_database_target_only"
FILE = "ANVIL_CAPTURE_DATABASE_QUALIFICATION_FILE"
IMAGE = "ANVIL_CAPTURE_DATABASE_IMAGE_DIGEST"
CHECKS = ("authenticated_target", "restricted_role", "read_only_scope",
          "actual_server_cancel", "terminal_cleanup", "no_model_dispatch")


def sha(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def trusted_transport(parameters):
    """Admission requires an immutable explicit trust root for TCP TLS."""
    if parameters["host"].startswith("/"):
        return
    if parameters.get("sslmode") != "verify-full" or not parameters.get("sslrootcert"):
        raise ValueError("Authenticated TLS target with explicit trust root required")
    for name in ("sslrootcert", "sslcert", "sslcrl"):
        if parameters.get(name):
            path = Path(parameters[name])
            info = path.stat()
            if (path.resolve(strict=True) != path or info.st_uid != 0
                    or info.st_mode & 0o022 or not os.statvfs(path).f_flag & os.ST_RDONLY):
                raise ValueError("Immutable operator trust material required")


def runtime_identity():
    """Exact installed source/lock/driver binding; no network or credentials."""
    source = Path(__file__).parent
    files = [source / name for name in (
        "marketing_capture_database.py", "marketing_capture_database_target.py",
        "marketing_capture_database_qualification.py", "marketing_capture_database_probe.py")]
    files.append(source.parents[1] / "uv.lock")
    image = os.environ.get(IMAGE, "")
    if not sha(image) or not capabilities.has_cancel_safe():
        raise ValueError("Qualified capture driver/image identity required")
    return {
        "source_sha256": digest({path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}),
        "image_sha256": image,
        "psycopg_version": version("psycopg"),
        "libpq_version": pq.version(),
        "cancel_safe": True,
    }


def validate(body, target_sha256, identity, *, now=None):
    """Validate evidence, never mint, extend or promote a qualification."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(body, dict):
        raise ValueError("Explicit qualification object required")
    if type(body.get("issued_at")) is not str or type(body.get("expires_at")) is not str:
        raise ValueError("Explicit qualification timestamps required")
    issued = datetime.fromisoformat(body["issued_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    checks = body.get("checks")
    if (body.get("schema_version") != SCHEMA or body.get("scope") != SCOPE
            or body.get("origin") != "independent_qa" or body.get("qualified") is not True
            or body.get("spending_authority") is not False or body.get("revoked") is not False
            or not sha(target_sha256) or body.get("target_sha256") != target_sha256
            or body.get("runtime_identity") != identity
            or not sha(body.get("role_profile_sha256"))
            or not sha(body.get("observed_target_sha256"))
            or not sha(body.get("probe_evidence_sha256"))
            or not sha(body.get("review_receipt_sha256"))
            or issued.tzinfo is None or expires.tzinfo is None
            or not issued <= now < expires or expires - issued > timedelta(hours=24)
            or not isinstance(checks, dict) or set(checks) != set(CHECKS)
            or any(not isinstance(checks[key], dict)
                   or checks[key].get("status") != "passed"
                   or not sha(checks[key].get("evidence_sha256")) for key in CHECKS)):
        raise ValueError("Current exact capture target qualification required")
    return {"schema_version": SCHEMA, "scope": SCOPE,
            "receipt_sha256": digest(body), "target_sha256": target_sha256,
            "expires_at": body["expires_at"], "spending_authority": False}


def installed(target_sha256):
    """Read only a root-owned immutable operator mount, never uploaded data."""
    configured = os.environ.get(FILE)
    if not configured:
        return None
    try:
        path = Path(configured)
        # A dedicated operator mount avoids accepting arbitrary uploaded JSON.
        expected = ROOT / ".data/runtime-qualification/capture-database/current.json"
        if path != expected or path.resolve(strict=True) != expected:
            raise ValueError("Fixed operator qualification path required")
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("No symlink qualification paths")
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o022 or not 0 < info.st_size <= 32768
                or not os.statvfs(path).f_flag & os.ST_RDONLY):
            raise ValueError("Read-only root-owned qualification mount required")
        from anvil.marketing_capture_database_target import configuration

        parameters, actual = configuration()
        if actual != target_sha256:
            raise ValueError("Capture target changed during admission")
        trusted_transport(parameters)
        return validate(load(path.read_bytes()), target_sha256, runtime_identity())
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        return None
