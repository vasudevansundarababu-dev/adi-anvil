"""Bounded stdin/stdout validator using the independently locked Harbor model."""

import importlib.metadata
import json
import sys

from harbor.models.trajectories import Trajectory


def main():
    if importlib.metadata.version("harbor") != "0.25.0":
        raise ValueError("Pinned Harbor version is required")
    raw = sys.stdin.buffer.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("ATIF bound")
    value = json.loads(raw)
    checked = Trajectory.model_validate(value).to_json_dict()
    sys.stdout.write(json.dumps(checked, sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
