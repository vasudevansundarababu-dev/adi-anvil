"""Reproduce versioned unsigned software metadata; never rewrite historical v1.

No containers, inference, signing keys or source/rights approvals are created.
"""

import argparse
import hashlib
import json
from pathlib import Path

import rfc8785

from anvil.benchmark_bundle import Manifest
from anvil.native_image_profile import IMAGE

HERE = Path(__file__).resolve().parent
LEGACY_SHA256 = "0ba5dcced76a7865486a302d11976229642b254054ce717f9acd81ecc262e290"


def content():
    original = HERE / "fictional-points-v1"
    manifest = json.loads((original / "manifest.json").read_bytes())
    if hashlib.sha256(rfc8785.dumps(manifest)).hexdigest() != LEGACY_SHA256:
        raise ValueError("Historical fixture changed")
    payloads = {}
    for entry in manifest["files"]:
        path = original / entry["path"]
        if path.is_symlink() or not path.resolve().is_relative_to(original.resolve()):
            raise ValueError("Historical fixture path escaped")
        raw = path.read_bytes()
        if len(raw) != entry["byte_size"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Historical fixture bytes changed")
        payloads[entry["path"]] = raw
    manifest["bank"].update(version="1.0.1", revision="fictional-revision-2-security-image")
    manifest["bank"]["title"] = (
        "Fictional arithmetic security-image successor — software tests only"
    )
    manifest["exporter"]["version"] = "1.0.1"
    manifest["exported_at"] = "2026-11-11T00:00:00Z"
    for task in manifest["tasks"]:
        task.update(version="1.0.1", revision=task["id"] + "-revision-2-security-image")
        task["environment"].update(
            image_reference=IMAGE, oci_manifest_digest=IMAGE.split("@", 1)[1]
        )
        task["evaluator_requirement"].update(version="1.0.1", image_digest=IMAGE.split("@", 1)[1])
    Manifest.model_validate(manifest)
    payloads["manifest.json"] = (
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode()
    return payloads


def build(destination):
    destination = Path(destination)
    if destination.resolve() == (HERE / "fictional-points-v1").resolve():
        raise ValueError("Historical fixture is immutable")
    for relative, raw in content().items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("Refusing to overwrite different successor bytes")
        path.write_bytes(raw)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=HERE / "fictional-points-v2")
    build(parser.parse_args().output_dir)
