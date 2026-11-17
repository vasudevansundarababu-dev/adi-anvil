"""New outcome-neutral report controls; no report activation or model calls."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from anvil.marketing_world_outcome_data import ALTERNATIVE_FILES, BASE_FILES, compile_reports
from anvil.praxis_generic_contract import canonical


def source(case="GT2-R01", branch="positive"):
    root = Path(os.environ["ANVIL_MARKETING_SOURCE_FIXTURE_ROOT"])
    raw = (root / "checksums.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "59539b978994b472495f46786cf5085eae553230d2d7a2356acb165dea9d539a"
    pins = json.loads(raw)
    paths = [f"cases/{case}/{name}" for name in BASE_FILES]
    paths += [f"reviewer_only/us-pair/{case}/reuse-test-{branch}/{name}" for name in ALTERNATIVE_FILES]
    return {path: (root / path).read_bytes() for path in paths}, pins


@pytest.mark.parametrize("case", ["GT2-R01", "GT2-R02"])
@pytest.mark.parametrize("branch", ["positive", "null", "negative"])
def test_all_report_branches_retain_original_other_scope_and_hide_outcome_identifiers(case, branch):
    files, pins = source(case, branch)
    before = dict(files)
    program = compile_reports(case, files, pins, branch=branch)
    original = {r["id"]: r for r in program["baseline"]}
    selected = {r["id"]: r for r in program["selected"]}
    for key, row in original.items():
        if row.get("locale") != "en-US" or row.get("channel") != "search" or row.get("week") not in (7, 8):
            assert selected[key] == row
    assert sum(not r["report_detail"] for r in selected.values()) == 1440
    assert any(r.get("experiment_id") == case + "_commute_reuse_test" for r in selected.values())
    encoded = canonical(program["selected"])
    assert all(label not in encoded for label in (b"_positive_", b"_negative_", b"_null_", b"reuse-test-"))
    assert files == before


def test_semantic_detail_ids_are_same_across_all_outcomes():
    ids = []
    for branch in ("positive", "null", "negative"):
        files, pins = source(branch=branch)
        value = compile_reports("GT2-R01", files, pins, branch=branch)
        ids.append({r["id"] for r in value["selected"]})
    assert ids[0] == ids[1] == ids[2]


def test_changed_report_bytes_fail_independent_hash_before_projection():
    files, pins = source()
    files["cases/GT2-R01/daily_performance.jsonl"] += b"\n"
    with pytest.raises(ValueError, match="independently pinned"):
        compile_reports("GT2-R01", files, pins, branch="positive")


def test_alternative_cannot_modify_other_market_even_with_matching_new_operator_pin():
    files, pins = source()
    path = "reviewer_only/us-pair/GT2-R01/reuse-test-positive/alternative_daily_performance.jsonl"
    rows = [json.loads(line) for line in files[path].splitlines()]
    row = next(r for r in rows if r["locale"] != "en-US")
    row["verified_visits"] += 1
    files[path] = b"\n".join(canonical(r) for r in rows) + b"\n"
    pins[path] = hashlib.sha256(files[path]).hexdigest()
    with pytest.raises(ValueError, match="unauthorized report"):
        compile_reports("GT2-R01", files, pins, branch="positive")
