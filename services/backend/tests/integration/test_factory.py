import psycopg
import pytest
from test_api_security import USERS, client_factory  # noqa: F401

from anvil.db import transaction, uid


def test_factory_vertical_versions_rights_and_access(client_factory, monkeypatch, journey):  # noqa: F811
    project = journey["project_id"]
    base = f"/api/v1/projects/{project}/factory"
    researcher = client_factory("researcher")[0]

    def post(path, body, status=200, key=None):
        r = researcher.post(base + path, json=body, headers={"Idempotency-Key": key or uid()})
        assert r.status_code == status, r.text
        return r.json().get("data")

    selection = {
        "objective_revision_id": journey["objective"]["current_revision_id"],
        "task_revision_ids": journey["suite"]["content"]["task_revision_ids"],
    }
    preview = post("/profile-preview", selection)
    assert preview["heterogeneity"]
    assert "Separate populations" in preview["segmentation_advice"]
    dims = preview["dimensions"] | {"subdomain": ["business-diagnostics"]}
    body = selection | {"title": "Synthetic catalog integration", "dimensions": dims}
    key = uid()
    profile = post("/profiles", body, key=key)
    assert post("/profiles", body, key=key) == profile
    post("/profiles", body | {"title": "changed"}, 409, key=key)
    catalog = post("/benchmarks", body)
    assert catalog["lifecycle"] == "registered"
    assert catalog["content"]["readiness"] == "metadata_only"
    request = {"profile_revision_id": profile["current_revision_id"], "threshold": 75}
    rec = post("/recommendations", request)
    assert rec["content"] == post("/recommendations", request)["content"]
    match = next(
        b for b in rec["content"]["ranked"] if b["revision_id"] == catalog["current_revision_id"]
    )
    assert match["total_score"] == 100
    assert match["task_coverage"]["selected_tasks"] == 3
    select = {
        "recommendation_revision_id": rec["current_revision_id"],
        "benchmark_revision_ids": [catalog["current_revision_id"]],
        "title": "Factory integration suite",
        "advisor_id": USERS["advisor"],
        "override_reason": "Select the exact test catalog revision, retaining development-only limits.",
    }
    suite = post("/suite-drafts", select)
    assert suite["lifecycle"] == "draft"
    assert set(suite["content"]["task_revision_ids"]) == set(selection["task_revision_ids"])
    assert suite["content"]["benchmark_revision_ids"] == select["benchmark_revision_ids"]
    bad = select | {"benchmark_revision_ids": [uid()]}
    post("/suite-drafts", bad, 422)
    gap = post(f"/recommendations/{rec['current_revision_id']}/gap-draft", {})
    assert gap["lifecycle"] == "draft"
    assert gap["content"]["dimensions"] == dims
    excluded = post("/recommendations", request)
    assert any(
        b["revision_id"] == gap["current_revision_id"] and "metadata_not_registered" in b["reasons"]
        for b in excluded["content"]["excluded"]
    )
    for name in ("advisor", "data-engineer", "sales"):
        assert client_factory(name)[0].post(base + "/profiles", json=body).status_code == 200
    assert client_factory("outsider")[0].get(base).status_code == 404
    with transaction(project, USERS["researcher"]) as c:
        original_hash = c.execute(
            "SELECT content_hash FROM anvil.revisions WHERE id=%s",
            (profile["current_revision_id"],),
        ).fetchone()["content_hash"]
        with pytest.raises(psycopg.Error):
            with c.transaction():
                c.execute(
                    "UPDATE anvil.revisions SET content='{}' WHERE id=%s",
                    (profile["current_revision_id"],),
                )
        assert (
            c.execute(
                "SELECT content_hash FROM anvil.revisions WHERE id=%s",
                (profile["current_revision_id"],),
            ).fetchone()["content_hash"]
            == original_hash
        )
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.revision_links WHERE revision_id=%s AND relation='benchmark'",
                (suite["current_revision_id"],),
            ).fetchone()["n"]
            == 1
        )
    # Different modality is excluded rather than silently invoking another adapter.
    unsupported = post(
        "/benchmarks",
        body
        | {"title": "Unsupported image contract", "dimensions": dims | {"modality": ["image"]}},
    )
    result = post("/recommendations", request)
    assert any(
        x["revision_id"] == unsupported["current_revision_id"]
        and "incompatible_modality" in x["reasons"]
        for x in result["content"]["excluded"]
    )
    from anvil import factory

    with monkeypatch.context() as patch:
        patch.setattr(factory.domain, "rights_ok", lambda *args: False)
        filtered = post("/recommendations", request)
        assert not filtered["content"]["ranked"]
        assert any(
            "rights_not_approved_for_local_fixture" in x["reasons"]
            for x in filtered["content"]["excluded"]
        )
        post("/suite-drafts", select, 409)
    with monkeypatch.context() as patch:
        patch.setattr(factory, "LIMIT", 0)
        post("/recommendations", request, 409)
    readback = researcher.get(base + "/recommendations/" + rec["current_revision_id"])
    assert readback.status_code == 200
    assert readback.json()["data"]["content"] == rec["content"]
    # Generic suite creation must preserve the same version and override gates.
    forged = suite["content"] | {"task_revision_ids": [uid()]}
    response = researcher.post(
        f"/api/v1/projects/{project}/suites", json=forged, headers={"Idempotency-Key": uid()}
    )
    assert response.status_code == 409
    response = researcher.post(
        f"/api/v1/projects/{project}/suites",
        json=suite["content"] | {"benchmark_revision_ids": []},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 422
