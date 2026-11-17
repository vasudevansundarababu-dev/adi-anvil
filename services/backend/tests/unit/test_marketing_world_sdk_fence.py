"""Mocked current-receipt fence; no SQL/serving image/provider qualification."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_marketing_world_registry import setup

from anvil import marketing_capture_evidence_store, marketing_capture_store
from anvil.marketing_world_registry import require_sdk


def ready(monkeypatch):
    # This unit isolates the world-receipt fence after manufactured preflight.
    # The actual original capture profile/reservation have separate negative
    # tests; these mocks issue no persisted admission or native authority.
    monkeypatch.setattr(marketing_capture_store, "require_sdk_capture_budget", lambda *_: None)
    monkeypatch.setattr(
        marketing_capture_evidence_store,
        "require_reserved_manifest",
        lambda *_: {"origin": "manufactured_unit_control"},
    )
    body, _, row, plan = setup(monkeypatch)
    plan.update(id=str(uuid4()), created_by=str(uuid4()))
    source = row["value"]["source"]
    source.update(
        case_id=body["case_id"],
        case_snapshot_sha256=body["case_snapshot_sha256"],
        execution_sha256=body["execution_sha256"],
        rights_receipt_sha256=body["rights_receipt_sha256"],
    )
    claim = SimpleNamespace(
        plan_id=plan["id"], actor_id=plan["created_by"], job_id="job", lease_token="lease"
    )

    class Connection:
        value = row["value"]

        def execute(self, sql, parameters):
            self.parameters = parameters
            return self

        def fetchone(self):
            return {"value": self.value}

    return claim, plan, Connection()


def test_legacy_receipt_cannot_qualify_current_world_or_changed_serving_image(monkeypatch):
    claim, plan, c = ready(monkeypatch)
    with pytest.raises(RuntimeError, match="source_or_serving_image_changed"):
        require_sdk(c, claim, plan)
    assert c.parameters == ("job", "lease", plan["id"])
    monkeypatch.setenv("ANVIL_RUNTIME_IMAGE_DIGEST", "sha256:" + "0" * 64)
    with pytest.raises(RuntimeError, match="serving_image_changed"):
        require_sdk(c, claim, plan)


def test_missing_or_foreign_broker_claim_is_not_a_source_qualification(monkeypatch):
    claim, plan, c = ready(monkeypatch)
    with pytest.raises(RuntimeError, match="worker_broker_claim"):
        require_sdk(c, None, plan)
    claim.actor_id = str(uuid4())
    with pytest.raises(RuntimeError, match="worker_broker_claim"):
        require_sdk(c, claim, plan)


def test_missing_or_revoked_runtime_receipt_blocks_sdk_admission(monkeypatch):
    claim, plan, c = ready(monkeypatch)
    c.value = None
    with pytest.raises(RuntimeError, match="sdk_qualification_required"):
        require_sdk(c, claim, plan)
