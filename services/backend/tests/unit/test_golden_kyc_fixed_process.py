"""Actual Linux process cleanup controls, not installed native qualification."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from anvil.golden_kyc_fixed_process import stop
from anvil.owned_process_group import UnreapedProcessGroup


@pytest.mark.skipif(sys.platform != "linux", reason="Actual Linux /proc control")
def test_exited_leader_cannot_leave_closed_pipe_descendant(tmp_path):
    marker = tmp_path / "descendant.pid"
    program = """import os,signal,sys,time
pid=os.fork()
if pid==0:
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 os.close(1);os.close(2)
 while True:time.sleep(1)
open(sys.argv[1],'w').write(str(pid))
"""
    child = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", program, str(marker)],
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    child._anvil_owned_group = UnreapedProcessGroup(child)
    until = time.monotonic() + 3
    try:
        while not child._anvil_owned_group.exited():
            assert time.monotonic() < until
            time.sleep(0.01)
        descendant = int(marker.read_text())
        assert Path(f"/proc/{descendant}/stat").exists()
        stop(child)
        assert child.returncode == 0
        assert not child._anvil_owned_group.held
        path = Path(f"/proc/{descendant}/stat")
        assert not path.exists() or path.read_text().rpartition(") ")[2].split()[0] == "Z"
        stop(child)  # Idempotent cleanup never signals a reaped PGID.
    finally:
        if child._anvil_owned_group.held:
            stop(child)
        child.stdout.close()
        child.stderr.close()


def test_missing_owner_never_signals_numeric_group(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(os, "killpg", lambda *a: pytest.fail("Unowned numeric group signal"))
    with pytest.raises(RuntimeError, match="ownership required"):
        stop(SimpleNamespace(pid=123))
