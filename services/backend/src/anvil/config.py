import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(os.environ.get("ANVIL_ROOT", Path(__file__).resolve().parents[4]))
if (ROOT / ".env").exists():
    for line in (ROOT / ".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)

LOCAL_ORIGIN = "http://127.0.0.1:3202"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def setting(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing configuration: {name}")
    return value


def https_origin(name: str, path_prefix: str = "") -> str:
    value = setting(name)
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.hostname in LOOPBACK_HOSTS
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or value.endswith("/")
        or not parts.path.startswith(path_prefix)
        or (not path_prefix and parts.path)
    ):
        raise RuntimeError(f"Unqualified cloud setting: {name}")
    return value


def validate_cloud():
    """Cloud mode is explicit and narrower than local: no seeds, HTTPS only, no live/email."""
    https_origin("WEB_ORIGIN")
    issuer = https_origin("OIDC_ISSUER", "/realms/")
    if not issuer.rsplit("/realms/", 1)[1] or "/" in issuer.rsplit("/realms/", 1)[1]:
        raise RuntimeError("Unqualified cloud setting: OIDC_ISSUER")
    for flag in ("ANVIL_LIVE_PROVIDERS_ENABLED", "ANVIL_REAL_EMAIL_ENABLED"):
        if os.environ.get(flag, "false") != "false":
            raise RuntimeError(f"{flag} must remain false in cloud mode")
    if len(setting("ANVIL_SESSION_KEY")) < 32:
        raise RuntimeError("ANVIL_SESSION_KEY too short for cloud mode")


def environment() -> str:
    env = setting("ANVIL_ENV")
    if env == "local":
        if setting("WEB_ORIGIN") != LOCAL_ORIGIN:
            raise RuntimeError("Unqualified web origin")
    elif env == "cloud":
        validate_cloud()
    else:
        raise RuntimeError("Development identity/fixture installation is local-only")
    return env


ENV = environment()
CLOUD = ENV == "cloud"


def local_only():
    """Synthetic identities, demo projects and compose-based backups never run in cloud."""
    if ENV != "local":
        raise RuntimeError("Development identity/fixture installation is local-only")
