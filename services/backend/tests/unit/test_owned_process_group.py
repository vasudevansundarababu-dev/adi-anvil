import signal
import subprocess
import sys
import time

import pytest

from anvil.owned_process_group import UnreapedProcessGroup


def test_leader_is_not_reaped_until_final_group_signal():
    child = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    group = UnreapedProcessGroup(child, fixed_same_uid=True)
    try:
        limit = time.monotonic() + 3
        while not group.exited() and time.monotonic() < limit:
            time.sleep(0.01)
        assert group.exited()
        assert child.returncode is None  # Exit observed WITHOUT poll/wait/reap.
        group.signal(signal.SIGKILL)
        assert group.reap(1) == 0
        with pytest.raises(RuntimeError, match="reaped"):
            group.signal(signal.SIGKILL)
    finally:
        if group.held:
            group.signal(signal.SIGKILL)
            group.reap(1)
