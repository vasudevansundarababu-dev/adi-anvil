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


def test_inbox_evidence_goes_out_as_a_list():
    from anvil.rlgym.integrations import wire_payload

    more = wire_payload(
        "inbox_item.send",
        {
            "kind": "more_data",
            "evidence": {"cells": [{"cell_key": "a"}, {"cell_key": "b"}], "lineage": "same"},
        },
    )
    assert more["evidence"] == [
        {"type": "cell", "cell_key": "a"},
        {"type": "cell", "cell_key": "b"},
        {"type": "plan", "lineage": "same"},
    ]
    one = wire_payload(
        "inbox_item.send", {"kind": "new_case_kind", "evidence": {"run_id": "run-1"}}
    )
    assert one["evidence"] == [{"type": "detail", "run_id": "run-1"}]
    assert wire_payload("inbox_item.send", {"evidence": None})["evidence"] == []
    assert wire_payload("evaluator.event", {"evidence": {"x": 1}}) == {"evidence": {"x": 1}}


def test_stub_events_are_refused_while_following_another_registry(monkeypatch):
    from anvil.rlgym.catalog import registry

    monkeypatch.setenv("RLGYM_STUDIO_URL", "http://127.0.0.1:8060")
    with pytest.raises(GymError) as refused:
        registry.receive(
            {"source": "studio-registry-stub", "type": "version.registered", "data": {"seq": 1}}
        )
    assert refused.value.code == "CONFLICT"


def test_forge_qualification_record_matches_p03_only_for_forge_published_templates(monkeypatch):
    from anvil.rlgym.catalog.templates import forge_qualification

    record = {
        "template_id": "tpl_x",
        "version": 1,
        "receipt_id": "tq-1",
        "event_sha256": "e" * 64,
        "status": "QUALIFIED",
    }
    doc = {
        "template_id": "tpl_x",
        "version": 1,
        "spec_sha256": "s" * 64,
        "forge_template_id": "uuid-1",
        "forge_version": 2,
    }
    checks = {"known_case_tests_passed": True, "detail": ["dropped"]}
    monkeypatch.setenv("RLGYM_FORGE_QUALIFICATION_URL", "http://127.0.0.1:8111")
    monkeypatch.setenv("RLGYM_FORGE_TENANT_ID", "t-1")
    assert (
        forge_qualification(doc, record, checks) is record
    )  # no ADI Forge version hash: the RL Gym's stub path
    out = forge_qualification({**doc, "forge_template_version_hash": "h" * 64}, record, checks)
    wire = {k: v for k, v in out.items() if not k.startswith("_")}
    assert set(wire) == {
        "template_id",
        "version",
        "template_version_hash",
        "status",
        "receipt_id",
        "receipt",
    }
    assert (
        wire["template_id"] == "uuid-1"
        and wire["version"] == 2
        and wire["template_version_hash"] == "h" * 64
    )
    assert out["_base"] == "http://127.0.0.1:8111" and out["_headers"] == {"X-Tenant-Id": "t-1"}
    assert "detail" not in wire["receipt"]["checks"]
