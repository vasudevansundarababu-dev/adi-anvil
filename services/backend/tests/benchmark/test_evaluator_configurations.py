"""Real isolated SQL/API checks, not live account or model evidence."""

import json
from uuid import uuid4

import psycopg
import pytest
from test_benchmark_pipeline import login
from test_private_storage import connection
from test_private_storage import lab as storage_lab

lab = storage_lab


def base(lab, project=None):
    return f"/api/v1/projects/{project or lab['project']}/workspace/evaluators"


def create(client, lab, **changes):
    body = {
        "name": "Fictional amount cap",
        "adapter": "zen",
        "rule": {"kind": "number_max", "field": "amount", "value": 100},
    }
    return client.post(base(lab), json=body | changes, headers={"idempotency-key": str(uuid4())})


@pytest.mark.parametrize("identity", ["admin", "engineer"])
@pytest.mark.parametrize(
    "adapter,version",
    [
        ("builtin", "anvil-evaluator-v1"),
        ("zen", "2.1.3"),
        ("opa-local", "1.22.2"),
        ("nemo", "0.24.1"),
        ("promptfoo", "0.125.1"),
    ],
)
def test_both_roles_persist_and_actually_validate_local_runtime(lab, identity, adapter, version):
    client = login(lab, identity)
    text_rule = adapter in {"nemo", "promptfoo"}
    response = create(
        client,
        lab,
        adapter=adapter,
        rule={"kind": "forbidden_text", "field": "text", "value": "forbidden"}
        if text_rule
        else {"kind": "number_max", "field": "amount", "value": 100},
    )
    assert response.status_code == 201, response.text
    row = response.json()["data"]
    assert row["status"] == "needs_testing"
    cases = {
        "cases": [
            {
                "facts": {"text": "allowed workflow"} if text_rule else {"amount": 100},
                "expected": "pass",
            },
            {
                "facts": {"text": "forbidden export"} if text_rule else {"amount": 101},
                "expected": "fail",
            },
            {"facts": {}, "expected": "unknown"},
        ]
    }
    response = client.post(
        base(lab) + "/" + row["id"] + "/test", json=cases, headers={"idempotency-key": str(uuid4())}
    )
    assert response.status_code == 200, response.text
    tested = response.json()["data"]
    assert tested["status"] == "ready"
    assert tested["validation"]["evidence"]["runtime_version"] == version
    assert tested["validation"]["evidence"]["provider_calls"] == 0
    assert client.get(base(lab)).json()["data"]["items"][0]["id"] == row["id"]
    assert "secret_ref" not in json.dumps(tested)
    with connection(project=lab["project"], user=lab[identity]) as c:
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.evaluator_validation_receipts WHERE configuration_id=%s",
                (row["id"],),
            ).fetchone()["n"]
            == 1
        )
    revoke = client.post(base(lab) + "/" + row["id"] + "/revoke")
    assert revoke.status_code == 200 and revoke.json()["data"]["status"] == "revoked"
    assert client.post(base(lab) + "/" + row["id"] + "/test", json=cases).status_code == 409


def test_wrong_cases_never_ready_and_other_project_hidden(lab):
    client = login(lab, "engineer")
    row = create(client, lab).json()["data"]
    cases = {
        "cases": [
            {"facts": {"amount": 100}, "expected": "fail"},
            {"facts": {"amount": 101}, "expected": "pass"},
            {"facts": {}, "expected": "unknown"},
        ]
    }
    response = client.post(
        base(lab) + "/" + row["id"] + "/test", json=cases, headers={"idempotency-key": str(uuid4())}
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "needs_testing"
    outsider = login(lab, "outsider")
    assert outsider.get(base(lab)).status_code == 404
    assert (
        outsider.post(
            base(lab, lab["other_project"]) + "/" + row["id"] + "/test", json=cases
        ).status_code
        == 404
    )


def test_history_immutable_even_via_app_database_role(lab):
    row = create(login(lab, "engineer"), lab).json()["data"]
    with pytest.raises(psycopg.Error):
        with connection(role="anvil_app", project=lab["project"], user=lab["engineer"]) as c:
            c.execute(
                "UPDATE anvil.evaluator_configurations SET name='rewritten' WHERE id=%s",
                (row["id"],),
            )


def test_csrf_and_unprovisioned_api_endpoint_rejected_without_calls(lab):
    client = login(lab, "engineer")
    client.headers["x-csrf-token"] = "wrong"
    assert create(client, lab).status_code == 403
    client = login(lab, "engineer")
    response = create(
        client,
        lab,
        adapter="arthur",
        rule=None,
        endpoint="https://unprovisioned.example",
        resource_id=str(uuid4()),
        secret="synthetic-unit-key",
    )
    assert response.status_code == 422, response.text
    assert "synthetic-unit-key" not in response.text
