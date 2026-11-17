"""Offline utility: python -m anvil.dataset_export_validate package.zip."""

import argparse
import json
from pathlib import Path

from anvil.dataset_export_contract import validate_archive


def main():
    parser = argparse.ArgumentParser(
        description="Validate a Golden evaluator-backed export without calls, SQL or imports"
    )
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    with args.package.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    result, _ = validate_archive(raw)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
