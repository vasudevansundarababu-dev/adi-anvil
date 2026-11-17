"""Offline generic validation against explicit template files; no readiness authority."""

import argparse
import json
from pathlib import Path

from anvil.praxis_generic_contract import TemplateSpec, digest, load
from anvil.praxis_generic_export import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--template", action="append", type=Path, default=[])
    args = parser.parse_args()
    templates = {}
    for filename in args.template:
        raw = load(filename.read_bytes())
        spec = TemplateSpec.model_validate(raw)
        templates[(spec.template_id, spec.version, digest(raw))] = raw

    def lookup(ref):
        raw = templates.get((ref.id, ref.version, ref.sha256))
        if raw is None:
            return None
        return {"row": {"spec": raw}, "qualified": False, "revoked": False}

    result, _ = validate(args.package.read_bytes(), lookup)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] is True else 1 if result["valid"] is False else 2


if __name__ == "__main__":
    raise SystemExit(main())
