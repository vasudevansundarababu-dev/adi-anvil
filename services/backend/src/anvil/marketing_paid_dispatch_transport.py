"""One dispatch child under a parent deadline, not native runtime qualification.

Synchronous Popen, OS/pipe bounds and parent death require an independently
qualified outer supervisor. Killing a client never proves API/provider rollback.
"""

import math
import subprocess
import sys
from pathlib import Path
from time import monotonic

from anvil.marketing_paid_world_transport import CLEANUP_SECONDS, _pump
from anvil.praxis_generic_contract import canonical


def execute(operation, payload, *, absolute_deadline, request_seconds):
    if (operation not in {"dispatch", "readiness"} or type(payload) is not dict
            or type(absolute_deadline) not in (int, float)
            or not math.isfinite(absolute_deadline)
            or type(request_seconds) is not int or not 1 <= request_seconds <= 600):
        raise ValueError("Exact phased dispatch request required")
    raw = canonical({"operation": operation, "request": payload})
    if not 0 < len(raw) <= 98304:
        raise ValueError("Bounded dispatch envelope required")
    deadline = min(absolute_deadline, monotonic() + request_seconds)
    remaining = deadline - monotonic()
    if not 1 <= remaining <= 600:
        raise TimeoutError("No dispatch phase remaining")
    work_deadline = deadline - min(CLEANUP_SECONDS, remaining / 2)
    helper = Path(__file__).with_name("marketing_paid_dispatch_rpc.py")
    if helper.is_symlink() or not helper.is_file():
        raise RuntimeError("Fixed dispatch helper missing")
    work_seconds = work_deadline - monotonic()
    if work_seconds <= 0:
        raise TimeoutError("No dispatch work interval remaining")
    process = subprocess.Popen(
        [sys.executable, "-I", "-S", str(helper), str(work_seconds)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        close_fds=True, start_new_session=False, env={"LANG": "C.UTF-8"},
    )
    try:
        result = _pump(process, raw, work_deadline)
    finally:
        cleanup = True
        try:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=max(0, min(CLEANUP_SECONDS, deadline - monotonic())))
        except Exception:
            cleanup = False
        finally:
            for pipe in (process.stdin, process.stdout):
                try:
                    pipe.close()
                except Exception:
                    cleanup = False
        if not cleanup:
            raise RuntimeError("Dispatch child cleanup unknown; no retry") from None
    if monotonic() >= deadline:
        raise TimeoutError("Dispatch deadline after cleanup")
    return result
