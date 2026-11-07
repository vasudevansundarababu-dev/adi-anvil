import hashlib
import os
from pathlib import Path

from fastapi import HTTPException

from anvil.config import ROOT
from anvil.db import one, uid

BENCHMARK_PRIVATE_CLASSES = frozenset(
    {"benchmark_raw", "benchmark_eval", "benchmark_judge", "benchmark_trace"}
)


def storage_root():
    configured = Path(os.environ.get("ARTIFACT_ROOT", ".data/artifacts"))
    root = configured if configured.is_absolute() else ROOT / configured
    if root.is_symlink() or not root.resolve().is_relative_to(ROOT.resolve()):
        raise RuntimeError("Artifact root must remain within this local repository")
    return root


def store(
    c,
    project,
    data: bytes,
    classification,
    mime="application/json",
    origin="illustrative",
    scan="clean",
):
    if classification in BENCHMARK_PRIVATE_CLASSES:
        raise HTTPException(403, "Private benchmark objects require the separate vault")
    aid = uid()
    folder = storage_root() / str(project)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    # The dedicated Docker worker runs as root; the API runs as the artifact-volume
    # owner. Keep artifacts owner-only without making worker-created files unreadable
    # to that same trusted application identity.
    owner = storage_root().stat().st_uid
    if os.geteuid() == 0 and folder.stat().st_uid != owner:
        os.chown(folder, owner, -1)
    path = folder / aid
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
        if os.geteuid() == 0 and os.fstat(f.fileno()).st_uid != owner:
            os.fchown(f.fileno(), owner, -1)
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


def read(c, aid, actor_only=False, *, structured_import=False):
    a = one(c, "SELECT * FROM anvil.artifacts WHERE id=%s", (aid,))
    if not a:
        raise HTTPException(404, "Artifact not found")
    if a["classification"] in BENCHMARK_PRIVATE_CLASSES:
        raise HTTPException(403, "Private benchmark artifacts require assigned access")
    structured_source = (
        structured_import
        and not actor_only
        and a.get("upload_purpose") == "task_import"
        and a["scan_status"] == "quarantined"
    )
    if (a["scan_status"] != "clean" and not structured_source) or (
        actor_only and a["classification"] != "actor"
    ):
        raise HTTPException(403, "Artifact unavailable for this use")
    root = storage_root().resolve()
    path = root / a["object_key"]
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise HTTPException(403, "Invalid artifact location")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != a["sha256"]:
        raise HTTPException(409, "Artifact integrity mismatch")
    return data
