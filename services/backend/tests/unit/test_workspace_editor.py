import pytest
from fastapi import HTTPException

from anvil import domain
from anvil.schemas import Decision
from anvil.workspace_editor import RevisionPatch, merge, public_content


def test_rubric_patch_keeps_private_anchors_and_calibration_without_returning_them():
    content = {
        "title": "Original rubric",
        "threshold": 70.0,
        "criteria": [
            {
                "id": "one",
                "label": "Original",
                "weight_bps": 10000,
                "anchors": {"0": "PRIVATE-ANCHOR"},
            }
        ],
        "calibration": {"private": "PRIVATE-CALIBRATION"},
    }
    changed = merge(
        "rubric",
        content,
        RevisionPatch(
            threshold=75.0, criteria=[{"id": "one", "label": "Edited label", "weight_bps": 10000}]
        ),
    )
    assert changed["criteria"][0]["anchors"] == content["criteria"][0]["anchors"]
    assert changed["calibration"] == content["calibration"]
    assert "PRIVATE" not in str(public_content("rubric", changed))
    assert content["threshold"] == 70
    with pytest.raises(HTTPException):
        merge(
            "rubric",
            content,
            RevisionPatch(criteria=[{"id": "other", "label": "Bad", "weight_bps": 10000}]),
        )
    with pytest.raises(HTTPException):
        merge(
            "rubric",
            content,
            RevisionPatch(criteria=[{"id": "one", "label": "Bad", "weight_bps": 9000}]),
        )


def test_protected_fields_and_cross_kind_fields_are_rejected():
    with pytest.raises(ValueError):
        RevisionPatch(title="Allowed", reference_artifact_ids=["private"])
    with pytest.raises(HTTPException):
        merge("task", {"title": "Task"}, RevisionPatch(threshold=50.0))


def test_self_approval_tracks_actual_revision_author_after_admin_edit(monkeypatch):
    monkeypatch.setattr(domain, "get_revision", lambda *args: {"created_by": "current-author"})
    monkeypatch.setattr(domain, "product_owners", lambda *args: ["current-author", "other-owner"])
    resource = {
        "id": "resource",
        "project_id": "project",
        "kind": "rubric",
        "lifecycle": "submitted",
        "created_by": "old-author",
        "current_revision_id": "new-revision",
    }
    with pytest.raises(HTTPException) as exc:
        domain.decide(
            None,
            resource,
            "current-author",
            {"product-owner"},
            Decision(
                purpose="approval",
                decision="approve",
                rationale="Must enforce actual current authorship",
            ),
        )
    assert exc.value.status_code == 409 and "Another Product Owner" in exc.value.detail
