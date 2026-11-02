from uuid import uuid4

from anvil import harbor_worker


def test_cloud_trial_uses_operator_work_volume_without_writing_authority_mount(
    tmp_path, monkeypatch
):
    readonly_root = tmp_path / "application"
    readonly_root.mkdir()
    (readonly_root / ".local").mkdir(mode=0o500)
    work_volume = tmp_path / "operator-work-volume"
    work_volume.mkdir(mode=0o700)
    monkeypatch.setattr(harbor_worker, "ROOT", readonly_root)
    monkeypatch.setenv("ANVIL_HARBOR_WORK_ROOT", str(work_volume))
    trial = str(uuid4())
    target = harbor_worker.check_workspace(trial)
    target.mkdir(mode=0o700)
    assert target.parent == work_volume
    assert not (readonly_root / ".local/harbor-checks").exists()
    assert target.stat().st_mode & 0o777 == 0o700
