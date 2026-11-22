"""RL Gym v2 work package 2.8 units: PDF HTML escaping, radar chart, write-once storage. No database."""

import pytest

from anvil.rlgym.common import GymError
from anvil.rlgym.results import pdf, service

MODELS = [
    {"system_id": "a", "name": "<b>A</b>", "version": 1},
    {"system_id": "b", "name": "B", "version": 1},
]


def test_pdf_escapes_every_value():
    assert pdf.e("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
    html = pdf.table(["H"], [[pdf.e("<img src=x onerror=1>")]])
    assert "<img" not in html and "&lt;img" in html
    bars = pdf.bars({"a": 50}, MODELS)
    assert "&lt;b&gt;A&lt;/b&gt;" in bars and "<b>A</b>" not in bars


def test_radar_needs_three_axes_and_clamps_nothing_outside_the_svg():
    axes = [{"capability": c, "per_model": {"a": 100, "b": 0}} for c in ("X", "Y")]
    assert pdf.radar(axes, MODELS) == ""
    axes.append({"capability": "Z<", "per_model": {"a": None}})
    svg = pdf.radar(axes, MODELS)
    assert svg.startswith("<svg") and "Z&lt;" in svg and svg.count("<polygon") == 4 + 2


def test_write_once_accepts_the_same_bytes_and_refuses_different(tmp_path):
    path = tmp_path / "x" / "f.pdf"
    service._write_once(path, b"%PDF-1")
    service._write_once(
        path, b"%PDF-1"
    )  # retry after a failed transaction finds the identical file
    with pytest.raises(GymError):
        service._write_once(path, b"%PDF-2")
    assert oct(path.stat().st_mode)[-3:] == "444"


def test_stored_files_are_hash_checked(tmp_path):
    root = tmp_path
    (root / "a.json").write_bytes(b"{}")
    with pytest.raises(GymError):
        service._read_checked(root, "a.json", "0" * 64)
    with pytest.raises(GymError):
        service._read_checked(root, "../etc/passwd", "0" * 64)
