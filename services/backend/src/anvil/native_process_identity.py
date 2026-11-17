"""Fail-closed kernel domain for native child PID interpretation; Linux only."""

import os
import re
from pathlib import Path
from uuid import UUID


def process_domain(proc_root=Path("/proc")):
    try:
        boot = (proc_root / "sys/kernel/random/boot_id").read_text().strip()
        if str(UUID(boot)) != boot:
            raise ValueError("noncanonical boot identity")
        # A foreign procfs mount must not hide/reinterpret namespace-local PIDs.
        if int((proc_root / "self/stat").read_text().split(" ", 1)[0]) != os.getpid():
            raise ValueError("foreign process visibility")
        namespace = proc_root / "self/ns/pid"
        link = os.readlink(namespace)
        match = re.fullmatch(r"pid:\[([1-9][0-9]*)\]", link)
        info = namespace.stat()
        init = (proc_root / "1/stat").read_text()
        init_fields = init.rpartition(") ")[2].split()
        if (
            not match
            or info.st_ino != int(match.group(1))
            or info.st_dev < 0
            or os.readlink(proc_root / "self/ns/pid_for_children") != link
            or os.readlink(proc_root / "1/ns/pid") != link
            or init.split(" ", 1)[0] != "1"
            or len(init_fields) < 20
            or not init_fields[19].isdigit()
            or int(init_fields[19]) <= 0
        ):
            raise ValueError("ambiguous PID namespace")
        return {
            "schema": "anvil.native-process-domain.v1",
            "boot_id": boot,
            "pid_namespace": link,
            "pid_namespace_device": info.st_dev,
            "pid_namespace_inode": info.st_ino,
            "namespace_init_start_ticks": init_fields[19],
        }
    except (OSError, ValueError, IndexError):
        raise RuntimeError("native_process_domain_unavailable") from None
