"""Real SQL draft intake from the exact checksum-verified public SEED package."""

import os
from pathlib import Path

import pytest
from test_private_storage import connection
from test_private_storage import lab as storage_lab

from anvil import benchmark_project_import as projects
from anvil.praxis_contract import PraxisTask, grade
from anvil.praxis_seed_handoff import packages
from anvil.praxis_seed_policy import evaluate

lab = storage_lab
pytestmark = pytest.mark.skipif(
    not os.environ.get("ANVIL_TEST_SEED_HANDOFF_ROOT"),
    reason="Exact verified published SEED handoff required",
)


def test_published_drafts_import_idempotently_with_rls_and_no_approvals(lab):
    root = Path(os.environ["ANVIL_TEST_SEED_HANDOFF_ROOT"])
    files = {
        str(p.relative_to(root)): p.read_bytes()
        for p in (root / "seed-export").rglob("*")
        if p.is_file()
    }
    groups = packages(
        (root / "STATUS.md").read_bytes(),
        (root / "MANIFEST.sha256").read_bytes(),
        files,
        commit="bef6f49ebf1ad6c40f4fec0fea597cdc88c64743",
    )
    ids = []
    for group in groups:
        with connection("anvil_app", lab["project"], lab["engineer"]) as c:
            stored = projects.store(c, lab["project"], lab["engineer"], group["content"], None)
            again = projects.store(c, lab["project"], lab["engineer"], group["content"], None)
            assert stored["id"] == again["id"]
            ids.append(stored["id"])
            for task in group["content"]["tasks"]:
                assert task["source"]["provenance"]["review"]["status"] == "draft"
                assert "PRIVATE-" not in str(task["actor"])
                assert "reference_output" not in task["actor"]
        with connection("anvil_app", lab["other_project"], lab["outsider"]) as c:
            assert (
                c.execute(
                    "SELECT id FROM anvil.benchmark_task_groups WHERE id=%s", (ids[-1],)
                ).fetchone()
                is None
            )
    assert len(ids) == 5


def test_actual_seed_rule_bridge_keeps_unknown_and_original_grading():
    import json

    root = Path(os.environ["ANVIL_TEST_SEED_HANDOFF_ROOT"]) / "seed-export"
    index = json.loads((root / "index.json").read_text())
    unknown = 0
    for project in index["projects"]:
        policy = json.loads((root / project["policy_import"]).read_text())
        rules = [r for p in policy["policies"] for r in p["rules"]]
        for item in project["tasks"]:
            task = PraxisTask.model_validate_json((root / item["task"]).read_bytes())
            reference = task.rubric.reference_output
            assert grade(task, reference)["reward"] == 1
            observed = evaluate(task, rules, reference)
            assert all(r["outcome"] in {"pass", "unknown"} for r in observed)
            unknown += sum(r["outcome"] == "unknown" for r in observed)
            assert all(r["outcome"] == "unknown" for r in evaluate(task, rules, {}))
            assert all(r["human_approval_verified"] is False for r in observed)
    assert unknown >= 4
