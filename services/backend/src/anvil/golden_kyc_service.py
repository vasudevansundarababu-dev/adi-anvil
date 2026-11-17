"""Bounded software-control service for disjoint Golden scheduler/grader roles.

This entry never starts paid modes or reclaims interrupted work. Exceptions stop
the service; operators must inspect durable custody before starting it again.
"""

import argparse
import os
import signal
import sys
from subprocess import Popen, TimeoutExpired
from threading import Event
from time import monotonic
from uuid import UUID

PHASES = {"scheduler": ("commands", "capture", "finish"), "grader": ("grade",)}
DSNS = {
    "scheduler": "ANVIL_GOLDEN_SCHEDULER_DATABASE_URL",
    "grader": "ANVIL_GOLDEN_GRADER_DATABASE_URL",
}


def validate_environment(role, env):
    if env.get("ANVIL_GOLDEN_KYC_ENABLED") != "true" or not env.get(DSNS[role]):
        raise RuntimeError("Explicit software-control admission and dedicated login required")
    for key, value in env.items():
        if not value:
            continue
        if (
            key.endswith("DATABASE_URL")
            and key != DSNS[role]
            or key.endswith("_API_KEY")
            or key in {"GOOGLE_APPLICATION_CREDENTIALS", "ANVIL_SECRET_MASTER_KEY"}
            or key.startswith("ANVIL_")
            and key.endswith("_ENABLED")
            and key != "ANVIL_GOLDEN_KYC_ENABLED"
            and value.lower() not in {"false", "0"}
        ):
            raise RuntimeError(
                "Software-control service has mixed credentials or active dispatch flags"
            )


def run_worker(argv, *, deadline, stop):
    """Own one process group; stop on interruption without replaying its work."""
    if stop.is_set() or monotonic() >= deadline:
        raise RuntimeError("Software worker deadline or stop reached before dispatch")
    child = Popen(
        [sys.executable, "-I", "-B", "-m", "anvil.golden_kyc_worker", *argv],
        start_new_session=True,
    )
    try:
        while child.poll() is None:
            if stop.is_set() or monotonic() >= deadline:
                raise RuntimeError(
                    "Software worker interrupted; inspect retained custody, no retry"
                )
            stop.wait(min(0.1, max(0, deadline - monotonic())))
        if child.returncode:
            raise RuntimeError("Software worker failed; inspect retained custody, no retry")
    finally:
        # A reaped leader does not prove same-group descendants exited. Finish
        # the owned group on normal completion, interruption and BaseException.
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=2)
            except TimeoutExpired:
                pass
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=2)
        except TimeoutExpired:
            raise RuntimeError("Software worker cleanup unknown; no retry") from None


def serve(role, projects, *, max_cycles, interval, max_seconds, stop, worker=None):
    """Poll only named projects, stop at cycle/time bounds, never retry a failure."""
    if role not in PHASES or not 1 <= len(projects) <= 32:
        raise ValueError("One supported role and 1–32 explicit projects required")
    projects = tuple(str(UUID(str(project))) for project in projects)
    if len(set(projects)) != len(projects):
        raise ValueError("Duplicate project")
    if not 1 <= max_cycles <= 10000 or not 0.1 <= interval <= 60 or not 1 <= max_seconds <= 3600:
        raise ValueError("Bounded cycle, poll and elapsed limits required")
    validate_environment(role, os.environ)
    deadline = monotonic() + max_seconds
    completed = 0
    for cycle in range(max_cycles):
        for project in projects:
            for phase in PHASES[role]:
                if stop.is_set() or monotonic() >= deadline:
                    return completed
                arguments = ["--project", project, "--mode", phase, "--max-commands", "20"]
                if worker is None:
                    run_worker(arguments, deadline=deadline, stop=stop)
                else:
                    worker(arguments)
        completed += 1
        if cycle + 1 < max_cycles:
            stop.wait(min(interval, max(0, deadline - monotonic())))
    return completed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=tuple(PHASES), required=True)
    parser.add_argument("--project", type=UUID, action="append", required=True)
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--poll-seconds", type=float, default=2)
    parser.add_argument("--max-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    stop = Event()
    previous = {}
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, lambda *_: stop.set())
        completed = serve(
            args.role,
            args.project,
            max_cycles=args.max_cycles,
            interval=args.poll_seconds,
            max_seconds=args.max_seconds,
            stop=stop,
        )
        print(f"Golden {args.role}: {completed} software-control polling cycles; no model calls")
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
