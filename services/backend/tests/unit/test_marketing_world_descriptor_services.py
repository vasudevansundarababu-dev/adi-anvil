"""New pure service controls. Real supplied fixture bytes; manufactured requests.

No SQL/API/native/component/model benchmark or qualification is exercised here.
"""

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

from anvil.marketing_task2_contract import WIRE_ROLES
from anvil.marketing_task2_runtime import Task2Controller
from anvil.marketing_world_service_sources import CASE_FILES, SHARED_FILES, normalize
from anvil.marketing_world_services import descriptor_proposal
from anvil.praxis_generic_contract import digest


def source(case="GT2-R01"):
    root = Path(os.environ["ANVIL_MARKETING_SOURCE_FIXTURE_ROOT"])
    raw_pins = (root / "checksums.json").read_bytes()
    assert hashlib.sha256(raw_pins).hexdigest() == "59539b978994b472495f46786cf5085eae553230d2d7a2356acb165dea9d539a"
    pins = json.loads(raw_pins)
    paths = ["shared/" + name for name in SHARED_FILES]
    paths += [f"cases/{case}/" + name for name in CASE_FILES]
    paths += [f"reviewer_only/us-pair/{case}/reuse-test-{branch}/conditional_campaign_approval.json"
              for branch in ("positive", "null", "negative")]
    files = {path: (root / path).read_bytes() for path in paths}
    execution = json.loads((Path(__file__).parents[1] / "fixtures/veyra-template-execution-v3.json").read_text())
    return files, pins, execution, normalize(case, files, pins, execution)


def request(case="GT2-R01", *, content=None):
    files, pins, execution, sources = source(case)
    controller = Task2Controller(case, records={}, start="2027-02-12T12:00:00Z",
                                 outcome="positive", budget_minor=20000000)
    if content is None:
        content = {"service_contract": sources["schema_version"], "mode": "reuse_exact_descriptor",
                   "creative_refs": [{k: creative[k] for k in ("id", "version", "descriptor_sha256")}
                                     for creative in sources["case"]["approved_creative_catalogue"]]}
    token = controller.credential(WIRE_ROLES["brief"])
    saved = controller.call(token, controller.generation, "production-requests", {
        "id": "manufactured-request", "expected_version": 0, "idempotency_key": "new-service-control",
        "content": content,
    })
    inputs = {"production_request": {"request_ref": {"id": saved["id"], "version": saved["version"], "sha256": digest(saved)}}}
    node = next(n for n in execution["workflow_graph"]["nodes"] if n["id"] == "task3")
    return controller, execution, node, inputs, sources, saved


@pytest.mark.parametrize("case", ["GT2-R01", "GT2-R02"])
def test_source_exact_descriptors_never_create_media_approval_or_spend(case):
    controller, execution, node, inputs, sources, saved = request(case)
    before = deepcopy(controller.capture())
    result = descriptor_proposal(controller, execution, node, inputs, sources)
    assert result["status"] == "simulated_descriptor_return"
    assert len(result["deliveries"]) == 6
    assert result["request_ref"]["sha256"] == digest(saved)
    assert all(row["asset_bytes_exist"] is False and row["human_approval"] is False for row in result["deliveries"])
    assert result["campaign_authority_issued"] is False
    assert digest(controller.capture()) == digest(before)
    assert not controller._approvals and not controller._reservations


@pytest.mark.parametrize("case", ["GT2-R01", "GT2-R02"])
def test_changed_source_bytes_rejected_before_service_normalization(case):
    files, pins, execution, _ = source(case)
    files[f"cases/{case}/approved_creative_catalogue.json"] = b"[]"
    with pytest.raises(ValueError, match="independently pinned"):
        normalize(case, files, pins, execution)


def test_stale_request_cannot_select_a_descriptor_effect():
    controller, execution, node, inputs, sources, saved = request()
    controller.call(controller.credential(WIRE_ROLES["brief"]), controller.generation,
                    "production-requests", {"id": saved["id"], "expected_version": saved["version"],
                    "idempotency_key": "changed-control", "content": {"changed": True}})
    with pytest.raises(ValueError, match="Current stored request"):
        descriptor_proposal(controller, execution, node, inputs, sources)


def test_unavailable_creative_returns_hold_without_partial_delivery():
    _, _, _, sources = source()
    content = {"service_contract": sources["schema_version"], "mode": "reuse_exact_descriptor",
               "creative_refs": [{"id": "not-a-released-creative", "version": 1, "descriptor_sha256": "a" * 64}]}
    controller, execution, node, inputs, sources, _ = request(content=content)
    result = descriptor_proposal(controller, execution, node, inputs, sources)
    assert result["status"] == "hold" and result["deliveries"] == []
    assert result["issues"][0]["code"] == "descriptor_missing_or_ambiguous"
    assert controller._committed == controller._settled == 0


def test_quote_or_new_generation_does_not_become_delivery():
    controller, execution, node, inputs, sources, _ = request(content={"mode": "new_video", "quote_id": "GT2-R01_new_video_quote"})
    result = descriptor_proposal(controller, execution, node, inputs, sources)
    assert result["status"] == "hold" and not result["deliveries"]
    assert result["actual_media_generated"] is False


def test_expired_rights_prevent_descriptor_return():
    controller, execution, node, inputs, sources, _ = request()
    controller.advance("2027-04-01T00:00:00Z")
    result = descriptor_proposal(controller, execution, node, inputs, sources)
    assert result["status"] == "hold" and not result["deliveries"]
    assert {i["code"] for i in result["issues"]} == {"rights_scope_or_validity_mismatch"}
