import hashlib
import json

import pytest
from test_api_security import USERS
from test_praxis_harbor import BASE

from anvil.cli import PROJECT
from anvil.config import ROOT
from anvil.db import one, transaction, uid


@pytest.mark.parametrize(
    "path",
    sorted((ROOT / "contracts/praxis/golden-v3").glob("*.export.json")),
    ids=lambda p: p.stem,
)
def test_source_import_roundtrip_is_private_idempotent_and_never_claims_ready(client_factory, path):
    client, _ = client_factory("researcher")
    outsider, _ = client_factory("outsider")
    envelope = json.loads(path.read_text())
    payload = json.loads(envelope["payload_json"])
    payload["task_id"] += "-" + uid()[:8]
    envelope["payload_json"] = json.dumps(payload)
    envelope["payload_sha256"] = hashlib.sha256(envelope["payload_json"].encode()).hexdigest()
    before = {}
    with transaction(PROJECT, USERS["researcher"]) as c:
        before = {
            table: one(c, "SELECT count(*) n FROM anvil." + table)["n"]
            for table in (
                "harbor_packages",
                "harbor_agent_calls",
                "jobs",
                "evaluation_spend_windows",
            )
        }
    key = uid()
    headers = {"Idempotency-Key": key}
    result = client.post(
        BASE + "/praxis-sources", json={"payload": json.dumps(envelope)}, headers=headers
    )
    assert result.status_code == 200, result.text
    saved = result.json()["data"]
    assert saved["source_sha256"] == envelope["payload_sha256"]
    assert not saved["executable_import"]["ready"]
    assert saved["executable_import"]["model_calls"] == "not_started"
    assert payload["evaluation_private"]["canary"] not in result.text
    assert "expected_reward_bps" not in result.text and '"probe"' not in result.text
    assert (
        client.post(
            BASE + "/praxis-sources", json={"payload": json.dumps(envelope)}, headers=headers
        ).json()["data"]["id"]
        == saved["id"]
    )
    detail = client.get(BASE + "/workspace/tasks/" + saved["id"])
    assert detail.status_code == 200, detail.text
    assert payload["evaluation_private"]["canary"] not in detail.text
    assert outsider.get(BASE + "/workspace/tasks/" + saved["id"]).status_code == 404
    assert (
        client.post(
            BASE + "/praxis-sources/" + saved["id"] + "/build",
            json={},
            headers={"Idempotency-Key": uid()},
        ).status_code
        == 409
    )
    tampered = {**envelope, "payload_json": envelope["payload_json"] + " "}
    assert (
        client.post(
            BASE + "/praxis-sources",
            json={"payload": json.dumps(tampered)},
            headers={"Idempotency-Key": uid()},
        ).status_code
        == 422
    )
    with transaction(PROJECT, USERS["researcher"]) as c:
        assert {
            table: one(c, "SELECT count(*) n FROM anvil." + table)["n"] for table in before
        } == before
