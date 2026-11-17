"""Fixed stdlib-only child for one private world RPC; never accepts a URL.

Private payload is stdin; stdout contains only a bounded successful public reply.
The parent owns the absolute deadline, including DNS, headers and slow streams.
"""

import http.client
import json
import math
import sys
from time import monotonic

REQUEST_LIMIT = 98304
RESPONSE_LIMIT = 131072


def exchange(raw, seconds):
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= REQUEST_LIMIT
        or type(seconds) not in (int, float)
        or not math.isfinite(seconds)
        or not 0 < seconds <= 600
    ):
        raise ValueError("Bounded fixed world request required")
    if not isinstance(json.loads(raw), dict):
        raise ValueError("World request object required")
    deadline = monotonic() + seconds
    connection = http.client.HTTPConnection("api", 8200, timeout=seconds)
    try:
        connection.request(
            "POST",
            "/internal/v1/worker-dispatch/world",
            body=raw,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError("World request unavailable")
        chunks, size = [], 0
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("World request deadline")
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            chunk = response.read(4096)
            if monotonic() >= deadline:
                raise TimeoutError("World response deadline")
            if not chunk:
                break
            size += len(chunk)
            if size > RESPONSE_LIMIT:
                raise ValueError("World response bound")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        connection.close()


def main():
    if len(sys.argv) != 2:
        return 42
    try:
        seconds = float(sys.argv[1])
        raw = sys.stdin.buffer.read(REQUEST_LIMIT + 1)
        result = exchange(raw, seconds)
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        return 42  # No input, response, traceback or lease enters logs.


if __name__ == "__main__":
    raise SystemExit(main())
