import hashlib
import os

from fastapi import HTTPException

from anvil.config import ROOT
from anvil.db import one, uid


def store(
    c,
    project,
    data: bytes,
    classification,
    mime="application/json",
    origin="illustrative",
    scan="clean",
):
    aid = uid()
    folder = ROOT / ".data/artifacts" / str(project)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / aid
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
        f.write(data)
    c.execute(
        "INSERT INTO anvil.artifacts(id,project_id,object_key,sha256,byte_size,mime_type,classification,scan_status,origin) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            aid,
            project,
            f"{project}/{aid}",
            hashlib.sha256(data).hexdigest(),
            len(data),
            mime,
            classification,
            scan,
            origin,
        ),
    )
    return aid


def read(c, aid, actor_only=False):
    a = one(c, "SELECT * FROM anvil.artifacts WHERE id=%s", (aid,))
    if not a:
        raise HTTPException(404, "Artifact not found")
    if a["scan_status"] != "clean" or (actor_only and a["classification"] != "actor"):
        raise HTTPException(403, "Artifact unavailable for this use")
    root = (ROOT / ".data/artifacts").resolve()
    path = root / a["object_key"]
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise HTTPException(403, "Invalid artifact location")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != a["sha256"]:
        raise HTTPException(409, "Artifact integrity mismatch")
    return data
