import json

import pytest
from test_api_security import USERS

from anvil import domain
from anvil.config import ROOT
from anvil.db import one, transaction, uid


@pytest.mark.parametrize("kind", ["task", "rubric", "protocol"])
def test_successor_is_canonical_draft_with_cas_private_field_preservation_and_history(
    client_factory, kind
):
    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    project = journey["project_id"]
    base = f"/api/v1/projects/{project}"
    with transaction(project, USERS["researcher"]) as c:
        original_protocol = domain.get_revision(
            c, journey["protocol"]["current_revision_id"], "protocol"
        )
        suite = domain.get_revision(c, original_protocol["content"]["suite_revision_id"], "suite")
        task = domain.get_revision(c, suite["content"]["task_revision_ids"][0], "task")
        original = {
            "task": task,
            "rubric": domain.get_revision(c, task["content"]["rubric_revision_id"], "rubric"),
            "protocol": original_protocol,
        }[kind]
        clone = domain.create(
            c,
            project,
            USERS["researcher"],
            kind,
            {**original["content"], "title": "Test-only editor " + kind},
        )
        original_revision = clone["current_revision_id"]
        original_content = clone["content"]
    admin, _ = client_factory("admin-1")
    path = base + f"/workspace/revisions/{original_revision}"
    before = admin.get(path + "/editor")
    assert before.status_code == 200, before.text
    assert before.json()["data"]["can_save"]
    assert "reference_artifact_ids" not in before.text and '"anchors"' not in before.text
    assert '"calibration"' not in before.text and "reviewer_ids" not in before.text
    body = {"title": "Edited test-only " + kind}
    if kind == "rubric":
        body["threshold"] = 75.0
    if kind == "protocol":
        body["comparison_policy"] = "Updated descriptive policy for this version only."
    assert admin.post(path + "/successor", json=body).status_code == 428
    assert (
        admin.post(path + "/successor", json=body, headers={"If-Match": "999"}).status_code == 412
    )
    key = uid()
    headers = {"If-Match": str(before.json()["data"]["row_version"]), "Idempotency-Key": key}
    saved = admin.post(path + "/successor", json=body, headers=headers)
    assert saved.status_code == 200, saved.text
    newer = saved.json()["data"]
    assert newer["revision"] == 2 and newer["lifecycle"] == "draft"
    assert newer["content"]["title"] == body["title"]
    assert (
        admin.post(path + "/successor", json=body, headers=headers).json()["data"]["revision_id"]
        == newer["revision_id"]
    )
    historical = admin.get(path + "/editor").json()["data"]
    assert (
        not historical["can_save"] and historical["content"]["title"] == original_content["title"]
    )
    assert (
        admin.post(
            path + "/successor",
            json=body,
            headers={"If-Match": str(newer["row_version"]), "Idempotency-Key": uid()},
        ).status_code
        == 409
    )
    history = admin.get(base + f"/workspace/resources/{clone['id']}/versions?limit=1").json()[
        "data"
    ]
    assert history["items"][0]["revision"] == 2 and history["next_cursor"] == 2
    with transaction(project, USERS["admin-1"]) as c:
        old = domain.get_revision(c, original_revision)
        new = domain.get_revision(c, newer["revision_id"])
        assert old["content"] == original_content
        assert str(new["created_by"]) == USERS["admin-1"]
        for field in (
            "reference_artifact_ids",
            "actor_artifact_ids",
            "calibration",
            "reviewer_ids",
            "connection_hash",
        ):
            if field in original_content:
                assert new["content"][field] == original_content[field]
        assert not one(
            c, "SELECT 1 FROM anvil.review_decisions WHERE revision_id=%s", (newer["revision_id"],)
        )
        assert one(
            c,
            "SELECT 1 FROM anvil.revision_links WHERE revision_id=%s AND target_revision_id=%s AND relation='supersedes'",
            (newer["revision_id"], original_revision),
        )
    outsider, _ = client_factory("outsider")
    assert outsider.get(path + "/editor").status_code == 404
    advisor, _ = client_factory("advisor")
    assert advisor.get(path + "/editor").status_code == 200
    assert not advisor.get(path + "/editor").json()["data"]["can_save"]
    assert (
        advisor.post(
            base + f"/workspace/revisions/{newer['revision_id']}/successor",
            json=body,
            headers={"If-Match": str(newer["row_version"])},
        ).status_code
        == 403
    )
    admin.headers.pop("X-CSRF-Token")
    assert (
        admin.post(
            base + f"/workspace/revisions/{newer['revision_id']}/successor", json=body
        ).status_code
        == 403
    )


def test_approved_revision_decision_stays_on_old_hash_after_successor(client_factory):
    journey = json.loads((ROOT / "artifacts/test-runs/journey.json").read_text())
    project = journey["project_id"]
    base = f"/api/v1/projects/{project}"
    with transaction(project, USERS["researcher"]) as c:
        task = domain.get_revision(c, journey["suite"]["content"]["task_revision_ids"][0], "task")
        rubric = domain.get_revision(c, task["content"]["rubric_revision_id"], "rubric")
        clone = domain.create(
            c,
            project,
            USERS["researcher"],
            "rubric",
            {**rubric["content"], "title": "Test-only reviewed successor"},
        )
    researcher, _ = client_factory("researcher")
    owner, _ = client_factory("admin-1")
    admin, _ = client_factory("admin-1")
    submitted = researcher.post(
        base + f"/rubrics/{clone['id']}/submit",
        json={},
        headers={"If-Match": str(clone["row_version"]), "Idempotency-Key": uid()},
    )
    assert submitted.status_code == 200, submitted.text
    approved = owner.post(
        base + f"/rubrics/{clone['id']}/decisions",
        json={
            "purpose": "approval",
            "decision": "approve",
            "rationale": "Independent synthetic test review; not paid or human validity authority.",
        },
        headers={
            "If-Match": str(submitted.json()["data"]["row_version"]),
            "Idempotency-Key": uid(),
        },
    )
    assert approved.status_code == 200, approved.text
    old = approved.json()["data"]
    changed = admin.post(
        base + f"/workspace/revisions/{old['current_revision_id']}/successor",
        json={"title": "New unapproved draft"},
        headers={"If-Match": str(old["row_version"]), "Idempotency-Key": uid()},
    )
    assert changed.status_code == 200 and changed.json()["data"]["lifecycle"] == "draft"
    with transaction(project, USERS["admin-1"]) as c:
        decisions = c.execute(
            "SELECT d.revision_id,d.subject_hash FROM anvil.review_decisions d JOIN anvil.revisions v ON v.id=d.revision_id WHERE v.resource_id=%s",
            (clone["id"],),
        ).fetchall()
        assert (
            len(decisions) == 1 and str(decisions[0]["revision_id"]) == old["current_revision_id"]
        )
        assert decisions[0]["subject_hash"] == old["content_hash"]
