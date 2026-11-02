from types import SimpleNamespace

from anvil import artifacts


def test_root_worker_preserves_volume_owner_and_private_file_modes(tmp_path, monkeypatch):
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    owner = root.stat().st_uid
    monkeypatch.setattr(artifacts, "storage_root", lambda: root)
    monkeypatch.setattr(artifacts.os, "geteuid", lambda: 0)
    monkeypatch.setattr(artifacts.os, "fstat", lambda fd: SimpleNamespace(st_uid=-1))
    changes = []
    monkeypatch.setattr(artifacts.os, "fchown", lambda fd, uid, gid: changes.append((uid, gid)))

    class Connection:
        def execute(self, *args):
            pass

    aid = artifacts.store(Connection(), "project", b"private generated code", "hidden_reference")
    path = root / "project" / aid
    assert changes == [(owner, -1)]
    assert path.read_bytes() == b"private generated code"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_application_writer_does_not_change_ownership(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "storage_root", lambda: tmp_path)
    monkeypatch.setattr(artifacts.os, "geteuid", lambda: 10001)

    def forbidden(*args):
        raise AssertionError("Non-root writer must not change ownership")

    monkeypatch.setattr(artifacts.os, "fchown", forbidden)
    monkeypatch.setattr(artifacts.os, "chown", forbidden)

    class Connection:
        def execute(self, *args):
            pass

    aid = artifacts.store(Connection(), "project", b"safe", "actor")
    assert (tmp_path / "project" / aid).stat().st_mode & 0o777 == 0o600
