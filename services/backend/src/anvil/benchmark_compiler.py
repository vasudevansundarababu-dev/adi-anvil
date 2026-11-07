"""Deterministic actor-only SME packages and regular-file output sealing."""

import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from pathlib import Path

import rfc8785

from anvil.benchmark_archive import validate_archive
from anvil.benchmark_bundle import actor_view, canonical_path
from anvil.harbor_package import HARBOR_VERSION

COMPILER_VERSION = "anvil-sme-artifact-1.0.1"
FIXTURE_IMAGE = "python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e"


@dataclass(frozen=True)
class ReviewedEvaluator:
    registry_id: str
    version: str
    implementation_sha256: str
    image_digest: str
    policy_sha256: str
    tool_sha256: str
    bank_id: str
    manifest_sha256: str
    source_classification: str
    review_reference: str


def fixture_binding():
    return ReviewedEvaluator(
        "fictional-arithmetic-unreviewed",
        "1.0.0",
        "87cf1f67287e96d2e7f581b5aabe52243b5c29f6f380a946a81fd91aced7bf4b",
        FIXTURE_IMAGE.split("@", 1)[1],
        "f1ddb919481f83200e93e4e2a13346b8a7603c8a38a0eb155d03a2396ba43d46",
        "a2f4197652df6a03503b18b1c20fa195f5cd596c47b450322ac958aab1af138d",
        "fictional-points",
        "0ba5dcced76a7865486a302d11976229642b254054ce717f9acd81ecc262e290",
        "original_synthetic_fixture",
        "human-native-fictional-scope-2026-11-07; source08121a2; software-only",
    )


def _hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def _owned_directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError("Staging requires an owner-only regular directory")


def _binding(parsed, task, binding):
    manifest = parsed.manifest
    if (
        not binding.review_reference
        or binding.source_classification != manifest.source.classification
        or binding.bank_id != manifest.bank.id
        or binding.manifest_sha256 != parsed.canonical_sha256
    ):
        raise ValueError("Reviewed evaluator source scope mismatch")
    required = task.evaluator_requirement.model_dump()
    if any(getattr(binding, key) != value for key, value in required.items()):
        raise ValueError("Reviewed evaluator digest/version mismatch")
    if (
        task.environment.image_reference != FIXTURE_IMAGE
        or task.environment.oci_manifest_digest != binding.image_digest
    ):
        raise ValueError("Environment is not approved for this local fixture profile")
    if (
        task.environment.cpus > 1
        or task.environment.memory_mb > 2048
        or task.environment.pids_limit > 64
    ):
        raise ValueError("Environment exceeds initial SME installation limits")
    members = {f.path: f for f in manifest.files}
    for server in task.tools:
        script = f"runtime_pack/{task.id}/tool-server.py"
        if (
            server.command != ["python", "inputs/tool-server.py"]
            or script not in members
            or members[script].sha256 != binding.tool_sha256
        ):
            raise ValueError("Tool implementation is not reviewed for this fixture profile")


@dataclass(frozen=True)
class CompiledTask:
    archive_sha256: str
    byte_size: int
    binding_sha256: str
    bindings: dict


def _compose(task):
    return json.dumps(
        {
            "services": {
                "main": {
                    "image": task.environment.image_reference,
                    "pull_policy": "never",
                    "network_mode": "none",
                    "user": "10001:10001",
                    "working_dir": "/workspace",
                    "read_only": True,
                    "cap_drop": ["ALL"],
                    "security_opt": ["no-new-privileges:true"],
                    "pids_limit": task.environment.pids_limit,
                    "cpus": task.environment.cpus,
                    "mem_limit": f"{task.environment.memory_mb}m",
                    "memswap_limit": f"{task.environment.memory_mb}m",
                    "environment": {"HOME": "/tmp/home", "PYTHONDONTWRITEBYTECODE": "1"},
                    "tmpfs": [
                        "/tmp:rw,nosuid,nodev,noexec,size=32m,uid=10001,gid=10001",
                        "/workspace/output:rw,nosuid,nodev,noexec,size=16m,uid=10001,gid=10001",
                    ],
                    "volumes": [
                        {
                            "type": "bind",
                            "source": "./actor/runtime_pack/" + task.id,
                            "target": "/workspace/inputs",
                            "read_only": True,
                        }
                    ],
                }
            }
        }
    ).encode()


def compile_task(source, receipt, task_id, binding, destination: Path, *, signers, now):
    if receipt.signature.status != "verified":
        raise ValueError("Verified source required; compilation cannot approve quarantine")
    manifest = receipt.parsed.manifest
    task = next((task for task in manifest.tasks if task.id == task_id), None)
    if task is None:
        raise ValueError("Unknown task")
    _binding(receipt.parsed, task, binding)
    destination = Path(destination)
    _owned_directory(destination.parent)
    projection = actor_view(manifest, task.id)
    actor_hash = hashlib.sha256(rfc8785.dumps(projection)).hexdigest()
    bindings = {
        "compiler": COMPILER_VERSION,
        "harbor": HARBOR_VERSION,
        "archive_sha256": receipt.archive_sha256,
        "manifest_sha256": receipt.parsed.canonical_sha256,
        "actor_sha256": actor_hash,
        "task_id": task.id,
        "task_version": task.version,
        "task_revision": task.revision,
        "environment": task.environment.model_dump(),
        "tools": [tool.model_dump() for tool in task.tools],
        "outputs": [out.model_dump() for out in task.outputs],
        "private_files": [
            file.model_dump()
            for file in manifest.files
            if file.path.startswith(f"eval_pack/{task.id}/")
        ],
        "evaluator": asdict(binding),
    }
    binding_hash = hashlib.sha256(rfc8785.dumps(bindings)).hexdigest()
    with tempfile.TemporaryDirectory(prefix=".compile-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        with ExitStack() as stack:
            sinks = {}
            for file in projection["files"]:
                name = file["path"]
                path = stage / "environment/actor" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                sinks[name] = stack.enter_context(path.open("xb"))
            current = validate_archive(source, signers=signers, now=now, _actor_sinks=sinks)
            if (
                current.signature.status != "verified"
                or current.archive_sha256 != receipt.archive_sha256
                or current.parsed.canonical_sha256 != receipt.parsed.canonical_sha256
            ):
                raise ValueError("Staged source changed or trust is no longer valid")
        generated = {
            "task.toml": (
                'schema_version = "1.4"\n[metadata]\norigin = "original_synthetic_fixture"\ncompiler = '
                + json.dumps(COMPILER_VERSION)
                + "\n[agent]\ntimeout_sec = "
                + str(task.timeout_seconds)
                + '.0\nuser = "10001"\n[verifier]\ntimeout_sec = 60.0\nuser = "10001"\nnetwork_mode = "no-network"\nenvironment_mode = "separate"\n[verifier.environment]\ndocker_image = '
                + json.dumps(task.environment.image_reference)
                + '\ncpus = 1\nmemory_mb = 2048\nnetwork_mode = "no-network"\n[environment]\ndocker_image = '
                + json.dumps(task.environment.image_reference)
                + "\nbuild_timeout_sec = 60.0\ncpus = "
                + str(task.environment.cpus)
                + "\nmemory_mb = "
                + str(task.environment.memory_mb)
                + '\nnetwork_mode = "no-network"\n'
            ).encode(),
            "instruction.md": (
                "# SME artifact task — original software fixture\n\nRead /workspace/inputs/prompt.md and actor assets. Write declared deliverables under /workspace/output.\n"
            ).encode(),
            "environment/docker-compose.yaml": _compose(task),
            "actor.json": rfc8785.dumps(projection),
            "tests/test.sh": b"#!/bin/sh\nexit 78\n",
        }
        for name, data in generated.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        package = stage / "package.zip"
        files = sorted(path for path in stage.rglob("*") if path.is_file())
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_STORED) as archive:
            for path in files:
                name = path.relative_to(stage).as_posix()
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.external_attr = 0o100444 << 16
                with path.open("rb") as incoming, archive.open(info, "w") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, length=65536)
        os.chmod(package, 0o600)
        archive_hash, size = _hash(package), package.stat().st_size
        os.link(package, destination, follow_symlinks=False)
    return CompiledTask(archive_hash, size, binding_hash, bindings)


@dataclass(frozen=True)
class SealedFile:
    path: str
    sha256: str
    byte_size: int


@dataclass(frozen=True)
class SealedOutputs:
    files: tuple[SealedFile, ...]
    missing: tuple[str, ...]
    manifest_sha256: str


def seal_outputs(source: Path, destination: Path, outputs) -> SealedOutputs:
    source, destination = Path(source), Path(destination)
    _owned_directory(destination.parent)
    files, missing = [], []
    try:
        with (
            ExitStack() as stack,
            tempfile.TemporaryDirectory(prefix=".seal-", dir=destination.parent) as temporary,
        ):
            root = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, root)
            stage = Path(temporary)
            for output in sorted(outputs, key=lambda out: out.path):
                canonical_path(output.path)
                descriptors = []
                parent = root
                try:
                    for part in output.path.split("/")[:-1]:
                        parent = os.open(
                            part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                        )
                        descriptors.append(parent)
                    descriptor = os.open(
                        output.path.split("/")[-1],
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=parent,
                    )
                except FileNotFoundError:
                    missing.append(output.path)
                    continue
                finally:
                    for owned in reversed(descriptors):
                        os.close(owned)
                with os.fdopen(descriptor, "rb") as incoming:
                    info = os.fstat(incoming.fileno())
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or info.st_nlink != 1
                        or info.st_size > output.max_bytes
                    ):
                        raise ValueError("Output is aliased, nonregular or exceeds declared quota")
                    target = stage / output.path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    digest, size = hashlib.sha256(), 0
                    with target.open("xb") as outgoing:
                        while chunk := incoming.read(65536):
                            size += len(chunk)
                            if size > output.max_bytes:
                                raise ValueError("Output exceeds declared quota")
                            digest.update(chunk)
                            outgoing.write(chunk)
                        outgoing.flush()
                        os.fsync(outgoing.fileno())
                    after = os.fstat(incoming.fileno())
                    if size != info.st_size or (
                        info.st_size,
                        info.st_mtime_ns,
                        info.st_ctime_ns,
                    ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ValueError("Output changed during sealing")
                    target.chmod(0o400)
                    files.append(SealedFile(output.path, digest.hexdigest(), size))
            body = {"files": [asdict(file) for file in files], "missing": missing}
            manifest_bytes = rfc8785.dumps(body)
            (stage / "seal.json").write_bytes(manifest_bytes)
            (stage / "seal.json").chmod(0o400)
            os.chmod(stage, 0o500)
            os.rename(stage, destination)
        return SealedOutputs(
            tuple(files), tuple(missing), hashlib.sha256(manifest_bytes).hexdigest()
        )
    except OSError as exc:
        raise ValueError("Unsafe output path or sealed destination") from exc
