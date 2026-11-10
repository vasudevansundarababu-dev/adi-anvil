import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def repository(tmp_path, files):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    files = {**files, "scripts/secret_scan.py": (ROOT / "scripts/secret_scan.py").read_text()}
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    return tmp_path


def scan(root):
    return subprocess.run(
        [sys.executable, str(root / "scripts/secret_scan.py")],
        capture_output=True,
        text=True,
        env={"PATH": os.defpath},
        check=False,
    )


def test_readiness_work_id_is_not_a_credential(tmp_path):
    root = repository(
        tmp_path, {"report.md": "docs/runs/anvil-task-readiness-explanations-2026-11-06/"}
    )
    result = scan(root)
    assert result.returncode == 0
    assert json.loads(result.stdout)["findings"] == []


def test_real_shaped_fixture_tokens_are_reported_without_values(tmp_path):
    fictional = ["sk-" + "x" * 32, "ghp_" + "x" * 32, "AKIA" + "1" * 16]
    root = repository(
        tmp_path, {f"test-{i}.txt": 'value="' + value + '"' for i, value in enumerate(fictional)}
    )
    result = scan(root)
    assert result.returncode == 1
    text = result.stdout
    assert all(value not in text for value in fictional)
    assert len(json.loads(text)["findings"]) == 3


def test_forbidden_runtime_file_remains_rejected(tmp_path):
    root = repository(tmp_path, {".local/runtime.txt": "fictional test metadata"})
    result = scan(root)
    assert result.returncode == 1
    assert json.loads(result.stdout)["findings"] == [
        {"path": ".local/runtime.txt", "rule": "private_file_tracked"}
    ]
