"""Bounded Project/Task import with optional policy sidecar; no imported code executes."""

import base64
import hashlib
import io
import json
import stat
import zipfile
from typing import Literal

from fastapi import HTTPException
from pydantic import Field

from anvil.db import Jsonb, audit, digest, one, uid
from anvil.praxis_contract import Identifier, Model, PraxisTask, Text, actor_view
from anvil.praxis_export import Export
from anvil.praxis_policy import Project, ProjectPolicyManifest, validate_package
from anvil.task_parser import json_value

MAX_ARCHIVE = 26 * 1024 * 1024
MAX_EXPANDED = 30 * 1024 * 1024


class Environment(Model):
    id: Identifier
    name: str = Field(min_length=1, max_length=200)
    version: Identifier
    kind: str = Field(min_length=1, max_length=100)
    enforce: bool = True


class FailureMode(Model):
    id: Identifier
    title: Text
    criterion_ids: list[Identifier] = Field(max_length=100)


class TaskEntry(Model):
    path: str = Field(min_length=1, max_length=240)
    environment_ids: list[Identifier] = Field(min_length=1, max_length=30)
    dimensions: dict[str, Literal["correctness", "evidence", "constraints"]] = Field(
        default_factory=dict
    )
    failure_modes: list[FailureMode] = Field(default_factory=list, max_length=100)


class ProjectImport(Model):
    schema_version: Literal["anvil.task-group-import.v1"]
    source_project: Project
    environments: list[Environment] = Field(min_length=1, max_length=30)
    tasks: list[TaskEntry] = Field(min_length=1, max_length=1000)
    policy_manifest_path: str | None = None


def safe_path(path):
    import re

    if not re.fullmatch(
        r"[A-Za-z0-9_-][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*", path
    ) or any(p in {".", ".."} for p in path.split("/")):
        raise ValueError("Unsafe package path")
    return path


def archive_files(raw):
    if len(raw) > MAX_ARCHIVE:
        raise ValueError("Project archive exceeds 26 MiB")
    files, size, names = {}, 0, set()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.infolist()) > 1200:
            raise ValueError("Project archive has too many files")
        for item in archive.infolist():
            if item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise ValueError("Unsupported ZIP compression")
            safe_path(item.filename)
            if (
                item.filename.casefold() in names
                or item.is_dir()
                or stat.S_ISLNK(item.external_attr >> 16)
                or item.flag_bits & 1
            ):
                raise ValueError("Duplicate, directory, symlink or encrypted package entry")
            names.add(item.filename.casefold())
            size += item.file_size
            if size > MAX_EXPANDED or item.file_size > 10 * 1024 * 1024:
                raise ValueError("Expanded package exceeds bounded limits")
            with archive.open(item) as stream:
                data = stream.read(min(item.file_size + 1, MAX_EXPANDED + 1))
            if len(data) != item.file_size:
                raise ValueError("Package entry size mismatch")
            files[item.filename] = data
    return files


def parse_task(payload):
    value = json_value(payload)
    if value.get("schema_version") == "praxis.anvil.task.v3":
        from anvil.praxis_executable import TaskV3

        return TaskV3.model_validate(value)
    if value.get("schema_version") == "praxis.anvil.task.v2":
        from anvil.praxis_staged import PraxisTaskV2

        return PraxisTaskV2.model_validate(value)
    return PraxisTask.model_validate(value)


def extract_source(source, raw):
    """Extraction failures retain originals; neither text nor documents confer authority."""
    try:
        if source.media_type in {"text/plain", "text/markdown"}:
            text = raw.decode("utf-8-sig")
        else:
            import subprocess
            import sys
            from pathlib import Path

            child = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("benchmark_policy_text.py")),
                    source.media_type,
                ],
                input=raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=6,
                check=True,
                env={"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"},
            )
            text = json.loads(child.stdout)["text"]
        if "\x00" in text or len(text) > 100000:
            raise ValueError("Extracted text exceeds bound")
        return {"status": "extracted", "text": text, "reason": None}
    except Exception:
        return {
            "status": "needs_text",
            "text": None,
            "reason": "Readable text could not be extracted within supported limits; original retained",
        }


def parse(raw):
    files = archive_files(raw)
    manifest = ProjectImport.model_validate(json_value(files["project.json"]))
    envs = {e.id for e in manifest.environments}
    if len(envs) != len(manifest.environments):
        raise ValueError("Duplicate environment ID")
    tasks, references, expected = [], {}, {"project.json"}
    for entry in manifest.tasks:
        safe_path(entry.path)
        expected.add(entry.path)
        envelope = Export.model_validate(json_value(files[entry.path]))
        payload = envelope.payload_json.encode()
        if (
            hashlib.sha256(payload).hexdigest() != envelope.payload_sha256
            or envelope.source.project_id != manifest.source_project.id
        ):
            raise ValueError("Task source Project or exact payload hash mismatch")
        task = parse_task(payload)
        if task.task_id in {t["task_id"] for t in tasks}:
            raise ValueError("Task IDs must be unique within the imported Project version")
        if set(entry.environment_ids) - envs or len(set(entry.environment_ids)) != len(
            entry.environment_ids
        ):
            raise ValueError("Unresolved or duplicate Task environment binding")
        criteria = task.rubric.criteria if hasattr(task, "rubric") else []
        criterion_ids = {c.id for c in criteria}
        if set(entry.dimensions) - criterion_ids or any(
            set(f.criterion_ids) - criterion_ids for f in entry.failure_modes
        ):
            raise ValueError("Task rubric/failure reference does not resolve")
        references[(task.task_id, task.task_version)] = envelope.payload_sha256
        tasks.append(
            {
                "task_id": task.task_id,
                "task_version": task.task_version,
                "title": task.title,
                "payload_sha256": envelope.payload_sha256,
                "source": task.model_dump(),
                "actor": actor_view(task),
                "rubric": task.rubric.model_dump() if hasattr(task, "rubric") else None,
                "environment_ids": entry.environment_ids,
                "dimensions": entry.dimensions,
                "failure_modes": [f.model_dump() for f in entry.failure_modes],
            }
        )
    policies = None
    if manifest.policy_manifest_path:
        expected.add(safe_path(manifest.policy_manifest_path))
        pm = ProjectPolicyManifest.model_validate(json_value(files[manifest.policy_manifest_path]))
        policy_files = {s.path: files[s.path] for s in pm.sources}
        pm = validate_package(
            files[manifest.policy_manifest_path],
            policy_files,
            (manifest.source_project.id, manifest.source_project.version),
            references,
        )
        expected.update(policy_files)
        policies = {
            "manifest": pm.model_dump(),
            "sources": [
                {
                    **s.model_dump(),
                    "original_base64": base64.b64encode(policy_files[s.path]).decode(),
                    "extraction": extract_source(s, policy_files[s.path]),
                }
                for s in pm.sources
            ],
        }
    if set(files) != expected:
        raise ValueError("Archive files must exactly match declared Task and policy files")
    content = {
        "source_project": manifest.source_project.model_dump(),
        "environments": [e.model_dump() for e in manifest.environments],
        "tasks": tasks,
    }
    return content, policies


def public_group(row):
    content = row["content"]
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "source_project_id": row["source_project_id"],
        "source_version": row["source_version"],
        "content_sha256": row["content_sha256"],
        "created_at": row["created_at"],
        "environments": content["environments"],
        "tasks": [
            {
                **{k: v for k, v in t.items() if k not in {"source", "rubric"}},
                "rubric": {
                    "criteria": [
                        {k: v for k, v in criterion.items() if k != "binding"}
                        for criterion in t["rubric"]["criteria"]
                    ]
                }
                if t["rubric"]
                else None,
            }
            for t in content["tasks"]
        ],
    }


def get(c, identifier):
    row = one(c, "SELECT * FROM anvil.benchmark_task_groups WHERE id=%s", (identifier,))
    if not row:
        raise HTTPException(404, "Task Group not found")
    return row


def store(c, project, user, content, policies):
    source = content["source_project"]
    fingerprint = digest(content)
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    previous = one(
        c,
        "SELECT * FROM anvil.benchmark_task_groups WHERE source_project_id=%s AND source_version=%s",
        (source["id"], source["version"]),
    )
    if previous and previous["content_sha256"] != fingerprint:
        raise HTTPException(
            409, "Source Project/version already exists with different bytes; export a new version"
        )
    identifier = previous["id"] if previous else uid()
    if not previous:
        c.execute(
            "INSERT INTO anvil.benchmark_task_groups(id,project_id,source_project_id,source_version,name,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                identifier,
                project,
                source["id"],
                source["version"],
                source["name"],
                Jsonb(content),
                fingerprint,
                user,
            ),
        )
        audit(
            c,
            project,
            user,
            "benchmark.project_imported",
            identifier,
            {
                "source_project_id": source["id"],
                "source_version": source["version"],
                "content_sha256": fingerprint,
            },
        )
    if policies:
        ph = digest(policies)
        old_sets = c.execute(
            "SELECT content FROM anvil.benchmark_policy_sets WHERE task_group_id=%s", (identifier,)
        ).fetchall()
        for old in old_sets:
            before = {
                (p["policy_id"], p["version"]): p for p in old["content"]["manifest"]["policies"]
            }
            for p in policies["manifest"]["policies"]:
                if (p["policy_id"], p["version"]) in before:
                    old_sources = {s["id"]: s for s in old["content"]["manifest"]["sources"]}
                    new_sources = {s["id"]: s for s in policies["manifest"]["sources"]}
                    if before[(p["policy_id"], p["version"])] != p or old_sources.get(
                        p["source_id"]
                    ) != new_sources.get(p["source_id"]):
                        raise HTTPException(
                            409, "Policy identity/version changed; create a new policy version"
                        )
        if not one(
            c,
            "SELECT id FROM anvil.benchmark_policy_sets WHERE task_group_id=%s AND content_sha256=%s",
            (identifier, ph),
        ):
            c.execute(
                "INSERT INTO anvil.benchmark_policy_sets(id,project_id,task_group_id,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
                (uid(), project, identifier, Jsonb(policies), ph, user),
            )
    return public_group(get(c, identifier))
