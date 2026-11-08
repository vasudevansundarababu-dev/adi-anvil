"""Real PostgreSQL/API publication gates; these are not native pass evidence."""

from test_benchmark_pipeline import review_and_build
from test_benchmark_pipeline import signed_lab as pipeline_lab
from test_private_storage import lab as storage_lab

lab = storage_lab
signed_lab = pipeline_lab


def test_library_records_real_import_and_latest_build_without_private_payloads(signed_lab):
    case = signed_lab
    before = case["client"].get(case["base"] + "/library").json()["data"]
    assert len(before["items"]) == 1 and before["items"][0]["latest_build"] is None
    build, _ = review_and_build(case)
    response = case["client"].get(case["base"] + "/library?limit=1")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["next_cursor"] is None
    assert data["items"][0]["latest_build"]["build_id"] == build["build_id"]
    assert "private_canary" not in response.text and "eval_pack" not in response.text


def test_freeze_does_not_turn_build_or_signature_into_native_qualification(signed_lab):
    case = signed_lab
    build, _ = review_and_build(case)
    response = case["client"].post(case["base"] + "/builds/" + build["build_id"] + "/freeze",
                                   json={"expected_subject_sha256": build["subject_sha256"]})
    assert response.status_code == 409, response.text
    assert "native qualification" in response.text


def test_library_limit_is_bounded_and_other_project_receipts_are_hidden(signed_lab):
    case = signed_lab
    assert case["client"].get(case["base"] + "/library?limit=101").status_code == 422
    other = case["base"].replace(str(case["lab"]["project"]), str(case["lab"]["other_project"]))
    response = case["client"].get(other + "/library")
    assert response.status_code in (403, 404)
