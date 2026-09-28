"""Repository-only guard; reports paths/rules, never matched secret values."""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    rb"sk-[A-Za-z0-9_-]{24,}",
    rb"gh[pousr]_[A-Za-z0-9]{25,}",
    rb"AKIA[0-9A-Z]{16}",
]


def scan():
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    local_values = []
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                if len(value) > 12 and any(x in key for x in ("PASSWORD", "SECRET", "SESSION_KEY")):
                    local_values.append(value.encode())
    accounts = ROOT / ".local/demo-accounts.md"
    if accounts.exists():
        local_values.extend(s.encode() for s in re.findall(r"`([^`]{16,})`", accounts.read_text()))
    findings = []
    for name in filter(None, files):
        p = Path(name)
        if p.name != ".env.example" and (
            p.name.startswith(".env")
            or any(x in p.parts for x in (".local", ".data", ".secrets"))
            or p.suffix == ".log"
        ):
            findings.append({"path": name, "rule": "private_file_tracked"})
            continue
        data = (ROOT / p).read_bytes()
        if any(re.search(pattern, data) for pattern in PATTERNS):
            findings.append({"path": name, "rule": "credential_pattern"})
        if any(value in data for value in local_values):
            findings.append({"path": name, "rule": "local_credential_match"})
    print(
        json.dumps({"tracked_files_checked": len(list(filter(None, files))), "findings": findings})
    )
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(int(scan()))
