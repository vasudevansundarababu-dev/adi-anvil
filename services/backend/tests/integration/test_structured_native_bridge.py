"""Real isolated SQL admission/accounting; only native transport and SDK are mocked."""

import hashlib
import json

import httpx
import pytest
from test_api_security import USERS
from test_workspace_adapter_contracts import response_body
from test_workspace_execution import configured as configured_fixture

from anvil import cli, environment_harbor, harbor_worker, workspace_execution
from anvil import environment_structured_agent as agent
from anvil.db import one, transaction

configured = configured_fixture


@pytest.mark.parametrize("fault", [None, "unknown_dispatch"])
def test_guarded_bridge_keeps_real_sql_intent_accounting_and_unknown(
    configured, monkeypatch, tmp_path, fault
):
    data = configured
    launched = data["post"]("/execution-groups/" + data["group"]["id"] + "/launch")
    member = launched["models"][0]
    with transaction(worker=True) as c:
        job = one(c, "SELECT * FROM anvil.claim_harbor_job()")
        assert str(job["target_id"]) == member["check"]["id"]
    with transaction(cli.PROJECT, USERS["admin-1"]) as c:
        row = one(c, "SELECT * FROM anvil.harbor_checks WHERE id=%s", (job["target_id"],))
        package = one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (row["package_id"],))
    monkeypatch.setenv("ANVIL_HARBOR_HOST_MEDIATED_STRUCTURED_ENABLED", "true")
    monkeypatch.setenv("ANVIL_HARBOR_DOCKER_HOST", "unix:///synthetic-sql-transport-only.sock")
    monkeypatch.setenv("ANVIL_ENVIRONMENT_HARBOR_PYTHON", "/synthetic/native/python")
    monkeypatch.setattr(harbor_worker, "check_workspace", lambda _: tmp_path / "native-check")
    native_calls = []

    def native(folder, actor, callback, **kwargs):
        native_calls.append(actor)
        output, receipt = callback()
        return {
            "collection": {
                "entries": [
                    {
                        "sha256": hashlib.sha256(
                            json.dumps(output, allow_nan=False).encode()
                        ).hexdigest()
                    }
                ]
            },
            "trusted_receipt": receipt,
        }

    monkeypatch.setattr(environment_harbor, "execute", native)
    wire = []

    def provider(request):
        wire.append(request)
        assert "PRIVATE-NORTHSTAR" not in request.content.decode()
        assert "reference_output" not in request.content.decode()
        if fault:
            raise httpx.ReadTimeout("synthetic post-dispatch uncertainty", request=request)
        return httpx.Response(
            200,
            json=response_body(
                member["model"]["provider"],
                '{"channel":"search","spend_usd":1000,"evidence_id":"ev-channel-costs"}',
            ),
        )

    transport = httpx.MockTransport(provider)
    if fault:
        with pytest.raises(RuntimeError, match="unknown_no_retry"):
            agent.process(job, row["created_by"], row, package, transport=transport)
        with transaction(cli.PROJECT, row["created_by"]) as c:
            call = one(
                c, "SELECT * FROM anvil.harbor_agent_calls WHERE plan_id=%s", (member["plan_id"],)
            )
            assert call["status"] == "execution_unknown" and call["actual_micro_usd"] is None
            assert call["reserved_micro_usd"] > 0
        with pytest.raises(RuntimeError, match="unknown_no_retry"):
            workspace_execution.decision(
                cli.PROJECT, row["created_by"], member["plan_id"], 0, transport=transport
            )
    else:
        agent.process(job, row["created_by"], row, package, transport=transport)
        with transaction(cli.PROJECT, row["created_by"]) as c:
            result = one(c, "SELECT * FROM anvil.harbor_checks WHERE id=%s", (row["id"],))
            call = one(
                c, "SELECT * FROM anvil.harbor_agent_calls WHERE plan_id=%s", (member["plan_id"],)
            )
            assert result["state"] == "succeeded" and result["invocation_count"] == 1
            assert result["result"]["model_performance"] is False
            assert result["result"]["origin"] == "native_sdk_mock_verification"
            assert (
                call["status"] == "completed"
                and 0 <= call["actual_micro_usd"] <= call["reserved_micro_usd"]
            )
    assert len(wire) == 1 and len(native_calls) == 1
