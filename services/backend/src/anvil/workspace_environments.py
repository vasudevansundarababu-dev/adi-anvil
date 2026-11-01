"""Inert, immutable task environment intake. Uploaded code is never executed here."""

import hashlib
from pathlib import PurePosixPath
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, model_validator

from anvil import artifacts, auth
from anvil.db import audit, digest, one, uid
from anvil.schemas import Strict


class ContextFile(Strict):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=262144)


class Environment(Strict):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    files: list[ContextFile] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def safe_context(self):
        paths = [file.path for file in self.files]
        if len(set(paths)) != len(paths) or "Dockerfile" not in paths:
            raise ValueError("Select one Dockerfile and unique companion file paths")
        if sum(len(file.content.encode()) for file in self.files) > 1048576:
            raise ValueError("Environment context exceeds 1 MiB")
        if any(
            len(file.content.encode()) > 262144 or "\x00" in file.content for file in self.files
        ):
            raise ValueError("Environment files must be text up to 256 KiB each")
        for path in paths:
            parts = PurePosixPath(path).parts
            if (
                not parts
                or path.startswith("/")
                or "\\" in path
                or any(part in ("", ".", "..") or part.startswith(".") for part in path.split("/"))
                or any(ord(char) < 32 for char in path)
            ):
                raise ValueError("Only relative, non-hidden environment paths are accepted")
        return self


def listing(c, sid):
    return [
        {
            **row,
            "status": "quarantined",
            "execution_available": False,
            "reason": "Custom Dockerfile build isolation and scanner qualification are not available yet",
        }
        for row in c.execute(
            "SELECT id,name,dockerfile_sha256,context_sha256,created_at FROM anvil.workspace_task_environments WHERE source_id=%s ORDER BY created_at DESC,id DESC",
            (sid,),
        ).fetchall()
    ]


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace")

    @router.post("/tasks/{sid}/environments")
    def import_environment(project: UUID, sid: UUID, body: Environment, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            if not one(c, "SELECT id FROM anvil.praxis_sources WHERE id=%s", (sid,)):
                raise HTTPException(404, "Task version not found in this project")

            def save():
                files = sorted((file.model_dump() for file in body.files), key=lambda f: f["path"])
                checksum = digest(files)
                old = one(
                    c,
                    "SELECT id FROM anvil.workspace_task_environments WHERE source_id=%s AND context_sha256=%s",
                    (sid, checksum),
                )
                if old:
                    return next(item for item in listing(c, sid) if item["id"] == old["id"])
                from anvil.harbor_package import encoded

                aid = artifacts.store(c, project, encoded(files), "internal", scan="quarantined")
                identifier = uid()
                dockerfile = next(file["content"] for file in files if file["path"] == "Dockerfile")
                c.execute(
                    "INSERT INTO anvil.workspace_task_environments(id,project_id,source_id,name,dockerfile_artifact_id,dockerfile_sha256,context_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        identifier,
                        project,
                        sid,
                        body.name.strip(),
                        aid,
                        hashlib.sha256(dockerfile.encode()).hexdigest(),
                        checksum,
                        user,
                    ),
                )
                audit(
                    c,
                    project,
                    user,
                    "workspace.environment_imported_quarantined",
                    identifier,
                    {
                        "source_id": str(sid),
                        "context_sha256": checksum,
                        "execution_available": False,
                    },
                )
                return next(item for item in listing(c, sid) if str(item["id"]) == identifier)

            return wrap(idempotent(c, project, user, request, body, save), request)

    return router
