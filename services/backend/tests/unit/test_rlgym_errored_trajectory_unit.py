"""D-050: an episode that stops with an error keeps its trajectory so far, apart from sealed evidence and never
scored. Synthetic data, a fake environment session and the controlled mock policy; no model calls, no database."""

import json
import os
import stat

import pytest

from anvil.rlgym.runs import worker


class FakeSession:
    """Answers reset, then fails on the third tool call (as a spend limit or a broken environment would)."""

    def __init__(self):
        self.calls, self.closed = 0, False

    def request(self, msg):
        if msg["op"] == "reset":
            return {"ok": True, "user_message": "Review the application."}
        if msg["op"] == "call":
            self.calls += 1
            if self.calls == 3:
                raise RuntimeError("episode spend limit $0.3 would be crossed")
            return {"ok": True, "state": "completed", "output": {"n": self.calls}}
        return {"ok": True}

    def close(self):
        self.closed = True


EPISODE = {
    "id": "run-x-e0001",
    "run_id": "run-x",
    "workspace_id": "ws",
    "kind": "case",
    "task_id": "t1",
    "task_revision": 1,
    "case_id": "kyc-1",
    "attempt": 1,
    "tries": 1,
    "system_id": "mock-a",
    "ts_prompt_id": None,
}
MANIFEST = {
    "manifest": {
        "tasks": [],
        "models": [{"system_id": "mock-a", "model_id": "mock/erratic-v1"}],
        "environment": {"version_id": "env@1"},
        "execution_mode": "mock",
        "note": "test",
    },
    "manifest_sha256": "0" * 64,
}


def run_failing():
    session = FakeSession()
    with pytest.raises(RuntimeError) as info:
        worker.execute(
            EPISODE,
            {"episode_timeout_s": 60},
            MANIFEST,
            None,
            {"assignment": "Review the application."},
            session_factory=lambda: session,
        )
    return info.value, session


def test_a_failing_episode_carries_its_trajectory_so_far():
    exc, session = run_failing()
    assert session.closed
    partial = exc.partial
    assert partial["steps"] == 2 and len(partial["transcript"]) == 2
    assert [e["tool"] for e in partial["tool_events"]] == [t["tool"] for t in partial["transcript"]]
    assert partial["live"] is False and partial["cost_usd"] == 0.0


def test_kept_trajectory_is_read_only_labelled_and_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(worker.scoring, "EVIDENCE_ROOT", tmp_path)
    exc, _ = run_failing()
    ref, digest = worker.keep_trajectory("ws", EPISODE, exc, "errored", str(exc))
    assert ref == "local-evidence://ws/run-x/run-x-e0001-t1.errored.json" and len(digest) == 64
    path = tmp_path / "ws/run-x/run-x-e0001-t1.errored.json"
    body = json.loads(path.read_text())
    assert body["schema"] == "rlgym.errored-episode.v1"
    assert body["sealed"] is False and body["scored"] is False and body["synthetic"] is True
    assert body["outcome"] == "errored" and "spend limit" in body["error"]["message"]
    assert len(body["transcript"]) == 2
    assert not os.stat(path).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    # A second write for the same try never replaces the first (and never raises).
    assert worker.keep_trajectory("ws", EPISODE, exc, "errored", "other") is None
    assert json.loads(path.read_text())["error"]["message"] == body["error"]["message"]
    # The sealed-evidence name is untouched: the errored file can't be mistaken for a sealed bundle.
    assert not (tmp_path / "ws/run-x/run-x-e0001-t1.json").exists()


def test_an_error_without_a_trajectory_keeps_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(worker.scoring, "EVIDENCE_ROOT", tmp_path)
    assert (
        worker.keep_trajectory("ws", EPISODE, RuntimeError("before reset"), "errored", "x") is None
    )
    assert not any(tmp_path.iterdir())


def test_run_episode_keeps_the_trajectory_before_recording_the_error():
    import inspect

    src = inspect.getsource(worker.run_episode)
    assert src.count("keep_trajectory(ws, episode, exc,") == 2
    assert src.count("_kept_event(c, ws, episode, kept)") == 2


def test_a_model_version_without_temperature_validates_and_sends_none():
    # The owner's form showed 0 pre-filled; an empty box now sends no temperature at all.
    from anvil.rlgym.live import gateway
    from anvil.rlgym.systems import service

    service._num({"max_output_tokens": 4096}, "temperature", 0)  # absent: allowed, no error
    body = gateway._anthropic_body("claude-haiku-5-5", "s", [], 4096, None)
    assert "temperature" not in body
    assert gateway._anthropic_body("m", "s", [], 4096, 0)["temperature"] == 0


class _Rows:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Ctx:
    """Just enough of a request context for systems._validate: a default, active key."""

    ws = "ws"

    class c:
        @staticmethod
        def execute(sql, args=None):
            return _Rows({"id": "key-1", "provider": "anthropic", "status": "active"})


def _config(params):
    from anvil.rlgym.systems import service

    return service._validate(
        _Ctx(),
        {
            "kind": "frontier",
            "provider": "anthropic",
            "model_id": "claude-haiku-5-5",
            "params": params,
            "limits": {"rpm": 30, "spend_per_episode_usd": 1},
        },
    )


def test_d052_empty_temperature_is_left_out_and_hashes_like_no_temperature():
    from anvil.rlgym.common import sha

    base = {"max_output_tokens": 4096, "timeout_s": 120}
    as_null = _config({**base, "temperature": None})
    left_out = _config(dict(base))
    assert "temperature" not in as_null["params"]
    assert sha(as_null) == sha(left_out)
    assert sha(_config({**base, "temperature": 0})) != sha(left_out)


def test_d052_the_form_never_saves_silently():
    import pathlib

    src = (
        pathlib.Path(__file__).parents[4] / "apps/web/src/components/rlgym/Models.tsx"
    ).read_text()
    assert "temperature.trim() === '' ? undefined : Number(temperature)" in src
    assert "NO_NEW_VERSION" in src and "Saved as version ${r.version}" in src
    assert "No change: same settings as an existing version." not in src
