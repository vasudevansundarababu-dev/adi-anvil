import os
from pathlib import Path

ROOT = Path(os.environ.get("ANVIL_ROOT", Path(__file__).resolve().parents[4]))
if (ROOT / ".env").exists():
    for line in (ROOT / ".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def setting(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing configuration: {name}")
    return value


def local_only():
    if setting("ANVIL_ENV") != "local":
        raise RuntimeError("Development identity/fixture installation is local-only")
    if setting("WEB_ORIGIN") != "http://127.0.0.1:3202":
        raise RuntimeError("Unqualified web origin")


local_only()
