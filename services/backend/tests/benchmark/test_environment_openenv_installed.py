"""Actual pinned OpenEnv class and authenticated WebSocket route, local SQL only."""

import pytest

pytest.importorskip("openenv", reason="Separate pinned OpenEnv trial runtime required")
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_private_storage import connection
from test_private_storage import lab as storage_lab

from anvil import environment_runtime as runtime
from anvil import environment_seeds as seeds
from anvil.environment_openenv_installed import ComponentAction, ComponentEnvironment, create_app

lab = storage_lab


def version(lab, template):
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        pack = runtime.pack_store(
            c,
            lab["project"],
            lab["engineer"],
            seeds.generate(template, seeds.CATALOG[template]["scenarios"][0]),
        )
        return runtime.create_version(
            c, lab["project"], lab["engineer"], pack["id"], "Actual OpenEnv " + template
        )


@pytest.mark.parametrize("template", list(seeds.CATALOG))
def test_installed_openenv_episode_mutates_resets_and_preserves_original_scoring(lab, template):
    item = version(lab, template)

    def factory():
        return connection("anvil_app", lab["project"], lab["engineer"])

    a = ComponentEnvironment(lab["project"], lab["engineer"], item["id"], factory)
    b = ComponentEnvironment(lab["project"], lab["engineer"], item["id"], factory)
    first = a.reset(seed=1)
    before = b.state.state_sha256
    action = ComponentAction(
        operation="list_records",
        arguments={"collection": seeds.CATALOG[template]["collections"][0]},
        expected_generation=a.state.generation,
    )
    observation = a.step(action, timeout_s=5)
    assert observation.reward is None and observation.metadata["anvil_score"] is None
    assert observation.result["result"]["status"] == "ok"
    assert a.state.step_count == 1 and b.state.state_sha256 == before
    with pytest.raises(ValueError):
        a.reset(seed=2)
    after = a.reset(seed=1)
    assert after.result["state"] == first.result["state"] and a.state.step_count == 0
    a.close()
    b.close()


def test_real_openenv_websocket_authentication_schemas_reset_step_and_isolation(lab):
    item = version(lab, "BNK-KYC")

    def connections():
        return connection("anvil_app", lab["project"], lab["engineer"])

    app = create_app(
        lambda: ComponentEnvironment(lab["project"], lab["engineer"], item["id"], connections),
        "synthetic-local-openenv-token-1234567890",
    )
    with TestClient(app) as client:
        assert client.get("/schema").status_code == 401
        headers = {"Authorization": "Bearer synthetic-local-openenv-token-1234567890"}
        schema = client.get("/schema", headers=headers)
        assert schema.status_code == 200, schema.text
        assert "expected_generation" in schema.text
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws"):
                pass
        with (
            client.websocket_connect("/ws", headers=headers) as a,
            client.websocket_connect("/ws", headers=headers) as b,
        ):
            a.send_json({"type": "reset", "data": {"seed": 1}})
            initial = a.receive_json()
            assert initial["type"] == "observation", initial
            b.send_json({"type": "reset", "data": {"seed": 1}})
            assert b.receive_json()["type"] == "observation"
            a.send_json({"type": "state"})
            state = a.receive_json()
            generation = state["data"]["generation"]
            b.send_json({"type": "state"})
            other = b.receive_json()
            assert other["data"]["episode_id"] != state["data"]["episode_id"]
            a.send_json(
                {
                    "type": "step",
                    "data": {
                        "operation": "request_information",
                        "arguments": {
                            "case_id": "case",
                            "reason": "Actual OpenEnv websocket request",
                        },
                        "expected_generation": generation,
                    },
                }
            )
            result = a.receive_json()
            assert result["type"] == "observation", result
            assert (
                result["data"]["reward"] is None
                and result["data"]["observation"]["metadata"]["anvil_score"] is None
            )
            b.send_json({"type": "state"})
            assert b.receive_json()["data"]["step_count"] == 0
            a.send_json({"type": "reset", "data": {"seed": 1}})
            assert a.receive_json()["type"] == "observation"
            a.send_json({"type": "state"})
            assert a.receive_json()["data"]["step_count"] == 0
