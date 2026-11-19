"""Real SQL four-product software regressions, never runtime qualification.

Uses the repository's synthetic 200-row control pack and real registration,
known-case evaluator checks, immutable bindings and project RLS. No routing or
qualification-admission mocks; no native Trial, provider or model is dispatched.
"""

from collections import Counter
from copy import deepcopy
from uuid import uuid4

import psycopg
import pytest
from fastapi import HTTPException
from test_golden_kyc_anvil_sql import scoped
from test_golden_kyc_sql import connection
from test_golden_kyc_sql import owned as owned_fixture

from anvil.db import Jsonb, digest
from anvil.golden_kyc_anvil import PRODUCT_NAMES, application_assignments, register, start, validate
from anvil.golden_kyc_evaluators import CRITERIA
from anvil.praxis_case_dataset import CaseDataset, from_snapshots

owned = owned_fixture


@pytest.fixture
def product_import(owned):
    with scoped(owned, "app")() as c:
        public = register(c, owned[1], owned[2], owned[4], application_types=True)
        stored = c.execute("SELECT * FROM banking.anvil_imports WHERE id=%s", (public["id"],)).fetchone()
        validate(c, stored)
    return owned, public, stored


def test_four_products_conserve_every_original_and_share_exact_evaluators(product_import):
    owned, public, stored = product_import
    with scoped(owned, "app")() as c:
        assert register(c, owned[1], owned[2], owned[4], application_types=True)["id"] == public["id"]
        originals = c.execute("SELECT id,snapshot,snapshot_sha256 FROM banking.applications "
                              "WHERE project_id=%s AND pack_id=%s ORDER BY id", (owned[1], owned[4])).fetchall()
        group = c.execute("SELECT content FROM anvil.benchmark_task_groups WHERE id=%s",
                          (public["task_group_id"],)).fetchone()["content"]
        bindings = c.execute("SELECT * FROM anvil.environment_task_bindings WHERE project_id=%s AND environment_id=%s",
                             (owned[1], public["environment_id"])).fetchall()
        manifest = stored["manifest"]
        rows = manifest["case_assignments"]
        assert manifest["task_mode"] == "reusable_application_workflow"
        assert len(originals) == len(rows) == len({row["application_id"] for row in rows}) == 200
        assert manifest["case_dataset"]["case_count"] == 200
        assert {row["application_id"]: row["application_sha256"] for row in rows} == {
            row["id"]: row["snapshot_sha256"] for row in originals}
        by_id = {row["id"]: row for row in originals}
        for row in rows:
            original = by_id[row["application_id"]]
            assert row["product"] == original["snapshot"]["product"]
            assert row["task_id"] == "KYC-" + original["snapshot"]["product"]
            assert row["application_sha256"] == digest(original["snapshot"])
        assert {task["task_id"] for task in group["tasks"]} == {"KYC-" + p for p in PRODUCT_NAMES}
        assert len(group["tasks"]) == len(bindings) == public["binding_count"] == 4
        # The full shared catalogue remains 50: 20 rubric +10 business +10 OPA
        # safety +10 trace controls. Four products do not duplicate these rows.
        evaluators = manifest["evaluators"]
        assert len(evaluators) == public["evaluator_count"] == 50
        rubric = [row for row in evaluators if row["kind"] == "rubric"]
        assert len(rubric) == 20 and {row["requirement"] for row in rubric} == set(CRITERIA)
        assert len({row["configuration_id"] for row in evaluators}) == 50
        counts = Counter(row["product"] for row in rows)
        for binding in bindings:
            snapshot = binding["snapshot"]
            assert digest(snapshot) == binding["snapshot_sha256"]
            assert snapshot["evaluators"] == evaluators
            assert snapshot["case_dataset"] == manifest["case_dataset"]
            selector = snapshot["case_selector"]
            assert selector["field"] == "product"
            assert binding["task_id"] == "KYC-" + selector["value"]
            assert selector["case_count"] == counts[selector["value"]]
            assert snapshot["independent_expectation_review"] == "pending"
        assert sum(counts.values()) == 200 and set(counts) == set(PRODUCT_NAMES)
        assert public["readiness"]["model_benchmark"] == "blocked"


@pytest.mark.parametrize("mutation", ["omit", "duplicate", "wrong_product", "wrong_hash"])
def test_rehashed_manifest_cannot_filter_duplicate_or_reroute_originals(product_import, mutation):
    owned, _, stored = product_import
    changed = deepcopy(stored)
    assignments = changed["manifest"]["case_assignments"]
    if mutation == "omit":
        assignments.pop()
    elif mutation == "duplicate":
        assignments[-1] = deepcopy(assignments[0])
    elif mutation == "wrong_product":
        alternate = next(p for p in PRODUCT_NAMES if p != assignments[0]["product"])
        assignments[0].update(product=alternate, task_id="KYC-" + alternate)
    else:
        assignments[0]["application_sha256"] = "0" * 64
    # Pass the outer checksum to exercise the actual membership/routing check.
    changed["manifest_sha256"] = digest(changed["manifest"])
    with scoped(owned, "app")() as c, pytest.raises(HTTPException, match="membership or routing changed"):
        validate(c, changed)


def test_original_snapshot_routing_rejects_incomplete_and_unsupported_product(product_import):
    owned, _, stored = product_import
    with connection(owned) as c:
        originals = c.execute("SELECT id,snapshot,snapshot_sha256 FROM banking.applications "
                              "WHERE project_id=%s AND pack_id=%s ORDER BY id", (owned[1], owned[4])).fetchall()
    dataset = CaseDataset.model_validate(stored["manifest"]["case_dataset_manifest"])
    with pytest.raises(HTTPException, match="Complete original application membership"):
        application_assignments(dataset, originals[:-1])
    changed = deepcopy(originals)
    changed[0]["snapshot"]["product"] = "unsupported-synthetic-product"
    changed[0]["snapshot_sha256"] = digest(changed[0]["snapshot"])
    changed_dataset = from_snapshots(dataset.id, dataset.version, changed)
    with pytest.raises(HTTPException, match="exact supported original product"):
        application_assignments(changed_dataset, changed)


def test_shared_evaluator_tamper_revocation_and_binding_immutability(product_import):
    owned, public, stored = product_import
    changed = deepcopy(stored)
    changed["manifest"]["evaluators"][0]["configuration_sha256"] = "0" * 64
    changed["manifest_sha256"] = digest(changed["manifest"])
    with scoped(owned, "app")() as c, pytest.raises(HTTPException, match="Evaluator binding revoked or changed"):
        validate(c, changed)
    with pytest.raises(psycopg.Error), scoped(owned, "app")() as c:
        c.execute("UPDATE anvil.environment_task_bindings SET snapshot=%s WHERE project_id=%s AND environment_id=%s",
                  (Jsonb({"synthetic_tamper": True}), owned[1], public["environment_id"]))
    before = digest(stored["manifest"])
    with scoped(owned, "app")() as c:
        c.execute("INSERT INTO anvil.evaluator_revocations(id,project_id,configuration_id,created_by) VALUES(%s,%s,%s,%s)",
                  (uuid4(), owned[1], stored["manifest"]["evaluators"][0]["configuration_id"], owned[2]))
    with scoped(owned, "app")() as c, pytest.raises(HTTPException, match="Evaluator binding revoked or changed"):
        start(c, owned[1], owned[2], public["id"])
    with connection(owned) as c:
        actual = c.execute("SELECT manifest FROM banking.anvil_imports WHERE id=%s", (public["id"],)).fetchone()
        assert digest(actual["manifest"]) == before


def test_foreign_project_cannot_read_or_start_product_import(product_import):
    owned, public, _ = product_import
    foreign = str(uuid4())
    with scoped(owned, "app")() as c:
        c.execute("SELECT set_config('anvil.project',%s,true)", (foreign,))
        assert not c.execute("SELECT id FROM banking.anvil_imports WHERE id=%s", (public["id"],)).fetchall()
        with pytest.raises(HTTPException, match="Golden import not found"):
            start(c, foreign, owned[2], public["id"])
