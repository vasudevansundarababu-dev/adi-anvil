import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(os.environ.get("ANVIL_ROOT", Path(__file__).resolve().parents[4]))
if (ROOT / ".env").exists():
    for line in (ROOT / ".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)

def local_web_origin():
    # A separate checkout may use an unused loopback port, never a remote origin.
    value = os.environ.get("ANVIL_LOCAL_WEB_PORT", "3202")
    if not value.isascii() or not value.isdecimal() or not 1024 <= int(value) <= 65535:
        raise RuntimeError("Invalid local web port")
    return f"http://127.0.0.1:{int(value)}"


LOCAL_ORIGIN = local_web_origin()
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
    """HTTPS only; legacy live/email stay off. Harbor has independent admission gates."""
    https_origin("WEB_ORIGIN")
    issuer = https_origin("OIDC_ISSUER", "/realms/")
    if not issuer.rsplit("/realms/", 1)[1] or "/" in issuer.rsplit("/realms/", 1)[1]:
        raise RuntimeError("Unqualified cloud setting: OIDC_ISSUER")
    for flag in ("ANVIL_LIVE_PROVIDERS_ENABLED", "ANVIL_REAL_EMAIL_ENABLED"):
        if os.environ.get(flag, "false") != "false":
            raise RuntimeError(f"{flag} must remain false in cloud mode")
    if os.environ.get("ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", "false") not in {"true", "false"}:
        raise RuntimeError("Unqualified cloud Harbor admission flag")
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


def harbor_live_enabled():
    flag = "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED" if CLOUD else "ANVIL_LIVE_PROVIDERS_ENABLED"
    return os.environ.get(flag, "false") == "true"


def private_file_owner(uid):
    # The Docker-host worker is root; the API owns the same read-only mounted files.
    return uid == os.getuid() or (CLOUD and os.getuid() == 0 and uid == 10001)


def local_only():
    """Synthetic identities, demo projects and compose-based backups never run in cloud."""
    if ENV != "local":
        raise RuntimeError("Development identity/fixture installation is local-only")
