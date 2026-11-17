"""Offline, aggregate Golden export validation. No SQL, evaluator execution or calls."""

import hashlib
import io
import json
import re
import stat
import zlib
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

from pydantic import BaseModel, ConfigDict, Field, ValidationError

VERSION = "anvil.evaluator-task-export.v1"
PROFILE_ID = "golden-kyc-run-evidence-v1"
ASSETS = Path(__file__).with_name("export_contract_assets")
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")]
Sha = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafePath = Annotated[
    str,
    Field(
        max_length=240, pattern=r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*(/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*$"
    ),
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Profile(Model):
    id: Literal[PROFILE_ID]
    path: Literal["evaluation-profile.json"]
    sha256: Sha


class Environment(Model):
    key: Literal["golden-kyc-v1"]
    version: Identifier
    source_sha256: Sha
    logical_environment_sha256: Sha
    data_sha256: Sha
    policy_sha256: Sha
    seed: int
    runtime: Literal["golden-kyc-postgres-v1"]
    openenv: Literal["0.12.0"]
    harbor: Literal["0.25.0"]


class Task(Model):
    task_id: Identifier
    task_version: Identifier
    path: SafePath
    task_payload_sha256: Sha
    application_sha256: Sha
    profile_id: Literal[PROFILE_ID]


class Execution(Model):
    location: Literal["anvil_only"]
    paid_calls: Literal[False]
    origin: Literal["software_control_not_model"]
    model_performance: Literal[False]


class Manifest(Model):
    schema_version: Literal[VERSION]
    package_id: Identifier
    package_version: Identifier
    profile: Profile
    environment: Environment
    tasks: list[Task] = Field(min_length=1, max_length=200)
    execution: Execution


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    )


def pointer(parts):
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def json_object(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("non-finite number")

    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError("JSON object required")

    def depth(item, level=0):
        if level > 32:
            raise ValueError("nesting limit")
        for child in (
            item.values() if isinstance(item, dict) else item if isinstance(item, list) else ()
        ):
            depth(child, level + 1)

    depth(value)
    return value


@lru_cache(maxsize=1)
def trusted_profile():
    return json_object((ASSETS / "evaluation-profile.json").read_bytes())


def validate_files(files):
    """Return all independent detectable producer errors; never echo submitted values."""
    errors = []

    def error(code, path, message, fix, file="anvil-export.json"):
        item = {
            "code": code,
            "owner": "praxis",
            "file": file,
            "pointer": path,
            "message": message,
            "fix": fix,
            "retryable": False,
        }
        if item not in errors:
            errors.append(item)

    def parse(path):
        if path not in files:
            error(
                "PX_FILE_MISSING",
                "",
                "Declared file is missing.",
                "Include this declared file in the package.",
                path,
            )
            return None
        try:
            return json_object(files[path])
        except (ValueError, UnicodeError, RecursionError):
            error(
                "PX_JSON_INVALID",
                "",
                "File must contain bounded UTF-8 JSON with unique keys and finite values.",
                "Fix JSON syntax, duplicate keys, encoding or nesting before exporting.",
                path,
            )
            return None

    raw = parse("anvil-export.json")
    profile = parse("evaluation-profile.json")
    expected = trusted_profile()
    if (
        "evaluation-profile.json" in files
        and files["evaluation-profile.json"] != (ASSETS / "evaluation-profile.json").read_bytes()
    ):
        error(
            "PX_PROFILE_CHANGED",
            "",
            "Profile file bytes differ from the published profile.",
            "Use the published profile file without changing content, formatting or encoding.",
            "evaluation-profile.json",
        )
    if profile is not None:

        def compare(got, want, parts=()):
            if type(got) is not type(want):
                error(
                    "PX_PROFILE_CHANGED",
                    pointer(parts),
                    "Frozen evaluator profile differs.",
                    "Use the exact Anvil-published profile; do not add output fields or evaluator code.",
                    "evaluation-profile.json",
                )
            elif isinstance(want, dict):
                for key in sorted(set(got) | set(want)):
                    if key not in got or key not in want:
                        error(
                            "PX_PROFILE_CHANGED",
                            pointer((*parts, key)),
                            "Frozen evaluator profile property differs.",
                            "Restore the published profile property.",
                            "evaluation-profile.json",
                        )
                    else:
                        compare(got[key], want[key], (*parts, key))
            elif isinstance(want, list):
                if len(got) != len(want):
                    error(
                        "PX_PROFILE_CHANGED",
                        pointer(parts),
                        "Frozen evaluator list length differs.",
                        "Preserve every published check in its original order.",
                        "evaluation-profile.json",
                    )
                for index, (a, b) in enumerate(zip(got, want)):
                    compare(a, b, (*parts, index))
            elif got != want:
                error(
                    "PX_PROFILE_CHANGED",
                    pointer(parts),
                    "Frozen evaluator profile value differs.",
                    "Restore the exact published profile value.",
                    "evaluation-profile.json",
                )

        compare(profile, expected)
    manifest = None
    if raw is not None:
        try:
            manifest = Manifest.model_validate(raw)
        except ValidationError as exc:
            for item in exc.errors():
                error(
                    "PX_MANIFEST_SCHEMA",
                    pointer(item["loc"]),
                    item["msg"],
                    "Use the published schema: correct type/value, include required fields and remove unknown fields.",
                )
    if (
        raw is not None
        and isinstance(raw.get("profile"), dict)
        and "evaluation-profile.json" in files
    ):
        if raw["profile"].get("sha256") != sha(files["evaluation-profile.json"]):
            error(
                "PX_FILE_HASH",
                "/profile/sha256",
                "Profile raw-byte hash does not match.",
                "Compute SHA256 of the exact published profile file bytes.",
            )
    if raw is not None and isinstance(raw.get("environment"), dict):
        for key, value in expected["environment"].items():
            if (
                type(raw["environment"].get(key)) is not type(value)
                or raw["environment"].get(key) != value
            ):
                error(
                    "PX_ENVIRONMENT_REFERENCE",
                    "/environment/" + key,
                    "Published environment reference was changed or omitted.",
                    "Copy this reference from the Anvil-published profile. Anvil provisions the environment; do not create one in Praxis.",
                )
    if raw is not None and isinstance(raw.get("execution"), dict):
        for key in ("paid_calls", "model_performance"):
            if raw["execution"].get(key) is not False:
                error(
                    "PX_MANIFEST_SCHEMA",
                    "/execution/" + key,
                    "This flag must be the JSON Boolean false.",
                    "Use false, not a number, string or enabled paid/model flag.",
                )
    entries = raw.get("tasks", []) if raw else []
    entries = entries[:200] if isinstance(entries, list) else []
    trusted = {t["task_id"]: t for t in expected["trusted_tasks"]}
    declared, ids, paths = {"anvil-export.json", "evaluation-profile.json"}, set(), set()
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            continue
        prefix = f"/tasks/{index}"
        tid, path = item.get("task_id"), item.get("path")
        if isinstance(tid, str):
            if tid in ids:
                error(
                    "PX_TASK_DUPLICATE",
                    prefix + "/task_id",
                    "Task ID is repeated.",
                    "Export each selected task ID once.",
                )
            ids.add(tid)
        if not isinstance(path, str) or not re.fullmatch(
            r"[A-Za-z0-9_-][A-Za-z0-9_.-]*(/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*", path
        ):
            continue
        if path.casefold() in paths or path.casefold() in {
            "anvil-export.json",
            "evaluation-profile.json",
        }:
            error(
                "PX_PATH_DUPLICATE",
                prefix + "/path",
                "Task path conflicts with another file.",
                "Use a unique relative task path, ignoring case.",
            )
        paths.add(path.casefold())
        declared.add(path)
        source = parse(path)
        target = trusted.get(tid) if isinstance(tid, str) else None
        if not target:
            error(
                "PX_TASK_UNKNOWN",
                prefix + "/task_id",
                "Task is not in this published Golden profile.",
                "Select a published Golden task; custom tasks require a separately supported profile.",
            )
            continue
        for key, value in target.items():
            if item.get(key) != value:
                error(
                    "PX_TASK_REFERENCE",
                    prefix + "/" + key,
                    "Frozen task reference differs.",
                    "Restore this task's exact ID/version/hash from the published profile.",
                )
        if source is not None:
            if digest(source) != target["task_payload_sha256"]:
                error(
                    "PX_TASK_PAYLOAD",
                    "",
                    "Frozen task source changed.",
                    "Export the original task source object, including actor assignment; do not wrap it as a legacy output-field task.",
                    path,
                )
    for path in sorted(set(files) - declared):
        error(
            "PX_UNDECLARED_FILE",
            "",
            "File is not declared in this contract.",
            "Remove this file. Keep authoring references, private material and executable code outside the export.",
            path,
        )
    return {
        "schema_version": "anvil.dataset-export-validation.v1",
        "contract": VERSION,
        "valid": not errors,
        "status": "export_valid" if not errors else "export_invalid",
        "errors": errors,
        "error_count": len(errors),
        "errors_truncated": False,
        "anvil_requirements": [],
        "review_gates": [],
        "paid_calls": False,
        "package_sha256": digest({p: sha(v) for p, v in sorted(files.items())}),
        "task_count": len(entries),
        "criterion_count": 20,
        "evaluator_requirements": 50,
    }, manifest


def validate_archive(raw):
    """Bounded archive parsing in memory, never extraction, imports or execution."""
    try:
        if len(raw) > 1024 * 1024:
            raise ValueError("compressed limit")
        files, names, total = {}, set(), 0
        with ZipFile(io.BytesIO(raw)) as archive:
            if len(archive.infolist()) > 1200:
                raise ValueError("entry limit")
            for item in archive.infolist():
                total += item.file_size
                if (
                    total > 30 * 1024 * 1024
                    or item.file_size > 10 * 1024 * 1024
                    or len(item.filename) > 240
                    or not re.fullmatch(
                        r"[A-Za-z0-9_-][A-Za-z0-9_.-]*(/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*",
                        item.filename,
                    )
                    or item.filename.casefold() in names
                    or stat.S_ISLNK(item.external_attr >> 16)
                    or item.flag_bits & 1
                    or item.compress_type not in (ZIP_STORED, ZIP_DEFLATED)
                ):
                    raise ValueError("unsafe archive")
                names.add(item.filename.casefold())
                with archive.open(item) as stream:
                    data = stream.read(item.file_size + 1)
                if len(data) != item.file_size:
                    raise ValueError("entry length")
                files[item.filename] = data
    except (ValueError, OSError, EOFError, RuntimeError, BadZipFile, zlib.error):
        return {
            "schema_version": "anvil.dataset-export-validation.v1",
            "contract": VERSION,
            "valid": False,
            "status": "export_invalid",
            "error_count": 1,
            "errors_truncated": False,
            "errors": [
                {
                    "code": "PX_ARCHIVE_INVALID",
                    "owner": "praxis",
                    "file": "",
                    "pointer": "",
                    "message": "Archive failed bounded ZIP safety or integrity checks.",
                    "fix": "Use a valid ZIP, STORE/DEFLATE only, no directory/symlink/encrypted or duplicate entries; use safe relative paths and stay within1MiB upload/30MiB expanded/10MiB per file/1200 entries.",
                    "retryable": False,
                }
            ],
            "anvil_requirements": [],
            "review_gates": [],
            "paid_calls": False,
        }, None
    return validate_files(files)
