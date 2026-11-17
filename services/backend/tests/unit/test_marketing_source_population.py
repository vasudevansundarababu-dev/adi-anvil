"""Actual approved source bytes with manufactured task/dataset IDs; source only."""

import json
import os
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from anvil.marketing_task2_persistence import freeze
from anvil.marketing_task2_tools import execute
from anvil.marketing_world_definition import definition
from anvil.marketing_world_population import decode_sources
from anvil.marketing_world_provisioning import build, load_files, needed_files
from anvil.praxis_generic_contract import canonical, digest


def proposal(case="GT2-R01"):
    root = Path(os.environ["ANVIL_MARKETING_SOURCE_FIXTURE_ROOT"])
    pins = json.loads((root / "checksums.json").read_bytes())
    dataset = {"fixture_manifest_sha256": "a" * 64, "fixture_manifest": {"source_hashes": pins},
               "manifest": {"schema_version": "anvil.campaign-case-dataset.v1", "id": "unit-source-dataset", "version": "1",
                            "case_count": 2, "cases": [{"id": name, "locale": "en-US", "snapshot_sha256": str(index) * 64}
                                                       for index, name in enumerate(("GT2-R01", "GT2-R02"), 1)]}}
    execution = json.loads((Path(__file__).parents[1] / "fixtures/veyra-template-execution-v3.json").read_bytes())
    files = load_files(root, case, pins)
    value = build(case, dataset, execution, task_id="unit-source-task", revision_id="unit-revision",
                  rights_receipt_sha256="c" * 64, files=files, branch_seed="b" * 64)
    return value, files, execution


@pytest.mark.parametrize("case", ["GT2-R01", "GT2-R02"])
def test_complete_actual_source_population_retains_original_caps_and_opening(case):
    value, _, execution = proposal(case)
    world = definition(value)
    controller = world.controller(0)
    counts = {key: len(rows) for key, rows in controller._initial.items()}
    assert counts["products"] == 1 and counts["capabilities"] == 3 and counts["campaigns"] == 7
    assert counts["questions"] == 4024 and counts["observation-windows"] == 252
    assert counts["reports"] == 2208 and counts["ledger"] == 1263
    assert sum(counts.values()) <= 20000 and len(canonical(value)) <= 16777216
    assert len(canonical(freeze(controller)[0])) <= 16777216
    assert all("manufactured-branch-marker" != row.public["id"] for row in world.records["work"])
    assert controller._clock == "2027-01-04T00:00:00+00:00"
    products = execute(controller, "orchestrator", "products.read", {}, execution)
    assert products["status"] == "completed" and products["result"]["records"][0]["content"]["sku"] == "VEYRA-HUSH-ONE"
    reports = execute(controller, "performance", "reports.query", {"window": 1}, execution)
    assert reports["status"] == "pending" and not reports["result"]["records"]
    questions = execute(controller, "intent", "questions.read", {"window": 1}, execution)
    assert questions["status"] == "pending" and not questions["result"]["records"]


def test_source_population_excludes_answer_files_and_verifies_large_original_in_bounded_chunks():
    value, files, _ = proposal()
    paths = needed_files("GT2-R01")
    assert not any("agent_outputs" in path or "analysis_for_reviewers" in path or "expected" in path for path in paths)
    source = value["population_source_documents"]
    path = "cases/GT2-R01/daily_query_observations.jsonl"
    assert len(source[path]) > 1
    decoded = decode_sources("GT2-R01", source, value["source_hashes"])
    assert decoded[path] == files[path]
    changed = deepcopy(source)
    changed[path] = changed[path][:-1]
    with pytest.raises(ValueError, match="independently pinned"):
        decode_sources("GT2-R01", changed, value["source_hashes"])


def test_released_query_rows_preserve_actual_missingness_and_lineage_without_truncation():
    value, files, execution = proposal("GT2-R02")
    world = definition(value)
    controller = world.controller(0)
    controller.advance(world.windows[-1].instant.isoformat())
    expected = [json.loads(row) for row in files["cases/GT2-R02/daily_query_observations.jsonl"].splitlines()
                if json.loads(row)["locale"] == "en-US"]
    actual = [row["public"] for row in controller._initial["questions"] if "observed_count" in row["public"]]
    assert len(actual) == len(expected) == 2016
    assert digest(actual) == digest(expected)
    assert Counter(row["coverage"] for row in actual) == Counter(row["coverage"] for row in expected)
    sample = expected[0]
    reply = execute(controller, "intent", "questions.read", {"window": sample["week"],
                    "filters": {"date": sample["date"], "source": sample["source"]}}, execution)
    selected = [row for row in expected if row["date"] == sample["date"] and row["source"] == sample["source"]]
    assert reply["status"] == "completed" and [row["content"] for row in reply["result"]["records"]] == selected
    broad = execute(controller, "intent", "questions.read", {}, execution)
    assert broad["status"] == "unavailable" and broad["result"]["records_silently_truncated"] is False


def test_case_actor_projection_excludes_internal_runtime_and_private_outcome_metadata():
    value, _, _ = proposal()
    world = definition(value)
    rows = [row.public for collection, row in world.population()
            if collection == "documents" and row.source_path == "cases/GT2-R01/case.json"]
    assert len(rows) == 1
    assert set(rows[0]) == {"id", "case_id", "focus_locale", "campaign_id", "start", "end", "task", "review_scope"}
    assert rows[0]["campaign_id"] == world.campaign_context.campaign_ref
    assert "PRIVATE_CONDITIONAL" not in str(rows[0]) and "observed_primary_experiment_results" not in rows[0]


def test_real_source_questions_keep_original_unknown_labels_separate_from_fictional_observations():
    value, files, _ = proposal()
    world = definition(value)
    rows = [row.public for collection, row in world.population() if collection == "questions" and row.source_path == "sources/finequestions_selected.jsonl"]
    originals = [json.loads(line) for line in files["sources/finequestions_selected.jsonl"].splitlines()]
    assert len(rows) == len(originals) == 2000
    assert all({key: row[key] for key in original} == original for row, original in zip(rows, originals))
    assert all(row["source_label_status"] == "ORIGINAL_LABEL_DEFINITIONS_UNAVAILABLE_NOT_CAMPAIGN_OBSERVATIONS" for row in rows)
