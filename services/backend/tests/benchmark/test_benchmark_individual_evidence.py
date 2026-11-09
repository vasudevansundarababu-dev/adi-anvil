"""Real SQL/access routing; queued-only fixtures never claim native execution."""

import json

import pytest
from test_benchmark_pipeline import queued_operation, review_and_build
from test_benchmark_pipeline import signed_lab as signed_lab_fixture
from test_private_storage import assign, connection
from test_private_storage import lab as storage_lab

lab = storage_lab
signed_lab = signed_lab_fixture


@pytest.fixture
def individual(signed_lab):
    case = signed_lab
    assign(case["lab"], "admin")
    build, _ = review_and_build(case)
    queued = queued_operation(case, build)
    return (
        case,
        build,
        queued,
        case["base"] + "/qualification-operations/" + queued["operation_id"] + "/evidence",
    )


def test_queued_route_has_no_invented_capture_and_requires_evaluation_duty(individual):
    case, build, queued, url = individual
    r = case["admin"].get(url)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["qualifications"] == [] and d["state"] == "queued"
    assert (
        d["primary"] is None
        and d["model_performance"] is False
        and d["comparison_admitted"] is False
    )
    assert case["client"].get(url).status_code == 403
    foreign = url.replace(case["lab"]["project"], case["lab"]["other_project"])
    assert case["admin"].get(foreign).status_code in (403, 404)


@pytest.mark.parametrize(
    "fault",
    [
        "source_revoked",
        "evaluator_revoked",
        "duty_revoked",
        "signer_revoked",
        "author_inactive",
        "source_bytes_changed",
    ],
)
def test_current_source_duty_and_integrity_changes_deny_route(individual, fault):
    case, build, queued, url = individual
    assert case["admin"].get(url).status_code == 200
    if fault in ["source_revoked", "evaluator_revoked"]:
        response = case["admin"].post(
            case["base"] + "/reviews/" + build["review_id"] + "/revoke",
            json={
                "target": "review" if fault == "source_revoked" else "evaluator",
                "rationale": "Contract-only current access revocation",
            },
        )
        assert response.status_code == 200, response.text
    elif fault == "signer_revoked":
        trust = case["trust"]
        trust["keys"][0]["revoked"] = True
        case["trust_path"].write_text(json.dumps(trust))
    elif fault == "author_inactive":
        with connection() as c:
            c.execute(
                "UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s",
                (case["lab"]["project"], case["lab"]["engineer"]),
            )
    elif fault == "source_bytes_changed":
        from anvil import benchmark_pipeline as pipeline
        from anvil.benchmark_storage import read_private_record

        original = read_private_record

        def changed(metadata):
            data = original(metadata)
            if metadata["classification"] == "benchmark_raw":
                return b"changed-contract-archive"
            return data

        from unittest.mock import patch

        with patch.object(pipeline, "read_private_record", side_effect=changed):
            assert case["admin"].get(url).status_code == 409
        return
    else:
        with connection(project=case["lab"]["project"], user=case["lab"]["admin"]) as c:
            a = c.execute(
                "SELECT id FROM anvil.benchmark_private_assignments WHERE project_id=%s AND user_id=%s AND scope='evaluation_review'",
                (case["lab"]["project"], case["lab"]["admin"]),
            ).fetchone()
            c.execute(
                "INSERT INTO anvil.benchmark_private_revocations(project_id,assignment_id,revoked_by,rationale) VALUES(%s,%s,%s,'Contract-only duty revocation')",
                (case["lab"]["project"], a["id"], case["lab"]["admin"]),
            )
    assert case["admin"].get(url).status_code in (403, 409)


def test_real_native_individual_evidence_demo_preserves_actual_qa_authority(signed_lab):
    """Opt-in actual QA execution, no comparison or production/human approval."""
    import hashlib
    import os
    import stat
    from pathlib import Path

    from anvil.benchmark_pipeline import process_operation
    from anvil.config import ROOT

    if os.environ.get("ANVIL_TEST_HARBOR") != "1":
        pytest.skip("Explicit isolated native opt-in required; no individual execution claim")
    case = signed_lab
    # Existing fixture duties are test-only and remain distinct from user approval.
    build, _ = review_and_build(case)
    queued = queued_operation(case, build)
    assert (
        process_operation(case["lab"]["project"], queued["operation_id"], case["lab"]["admin"])
        == "passed"
    )
    url = case["base"] + "/qualification-operations/" + queued["operation_id"] + "/evidence"
    response = case["admin"].get(url)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["state"] == "passed" and len(data["qualifications"]) == 3
    assert (
        data["primary"] is None
        and data["comparison_admitted"] is False
        and data["model_performance"] is False
    )
    for qualification in data["qualifications"]:
        assert qualification["outcome"] == "passed" and len(qualification["trials"]) == 3
        for trial in qualification["trials"]:
            assert trial["provider_calls"] == 0
            assert trial["controls"] == {
                "fresh_actor": True,
                "non_root_readonly_no_egress_cgroups": True,
            }
            capture = trial["public_capture"]
            assert capture is not None and capture["criteria"]
            for output in capture["outputs"]:
                if output["text"] is not None:
                    raw = output["text"].encode()
                    assert len(raw) == output["byte_size"]
                    assert hashlib.sha256(raw).hexdigest() == output["sha256"]
            if trial["mode"] == "positive":
                assert capture["outputs"] and not capture["missing"]
    # The actual persisted endpoint must reopen identically, not synthesize a score.
    assert case["admin"].get(url).json()["data"] == data
    foreign = url.replace(case["lab"]["project"], case["lab"]["other_project"])
    assert case["admin"].get(foreign).status_code in (403, 404)
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM anvil.benchmark_comparisons WHERE project_id=%s",
                (case["lab"]["project"],),
            ).fetchone()["n"]
            == 0
        )
        review = c.execute(
            "SELECT expires_at FROM anvil.benchmark_source_reviews WHERE id=%s",
            (build["review_id"],),
        ).fetchone()
    destination = os.environ.get("ANVIL_TEST_EVIDENCE_DISCOVERY_PATH")
    if destination:
        path = Path(destination)
        if (
            not path.is_absolute()
            or not path.is_relative_to(ROOT / ".local")
            or path.parent.is_symlink()
        ):
            raise ValueError("Discovery manifest must use owned private test root")
        info = path.parent.stat()
        if (
            info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or path.parent.resolve() != path.parent
        ):
            raise ValueError("Discovery parent is not canonical owned0700")
        manifest = {
            "origin": "actual_original_synthetic_qa_execution_not_user_approval",
            "project_id": case["lab"]["project"],
            "operation_id": queued["operation_id"],
            "admin_id": case["lab"]["admin"],
            "build_id": build["build_id"],
            "review_id": build["review_id"],
            "review_expires_at": review["expires_at"].isoformat(),
            "public_trust_policy_path": str(case["trust_path"]),
            "public_trust_policy_sha256": hashlib.sha256(
                case["trust_path"].read_bytes()
            ).hexdigest(),
            "endpoint_response_sha256": hashlib.sha256(
                json.dumps(data, sort_keys=True).encode()
            ).hexdigest(),
            "comparison_admitted": False,
            "human_score_reviews_created": False,
        }
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(manifest, stream, sort_keys=True)
