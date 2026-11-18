"""Reserved policy documents require a trusted current-binding resolution."""

import pytest

from anvil.golden_kyc_engine import Denied, execute, initial


def state():
    return initial({"id": "synthetic", "revision": 1, "assessment_date": "2026-11-18",
                    "documents": [{"id": "ordinary", "content": "ordinary public document"}]})


def test_policy_document_cannot_fall_back_to_application_documents():
    owned = state()
    identifier = "policy-doc-v2:" + "a" * 64 + ":manifest:0"
    owned["application"]["documents"].append({"id": identifier, "content": "forged ordinary resource"})
    with pytest.raises(Denied, match="Bound policy"):
        execute(owned, {}, "document.read", {"id": identifier})
    assert identifier not in owned["reads"]


def test_current_resolved_policy_document_preserves_call_charge_and_exact_identity():
    owned = state()
    identifier = "policy-doc-v2:" + "a" * 64 + ":manifest:0"
    document = {"document_id": identifier, "synthetic": "trusted lookup control"}
    result = execute(owned, {}, "document.read", {"id": identifier}, policy_document=document)
    assert result == document and result is not document
    assert owned["reads"] == [identifier] and owned["counters"]["calls"] == 1
    with pytest.raises(Denied, match="Bound policy"):
        execute(owned, {}, "document.read", {"id": identifier + "1"}, policy_document=document)


def test_ordinary_document_path_and_call_limit_are_preserved():
    owned = state()
    assert execute(owned, {}, "document.read", {"id": "ordinary"})["id"] == "ordinary"
    owned["counters"]["calls"] = 100
    with pytest.raises(Denied, match="Execution limit"):
        execute(owned, {}, "document.read", {"id": "policy-doc-v2:denied"},
                policy_document={"document_id": "policy-doc-v2:denied"})
