"""Manufactured labels only; actual kernel probe is separately recorded."""

from types import SimpleNamespace

import pytest

from anvil import marketing_native_mac as mac


def platform(monkeypatch):
    monkeypatch.setattr(mac.sys, "platform", "linux")
    monkeypatch.setattr(mac.os, "uname", lambda: SimpleNamespace(machine="x86_64"))
    monkeypatch.setattr(mac.os, "geteuid", lambda: 0)


@pytest.mark.parametrize("role", ["sdk", "graph"])
def test_fixed_role_only_adds_profile_and_preserves_operator(monkeypatch, role):
    platform(monkeypatch)
    labels = iter(
        [mac.OPERATOR + " (enforce)", mac.ACTORS[role] + "//&" + mac.OPERATOR + " (enforce)"]
    )
    monkeypatch.setattr(mac, "_current_label", lambda: next(labels))
    writes, closed = [], []
    monkeypatch.setattr(mac.os, "open", lambda path, flags: 123)
    monkeypatch.setattr(mac.os, "write", lambda fd, raw: writes.append((fd, raw)) or len(raw))
    monkeypatch.setattr(mac.os, "close", lambda fd: closed.append(fd))
    mac.stack_actor_profile(role)
    assert writes == [(123, ("stack " + mac.ACTORS[role]).encode())]
    assert closed == [123]


@pytest.mark.parametrize(
    "value",
    [
        "unconfined",
        mac.OPERATOR + " (complain)",
        "other (enforce)",
        mac.OPERATOR + "//&other (enforce)",
        mac.OPERATOR + "//&" + mac.OPERATOR + " (enforce)",
    ],
)
def test_unqualified_or_mixed_original_label_never_attempts_transition(monkeypatch, value):
    platform(monkeypatch)
    monkeypatch.setattr(mac, "_current_label", lambda: value)
    monkeypatch.setattr(mac.os, "open", lambda *a: pytest.fail("No mutation allowed"))
    with pytest.raises(ValueError):
        mac.stack_actor_profile("sdk")


def test_short_transition_write_is_unknown_and_not_retried(monkeypatch):
    platform(monkeypatch)
    monkeypatch.setattr(mac, "_current_label", lambda: mac.OPERATOR + " (enforce)")
    writes, closed = [], []
    monkeypatch.setattr(mac.os, "open", lambda *a: 123)
    monkeypatch.setattr(mac.os, "write", lambda fd, raw: writes.append(raw) or 1)
    monkeypatch.setattr(mac.os, "close", lambda fd: closed.append(fd))
    with pytest.raises(RuntimeError, match="unknown_no_retry"):
        mac.stack_actor_profile("graph")
    assert len(writes) == 1 and closed == [123]


def test_wrong_post_transition_label_refuses_readiness_without_retry(monkeypatch):
    platform(monkeypatch)
    labels = iter([mac.OPERATOR + " (enforce)", mac.OPERATOR + " (enforce)"])
    monkeypatch.setattr(mac, "_current_label", lambda: next(labels))
    writes = []
    monkeypatch.setattr(mac.os, "open", lambda *a: 123)
    monkeypatch.setattr(mac.os, "write", lambda fd, raw: writes.append(raw) or len(raw))
    monkeypatch.setattr(mac.os, "close", lambda fd: None)
    with pytest.raises(ValueError, match="original_enforced_actor"):
        mac.stack_actor_profile("sdk")
    assert len(writes) == 1
