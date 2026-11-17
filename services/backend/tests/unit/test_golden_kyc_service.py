import subprocess
import sys
from threading import Event
from time import monotonic, sleep

import pytest

from anvil import golden_kyc_service as service
from anvil.golden_kyc_service import DSNS, serve, validate_environment

PROJECT = "abc00000-0000-0000-0000-000000000001"


@pytest.fixture
def admitted(monkeypatch):
    monkeypatch.setattr(
        "os.environ",
        {
            "ANVIL_GOLDEN_KYC_ENABLED": "true",
            DSNS["scheduler"]: "postgresql://dedicated-runtime/test",
        },
    )


def test_only_explicit_software_phases_are_dispatched_in_order(admitted):
    calls = []
    assert (
        serve(
            "scheduler",
            [PROJECT],
            max_cycles=2,
            interval=0.1,
            max_seconds=10,
            stop=Event(),
            worker=calls.append,
        )
        == 2
    )
    assert [args[3] for args in calls] == ["commands", "capture", "finish"] * 2
    assert all(args[1] == PROJECT for args in calls)


def test_worker_failure_stops_without_any_automatic_retry(admitted):
    calls = []

    def failed(args):
        calls.append(args)
        raise RuntimeError("ambiguous retained operation")

    with pytest.raises(RuntimeError, match="ambiguous retained operation"):
        serve(
            "scheduler",
            [PROJECT],
            max_cycles=5,
            interval=0.1,
            max_seconds=10,
            stop=Event(),
            worker=failed,
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "key,value",
    [
        (DSNS["grader"], "postgresql://grader/test"),
        ("DATABASE_URL", "postgresql://owner/test"),
        ("OPENAI_API_KEY", "synthetic-never-a-real-key"),
        ("ANVIL_GOLDEN_KYC_PAID_WORKER_ENABLED", "true"),
        ("ANVIL_CAMPAIGN_GRADING_ENABLED", "true"),
    ],
)
def test_mixed_credentials_and_paid_flags_are_rejected(key, value):
    with pytest.raises(RuntimeError, match="mixed credentials"):
        validate_environment(
            "scheduler",
            {
                "ANVIL_GOLDEN_KYC_ENABLED": "true",
                DSNS["scheduler"]: "dedicated",
                key: value,
            },
        )


def test_grader_only_receives_grade_phase(monkeypatch):
    monkeypatch.setattr(
        "os.environ",
        {
            "ANVIL_GOLDEN_KYC_ENABLED": "true",
            DSNS["grader"]: "dedicated",
        },
    )
    calls = []
    serve(
        "grader",
        [PROJECT],
        max_cycles=1,
        interval=0.1,
        max_seconds=10,
        stop=Event(),
        worker=calls.append,
    )
    assert [args[3] for args in calls] == ["grade"]


def test_stopped_service_does_not_claim_more_work(admitted):
    stop = Event()
    stop.set()
    assert (
        serve(
            "scheduler",
            [PROJECT],
            max_cycles=1,
            interval=0.1,
            max_seconds=10,
            stop=stop,
            worker=lambda _: pytest.fail("unexpected dispatch"),
        )
        == 0
    )


def test_active_child_is_terminated_at_deadline_and_not_restarted(monkeypatch):
    children = []

    def sleeping_worker(command, **kwargs):
        assert command[1:5] == ["-I", "-B", "-m", "anvil.golden_kyc_worker"]
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(service, "Popen", sleeping_worker)
    started = monotonic()
    with pytest.raises(RuntimeError, match="interrupted.*no retry"):
        service.run_worker(["--mode", "capture"], deadline=started + 0.2, stop=Event())
    assert monotonic() - started < 3
    assert len(children) == 1 and children[0].poll() is not None


def test_failed_child_stops_without_another_attempt(monkeypatch):
    children = []

    def failed_worker(command, **kwargs):
        child = subprocess.Popen([sys.executable, "-c", "raise SystemExit(7)"], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(service, "Popen", failed_worker)
    with pytest.raises(RuntimeError, match="failed.*no retry"):
        service.run_worker([], deadline=monotonic() + 5, stop=Event())
    assert len(children) == 1 and children[0].returncode == 7


def test_deadline_also_stops_descendant_that_ignores_sigterm(tmp_path, monkeypatch):
    heartbeat = tmp_path / "owned-descendant-heartbeat"
    descendant = (
        "import signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"p=Path({str(heartbeat)!r}); "
        "\nwhile True:\n p.write_text(str(time.monotonic_ns()))\n time.sleep(.02)"
    )
    leader = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{descendant!r}]); time.sleep(30)"
    )
    children = []

    def launch(command, **kwargs):
        child = subprocess.Popen([sys.executable, "-c", leader], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(service, "Popen", launch)
    try:
        with pytest.raises(RuntimeError, match="interrupted.*no retry"):
            service.run_worker([], deadline=monotonic() + 0.8, stop=Event())
        assert len(children) == 1 and children[0].poll() is not None
        assert heartbeat.is_file()
        sleep(0.1)
        retained = heartbeat.read_bytes()
        sleep(0.15)
        assert heartbeat.read_bytes() == retained
    finally:
        # Even a regression must not leave this test's owned descendant running.
        import os
        import signal

        for child in children:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_continuous_mode_renews_only_clean_windows_and_stops_on_signal(monkeypatch):
    stopped, calls = Event(), []
    monkeypatch.setattr(service, "Event", lambda: stopped)

    def clean(role, projects, **kwargs):
        calls.append((role, projects))
        if len(calls) == 2:
            stopped.set()
        return 1

    monkeypatch.setattr(service, "serve", clean)
    service.main(
        ["--role", "scheduler", "--project", PROJECT, "--continuous", "--poll-seconds", ".1"]
    )
    assert len(calls) == 2


def test_continuous_mode_never_restarts_failed_window(monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("retained_unknown_no_retry")

    monkeypatch.setattr(service, "serve", fail)
    with pytest.raises(RuntimeError, match="retained_unknown_no_retry"):
        service.main(["--role", "scheduler", "--project", PROJECT, "--continuous"])
    assert calls == [1]
