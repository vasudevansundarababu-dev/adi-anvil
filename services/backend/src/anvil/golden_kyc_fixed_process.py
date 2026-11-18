"""Linux fixed-child cleanup while the unreaped leader still owns its PGID."""

import os
import signal
import time
from pathlib import Path


def stop(child):
    owner = getattr(child, "_anvil_owned_group", None)
    if owner is None:
        raise RuntimeError("Unreaped fixed child ownership required")
    if not owner.held:
        return
    if not hasattr(child, "_anvil_cleanup_ends"):
        child._anvil_cleanup_ends = time.monotonic() + 2
    ends = child._anvil_cleanup_ends
    if time.monotonic() >= ends:
        raise RuntimeError("Fixed group cleanup deadline exhausted")
    # Holding the unreaped session leader prevents PGID reuse. No post-reap
    # numeric group signal is permitted, including on the normal exit path.
    owner.signal(signal.SIGKILL)
    while True:
        live = False
        for proc in Path("/proc").iterdir():
            if time.monotonic() >= ends:
                raise RuntimeError("Fixed group termination unconfirmed")
            if not proc.name.isdigit():
                continue
            try:
                fields = (proc / "stat").read_text().rpartition(") ")[2].split()
                if len(fields) < 20:
                    raise RuntimeError("Fixed process observation incomplete")
                if fields[2] == str(child.pid) and fields[3] == str(child.pid) and fields[0] != "Z":
                    if proc.stat().st_uid != os.geteuid():
                        raise RuntimeError("Fixed process ownership changed")
                    live = True
            except FileNotFoundError:
                continue
        if not live:
            break
        time.sleep(min(0.01, max(0, ends - time.monotonic())))
    owner.reap(ends - time.monotonic())
