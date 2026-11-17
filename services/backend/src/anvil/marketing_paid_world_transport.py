"""Parent-enforced world RPC time/byte bounds; no network IO in this process."""

import math
import os
import selectors
import subprocess
import sys
from pathlib import Path
from time import monotonic

REQUEST_LIMIT = 98304
RESPONSE_LIMIT = 131072
# Maximum reserve WITHIN the caller's deadline, never an added grace period.
# Actual process/pipe cleanup still requires independent runtime qualification.
CLEANUP_SECONDS = 5


def _pump(process, raw, deadline):
    offset, chunks, size, eof = 0, [], 0, False
    os.set_blocking(process.stdin.fileno(), False)
    os.set_blocking(process.stdout.fileno(), False)
    with selectors.DefaultSelector() as selected:
        selected.register(process.stdin, selectors.EVENT_WRITE)
        selected.register(process.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("marketing_world_absolute_rpc_deadline")
            code = process.poll()
            if eof and code is not None:
                if code != 0 or not size:
                    raise RuntimeError("marketing_world_child_failed_or_outcome_unknown")
                return b"".join(chunks)
            for key, event in selected.select(min(remaining, 0.1)):
                if monotonic() >= deadline:
                    raise TimeoutError("marketing_world_absolute_rpc_deadline")
                if key.fileobj is process.stdin:
                    try:
                        offset += os.write(process.stdin.fileno(), raw[offset : offset + 16384])
                    except BlockingIOError:
                        continue
                    if offset == len(raw):
                        selected.unregister(process.stdin)
                        process.stdin.close()
                elif key.fileobj is process.stdout:
                    try:
                        chunk = os.read(process.stdout.fileno(), 4096)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selected.unregister(process.stdout)
                        eof = True
                    else:
                        size += len(chunk)
                        if size > RESPONSE_LIMIT:
                            raise ValueError("marketing_world_response_limit")
                        chunks.append(chunk)


def execute(raw, *, absolute_deadline, request_seconds):
    """One child, no retry, one deadline captured before spawn.

    IO elapsed time is enforced only after synchronous Popen returns. A blocked
    spawn/exec handshake still needs an independently qualified outer supervisor
    before this path may be admitted. The helper shares the native operation's
    process group. Independent native
    lifecycle/recovery must also kill that group after parent death. Checks here
    do not establish process/image/runtime qualification. Up to five seconds
    (at most half the remaining interval) is reserved INSIDE this call's original
    deadline for owned-child cleanup. Unproved cleanup remains Unknown and grants
    no new time; a blocking spawn still needs the outer qualified supervisor.
    """
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= REQUEST_LIMIT
        or type(absolute_deadline) not in (int, float)
        or not math.isfinite(absolute_deadline)
        or type(request_seconds) is not int
        or not 1 <= request_seconds <= 600
    ):
        raise ValueError("Exact bounded private world transport required")
    deadline = min(absolute_deadline, monotonic() + request_seconds)
    remaining = deadline - monotonic()
    if remaining < 1 or remaining > 600:
        raise TimeoutError("marketing_world_transport_deadline")
    work_deadline = deadline - min(CLEANUP_SECONDS, remaining / 2)
    helper = Path(__file__).with_name("marketing_paid_world_rpc.py")
    if helper.is_symlink() or not helper.is_file():
        raise RuntimeError("marketing_world_fixed_helper_missing")
    work_seconds = work_deadline - monotonic()
    if work_seconds <= 0:
        raise TimeoutError("marketing_world_no_rpc_phase_remaining")
    process = subprocess.Popen(
        [sys.executable, "-I", "-S", str(helper), str(work_seconds)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=False,
        env={"LANG": "C.UTF-8"},
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
            raise RuntimeError("marketing_world_owned_child_cleanup_unknown_no_retry") from None
    if monotonic() >= deadline:
        raise TimeoutError("marketing_world_rpc_deadline_after_cleanup")
    return result
