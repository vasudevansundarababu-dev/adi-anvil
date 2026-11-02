"""Bundle the shared golden contract and checked software evidence, never secrets/logs."""

import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path

from anvil.praxis_executable import parse
from anvil.praxis_export import parse_export

ROOT = Path(__file__).resolve().parents[1]


def package():
    source = ROOT / "contracts/praxis/golden-v3"
    report = json.loads((ROOT / "artifacts/test-runs/golden-v3-report.json").read_text())
    assert len(report["tasks"]) == 3 and all(
        len(t["harbor"]) == 3 and all(r["passed"] for r in t["harbor"]) for t in report["tasks"]
    )
    for path, result in zip(sorted(source.glob("*.export.json")), report["tasks"], strict=True):
        raw, envelope = parse_export(path.read_bytes())
        assert envelope.payload_sha256 == result["source_sha256"]
        task = parse(raw)
        assert task.task_id == result["task_id"]
    output = ROOT / "artifacts/golden-harbor-imports"
    output.mkdir(parents=True, exist_ok=True)
    files = {"golden-v3/" + p.name: p.read_bytes() for p in source.iterdir() if p.is_file()}
    files["task-v3.schema.json"] = (ROOT / "contracts/praxis/task-v3.schema.json").read_bytes()
    files["verification-report.json"] = (
        ROOT / "artifacts/test-runs/golden-v3-report.json"
    ).read_bytes()
    pipeline_report = ROOT / "artifacts/test-runs/import-pipeline-e2e.json"
    if pipeline_report.is_file():
        pipeline = json.loads(pipeline_report.read_text())
        assert len(pipeline) == 3 and all(
            t["evaluation"]["trials"] == 6
            and t["notebook_successor"] == "ready"
            and not t["model_performance"]
            for t in pipeline
        )
        files["application-pipeline-report.json"] = pipeline_report.read_bytes()
    for path in (ROOT / "fixtures/executable-import").rglob("*"):
        if path.is_file() and path.suffix != ".pyc" and "__pycache__" not in path.parts:
            files[
                "reference-fixtures/" + str(path.relative_to(ROOT / "fixtures/executable-import"))
            ] = path.read_bytes()
    manifest = {
        "schema_version": "anvil.golden-delivery.v1",
        "origin": "synthetic_software_verification_only",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
        "image_reference": task.environment.model_dump(),
        "image_delivery": "separate local Docker archive; not published to a registry",
    }
    files["MANIFEST.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    archive = output / "praxis-anvil-golden-v3.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as stream:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            stream.writestr(info, data)
    for path in source.glob("*.export.json"):
        (output / path.name).write_bytes(path.read_bytes())
    print(
        json.dumps(
            {
                "archive": str(archive),
                "files": len(files),
                "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        )
    )
    return output, task.environment.image_reference


if __name__ == "__main__":
    output, image = package()
    host = os.environ.get("ANVIL_HARBOR_DOCKER_HOST", "unix:///var/run/docker.sock")
    if not host.startswith("unix://"):
        raise RuntimeError("Golden image export requires an explicit local Unix Docker socket")
    subprocess.run(
        [
            "docker",
            "--host",
            host,
            "image",
            "save",
            "-o",
            str(output / "anvil-golden-tools-1.0.0.tar"),
            image,
        ],
        check=True,
    )
    print("Supplied image archived without registry push")
    delivered = sorted(output.glob("*.export.json")) + [
        output / "praxis-anvil-golden-v3.zip",
        output / "anvil-golden-tools-1.0.0.tar",
    ]
    (output / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in delivered
        )
    )
