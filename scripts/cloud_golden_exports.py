"""Create explicit cloud-image successors; never rewrite original golden source records."""

import argparse
import hashlib
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9.-]+/[A-Za-z0-9_./-]+@sha256:[0-9a-f]{64}", args.image):
        raise SystemExit("Use the verified registry image@sha256:digest")
    root = Path(__file__).resolve().parents[1]
    target = root / "contracts/praxis/golden-v3-cloud"
    target.mkdir(exist_ok=True)
    for path in sorted((root / "contracts/praxis/golden-v3").glob("*.export.json")):
        envelope = json.loads(path.read_text())
        payload = json.loads(envelope["payload_json"])
        payload["task_version"] = "1.1.0"
        payload["revision_id"] += "-cloud-1"
        payload["environment"].update(
            image_reference=args.image,
            digest=args.image.rsplit("@", 1)[1],
            digest_kind="oci_manifest",
        )
        raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        sha = hashlib.sha256(raw.encode()).hexdigest()
        envelope.update(payload_json=raw, payload_sha256=sha)
        envelope["source"]["record_hash"] = sha
        (target / path.name).write_text(json.dumps(envelope, indent=2) + "\n")
    print("Created three cloud-image successor exports; original versions unchanged.")


if __name__ == "__main__":
    main()
