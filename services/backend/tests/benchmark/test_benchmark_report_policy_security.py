"""Independent role/frozen-policy checks; synthetic humans are test identities only."""

import io
from uuid import uuid4

import psycopg
import pytest
from pypdf import PdfReader
from test_benchmark_golden import body as golden_body
from test_benchmark_golden import client as golden_client
from test_benchmark_golden import create as create_dataset
from test_benchmark_rehearsal_security import base, client, create, execute
from test_benchmark_rehearsal_security import enabled as rehearsal_enabled
from test_benchmark_rehearsal_security import lab as rehearsal_lab
from test_private_storage import assign, connection

lab = rehearsal_lab
enabled = rehearsal_enabled


def policy_url(lab):
    return base(lab).removesuffix("/rehearsals") + "/report-review-policy"


def configure(lab, count):
    response = client(lab, "admin").post(policy_url(lab), json={"required_reviewers": count})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def completed(lab, *, creator="engineer", executor="engineer"):
    draft = create(client(lab, creator), lab)
    response = execute(client(lab, executor), lab, draft)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def reviewer(lab, number):
    identity = "report_reviewer_" + str(number)
    identifier = str(uuid4())
    with connection() as c:
        c.execute(
            "INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,'independent-report-policy-test',%s,'Synthetic report reviewer')",
            (identifier, lab["org"], identifier),
        )
        c.execute(
            "INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,'rl-engineer')",
            (lab["project"], identifier),
        )
    lab[identity] = identifier
    return client(lab, identity), assign(lab, identity, scope="evaluation_review")


@pytest.mark.parametrize("count", [0, 1, 4])
def test_admin_configures_zero_one_or_n_distinct_reviewers_without_hardcoded_three(lab, count):
    configure(lab, count)
    saved = completed(lab)
    authorization = saved["report_authorization"]
    assert authorization["required_reviewers"] == count
    assert authorization["ready"] is (count == 0)
    assert authorization["reviewer_verified"] is False
    for number in range(count):
        c, duty = reviewer(lab, number)
        response = c.post(
            base(lab) + "/" + saved["id"] + "/report-review",
            json={
                "expected_result_sha256": saved["result"]["result_sha256"],
                "assignment_id": duty,
                "human_reviewed": True,
                "rationale": "Explicit independent synthetic reviewer test decision",
            },
        )
        assert response.status_code == 200, response.text
        authorization = response.json()["data"]
        assert authorization["completed_reviewers"] == number + 1
        assert authorization["ready"] is (number + 1 >= count)
        if number == 0:
            duplicate = c.post(
                base(lab) + "/" + saved["id"] + "/report-review",
                headers={"idempotency-key": str(uuid4())},
                json={
                    "expected_result_sha256": saved["result"]["result_sha256"],
                    "assignment_id": duty,
                    "human_reviewed": True,
                    "rationale": "Repeated same synthetic reviewer must not add a reviewer",
                },
            )
            assert duplicate.status_code in {200, 409}, duplicate.text
            assert (
                client(lab)
                .get(base(lab) + "/" + saved["id"])
                .json()["data"]["report_authorization"]["completed_reviewers"]
                == 1
            )
    if count:
        assert authorization["state"] == "reviewed" and authorization["reviewer_verified"]
    else:
        assert authorization["state"] == "policy_no_review"


def test_exemption_follows_actual_admin_executor_not_draft_creator(lab):
    configure(lab, 4)
    created_by_admin = completed(lab, creator="admin", executor="engineer")
    assert created_by_admin["report_authorization"]["state"] == "pending_review"
    executed_by_admin = completed(lab, creator="engineer", executor="admin")
    authority = executed_by_admin["report_authorization"]
    assert authority["state"] == "admin_run_exempt" and authority["ready"]
    assert authority["admin_actor_id"] == lab["admin"]
    assert not authority["reviewer_verified"] and authority["completed_reviewers"] == 0
    assert executed_by_admin["official_primary"] is None
    assert executed_by_admin["model_performance"] is False


def test_only_actual_admin_can_configure_or_approve_exact_immutable_result(lab):
    engineer = client(lab)
    assert engineer.post(policy_url(lab), json={"required_reviewers": 0}).status_code == 403
    assert (
        engineer.post(policy_url(lab), json={"required_reviewers": 0, "is_admin": True}).status_code
        == 422
    )
    saved = completed(lab)
    url = base(lab) + "/" + saved["id"] + "/report-approval"
    body = {
        "expected_result_sha256": saved["result"]["result_sha256"],
        "rationale": "Synthetic explicit Admin report release only",
    }
    assert engineer.post(url, json=body).status_code == 403
    admin = client(lab, "admin")
    assert admin.post(url, json={**body, "expected_result_sha256": "0" * 64}).status_code == 409
    response = admin.post(url, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "admin_approved"
    assert response.json()["data"]["ready"] and not response.json()["data"]["reviewer_verified"]
    assert response.json()["data"]["completed_reviewers"] == 0


def test_frozen_old_report_policy_is_not_rewritten_by_new_project_configuration(lab):
    configure(lab, 4)
    first = completed(lab)
    frozen = first["report_authorization"]["policy"]
    configure(lab, 0)
    fetched = client(lab).get(base(lab) + "/" + first["id"]).json()["data"]
    assert fetched["report_authorization"]["policy"] == frozen
    assert not fetched["report_authorization"]["ready"]
    assert completed(lab)["report_authorization"]["state"] == "policy_no_review"


def test_sql_engineer_cannot_forge_admin_report_authority(lab):
    saved = completed(lab)
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute(
                "INSERT INTO anvil.benchmark_report_admin_executions(id,project_id,target_kind,target_id,actor_id) VALUES(%s,%s,'rehearsal',%s,%s)",
                (str(uuid4()), lab["project"], saved["id"], lab["engineer"]),
            )
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute(
                "INSERT INTO anvil.benchmark_report_decisions(id,project_id,target_kind,target_id,result_sha256,actor_id,decision,rationale,human_reviewed) VALUES(%s,%s,'rehearsal',%s,%s,%s,'admin_approved','Attempted spoofed Admin report decision',true)",
                (
                    str(uuid4()),
                    lab["project"],
                    saved["id"],
                    saved["result"]["result_sha256"],
                    lab["admin"],
                ),
            )


def test_report_decisions_require_current_own_duty_and_cross_project_target_is_hidden(lab):
    saved = completed(lab)
    c, duty = reviewer(lab, 1)
    url = base(lab) + "/" + saved["id"] + "/report-review"
    body = {
        "expected_result_sha256": saved["result"]["result_sha256"],
        "assignment_id": duty,
        "human_reviewed": True,
        "rationale": "Explicit independent test report review decision",
    }
    assert client(lab).post(url, json=body).status_code == 403
    with connection() as db:
        db.execute(
            "INSERT INTO anvil.benchmark_private_revocations(project_id,assignment_id,revoked_by,rationale) VALUES(%s,%s,%s,'Synthetic test revoked reviewer duty')",
            (lab["project"], duty, lab["admin"]),
        )
    assert c.post(url, json=body).status_code == 403
    other = client(lab, "outsider")
    assert (
        other.post(url.replace(lab["project"], lab["other_project"]), json=body).status_code == 404
    )


def test_actual_pdf_is_blocked_until_exact_admin_authorization(lab):
    configure(lab, 4)
    engineer = client(lab)
    private_expected = "PRIVATE_EXPECTED_REPORT_EXCLUSION_" + uuid4().hex
    golden = golden_client(lab, "engineer")
    dataset = create_dataset(golden, policy_url(lab).removesuffix("/report-review-policy"))
    version = golden.post(
        policy_url(lab).removesuffix("/report-review-policy")
        + "/golden-datasets/"
        + dataset
        + "/versions",
        json=golden_body(expected_output=private_expected),
    )
    assert version.status_code == 201, version.text
    name = "Literal <b>scripted & fictional</b> report"
    response = engineer.post(base(lab), json={"name": name})
    assert response.status_code == 201, response.text
    saved = execute(engineer, lab, response.json()["data"]).json()["data"]
    params = {"expected_result_sha256": saved["result"]["result_sha256"], "template": "technical"}
    url = base(lab) + "/" + saved["id"] + "/report"
    assert engineer.get(url, params=params).status_code == 409
    approval = client(lab, "admin").post(
        base(lab) + "/" + saved["id"] + "/report-approval",
        json={
            "expected_result_sha256": saved["result"]["result_sha256"],
            "rationale": "Synthetic actual Admin report authorization test",
        },
    )
    assert approval.status_code == 200, approval.text
    assert (
        engineer.get(url, params={**params, "expected_result_sha256": "0" * 64}).status_code == 409
    )
    assert engineer.get(url, params={**params, "include_raw_prompts": "true"}).status_code == 403
    report = engineer.get(url, params=params)
    assert report.status_code == 200, report.text
    assert report.headers["content-type"].startswith("application/pdf")
    assert report.content[:4] == b"%PDF"
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(report.content)).pages)
    assert name in text
    assert "81" in text and saved["result"]["result_sha256"] in text
    normalized = " ".join(text.split())
    assert "No model inference" in normalized and "hidden reasoning" in normalized
    assert private_expected not in text


def test_actual_admin_execution_and_zero_policy_need_no_extra_pdf_approval(lab):
    configure(lab, 4)
    admin_run = completed(lab, executor="admin")
    configure(lab, 0)
    zero_run = completed(lab)
    c = client(lab)
    for row in (admin_run, zero_run):
        response = c.get(
            base(lab) + "/" + row["id"] + "/report",
            params={"expected_result_sha256": row["result"]["result_sha256"]},
        )
        assert response.status_code == 200, response.text
