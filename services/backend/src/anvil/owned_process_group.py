"""Keep the owned leader unreaped until group signaling is finished.

A PID/PGID must not become reusable between observing exit and killing remaining
descendants. Never poll()/wait() the Popen outside this owner before final reap.
"""

import os
import select
import sys


class UnreapedProcessGroup:
    def __init__(self, child, *, fixed_same_uid=False):
        self.child = child
        self.held = True
        self._exited = False
        self._watch = None
        self._observation_error = None
        self._fixed_same_uid = fixed_same_uid
        if sys.platform == "darwin":
            try:
                self._watch = select.kqueue()
                self._watch.control(
                    [
                        select.kevent(
                            child.pid,
                            filter=select.KQ_FILTER_PROC,
                            flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE | select.KQ_EV_ONESHOT,
                            fflags=select.KQ_NOTE_EXIT,
                        )
                    ],
                    0,
                    0,
                )
            except BaseException as error:
                # Caller retains custody and its ORIGINAL cleanup budget.
                self._observation_error = error
        elif not hasattr(os, "waitid") or not hasattr(os, "WNOWAIT"):
            self._observation_error = RuntimeError("Unreaped child observation is unavailable")

    def exited(self):
        if not self.held:
            raise RuntimeError("Owned group was already reaped")
        if self._observation_error is not None:
            raise RuntimeError(
                "Owned child exit observation unavailable"
            ) from self._observation_error
        if not self._exited:
            if self._watch is not None:
                self._exited = bool(self._watch.control(None, 1, 0))
            else:
                self._exited = (
                    os.waitid(os.P_PID, self.child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    is not None
                )
        return self._exited

    def signal(self, number):
        if not self.held:
            raise RuntimeError("Cannot signal a reaped process group")
        try:
            os.killpg(self.child.pid, number)
        except ProcessLookupError:
            pass
        except PermissionError:
            # XNU killpg1 filters zombies then returns EPERM when no signallable
            # member remains. Only fixed same-UID software children opt into
            # this compatibility case; Linux/native custody never ignores EPERM.
            # apple-oss-distributions/xnu/bsd/kern/kern_sig.c:killpg1
            if not (sys.platform == "darwin" and self._fixed_same_uid and self.exited()):
                raise

    def reap(self, timeout):
        # This must be the LAST operation using the numeric group identity.
        result = self.child.wait(timeout=max(0, timeout))
        self.held = False
        if self._watch is not None:
            self._watch.close()
            self._watch = None
        return result
