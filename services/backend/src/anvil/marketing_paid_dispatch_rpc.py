"""Fixed stdlib-only dispatch/readiness/prepare child; capabilities never logged."""

import http.client
import json
import math
import sys
from time import monotonic


def exchange(raw, seconds):
    if (type(raw) is not bytes or not 0 < len(raw) <= 98304
            or type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not 0 < seconds <= 600):
        raise ValueError("Bounded dispatch input required")
    envelope = json.loads(raw)
    if (type(envelope) is not dict or set(envelope) != {"operation", "request"}
            or envelope["operation"] not in {"dispatch", "readiness", "prepare"}
            or type(envelope["request"]) is not dict):
        raise ValueError("Fixed dispatch/readiness envelope required")
    body = json.dumps(envelope["request"], allow_nan=False, separators=(",", ":")).encode()
    deadline = monotonic() + seconds
    connection = http.client.HTTPConnection("api", 8200, timeout=seconds)
    try:
        connection.request(
            "POST", "/internal/v1/worker-dispatch/" + envelope["operation"],
            body=body, headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError("Dispatch outcome unavailable")
        chunks, size = [], 0
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("Dispatch response deadline")
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            chunk = response.read(4096)
            if monotonic() >= deadline:
                raise TimeoutError("Dispatch response deadline")
            if not chunk:
                return b"".join(chunks)
            size += len(chunk)
            if size > 131072:
                raise ValueError("Dispatch response bound")
            chunks.append(chunk)
    finally:
        connection.close()


def main():
    if len(sys.argv) != 2:
        return 42
    try:
        raw = sys.stdin.buffer.read(98305)
        result = exchange(raw, float(sys.argv[1]))
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        return 42


if __name__ == "__main__":
    raise SystemExit(main())
