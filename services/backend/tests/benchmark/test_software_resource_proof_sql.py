"""Actual savepoint rollback and fresh authority with synthetic data only."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from test_golden_kyc_anvil_sql import scoped
from test_golden_kyc_sql import owned as owned_fixture

from anvil import qualification_resources
from anvil.golden_kyc_anvil import register, validate_software

owned = owned_fixture


def test_final_source_scan_failure_rolls_back_real_registration_writes(owned, monkeypatch):
    real_root = qualification_resources.qualification_root
    scans = []

    def fail_at_exit():
        scans.append(True)
        if len(scans) == 2:
            raise RuntimeError("synthetic engineering final-scan failure")
        return real_root()

    with scoped(owned, "app")() as c:
        before = c.execute("SELECT count(*) AS n FROM anvil.evaluator_configurations").fetchone()["n"]
        with monkeypatch.context() as fault:
            fault.setattr(qualification_resources, "qualification_root", fail_at_exit)
            with pytest.raises(RuntimeError, match="synthetic engineering"):
                register(c, owned[1], owned[2], owned[4], application_types=True)
        assert len(scans) == 2
        assert c.execute("SELECT count(*) AS n FROM anvil.evaluator_configurations").fetchone()["n"] == before
        assert not c.execute("SELECT id FROM banking.anvil_imports WHERE pack_id=%s", (owned[4],)).fetchall()
        assert not c.execute("SELECT id FROM anvil.environment_task_bindings").fetchall()
        # The connection remains usable; failure did not commit partial rows.
        assert c.execute("SELECT 1 AS ok").fetchone()["ok"] == 1


def test_software_validation_rescans_and_observes_current_revocations(owned, monkeypatch):
    real_root = qualification_resources.qualification_root
    scans = []

    def observed():
        scans.append(True)
        return real_root()

    with scoped(owned, "app")() as c:
        with monkeypatch.context() as count:
            count.setattr(qualification_resources, "qualification_root", observed)
            imported = register(c, owned[1], owned[2], owned[4], application_types=True)
            row = c.execute("SELECT * FROM banking.anvil_imports WHERE id=%s", (imported["id"],)).fetchone()
            assert len(scans) == 2
            validate_software(c, row)
            assert len(scans) == 4
            receipts = c.execute("SELECT evidence FROM anvil.evaluator_validation_receipts").fetchall()
            assert len(receipts) == 50 and sum(len(item["evidence"]["cases"]) for item in receipts) == 150
            assert all(item["evidence"]["passed"] for item in receipts)
            c.execute("INSERT INTO anvil.evaluator_revocations(id,project_id,configuration_id,created_by) VALUES(%s,%s,%s,%s)",
                      (str(uuid4()), owned[1], row["manifest"]["evaluators"][0]["configuration_id"], owned[2]))
            with pytest.raises(HTTPException, match="revoked or changed"):
                validate_software(c, row)
            # The rejected operation still starts a fresh real verification.
            assert len(scans) == 5
