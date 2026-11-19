"""Private diagnostics do not confer execution or qualification authority."""
import json

import pytest

from anvil import environment_harbor as native
from anvil import golden_kyc_probe as probe


def test_capture_failure_retains_exclusive_private_prefixes(tmp_path):
    tmp_path.chmod(0o700)
    error = native.FixedCaptureStopped("callback_deadline", {"bytes": 6},
                                       private_prefixes={"stdout": b"abc", "stderr": b"def"})
    native.retain_fixed_capture_failure(tmp_path, "harbor-private.log", error)
    path = tmp_path / "harbor-private.log"
    assert path.read_bytes() == b"abcdef"
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads((tmp_path / "harbor-private.log.capture.json").read_text()) == {"bytes": 6}
    assert "abc" not in str(error.evidence)
    with pytest.raises(FileExistsError):
        native.retain_fixed_capture_failure(tmp_path, "harbor-private.log", error)


@pytest.mark.parametrize("name,parts", [("../public", {}),
    ("harbor-private.log", {"stdout": b"x" * 1048577}),
    ("harbor-private.log", {"stderr": "not bytes"})])
def test_capture_failure_rejects_unsafe_destinations_and_bounds(tmp_path, name, parts):
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError):
        native.retain_fixed_capture_failure(tmp_path, name,
            native.FixedCaptureStopped("test", {}, private_prefixes=parts))
    assert list(tmp_path.iterdir()) == []


def test_safe_worker_failure_omits_exception_message(capsys):
    try:
        raise ValueError("postgresql://private-password@private-host")
    except ValueError as error:
        probe.write_safe_failure(error)
    output = capsys.readouterr()
    value = json.loads(output.err)
    assert output.out == ""
    assert value["error_type"] == "ValueError"
    assert value["frames"][-1]["function"] == "test_safe_worker_failure_omits_exception_message"
    assert "private-password" not in output.err
    assert "private-host" not in output.err
