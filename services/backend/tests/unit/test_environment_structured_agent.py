import hashlib
import json
from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from anvil import environment_structured_agent as agent
from anvil import harbor_agents, harbor_worker
from anvil.config import ROOT
from anvil.harbor_package import compile_package

RAW = (ROOT / "contracts/praxis/synthetic-marketing.task.json").read_bytes()


def test_source_and_output_contracts_refuse_guessed_bindings_and_ambiguous_json():
    task, manifest, _ = compile_package(RAW)
    assert agent.source_task(RAW, manifest).task_id == task.task_id
    for bad in (
        {**manifest, "binding": "component-guessed-v1"},
        {**manifest, "source_sha256": "0" * 64},
    ):
        with pytest.raises(ValueError):
            agent.source_task(RAW, bad)
    for text in ("[]", '{"a":1,"a":2}', "```json\n{}\n```", " " * 65537):
        with pytest.raises(ValueError):
            agent.output_value(text)


def test_disabled_path_never_touches_database_or_provider(monkeypatch):
    monkeypatch.delenv("ANVIL_HARBOR_HOST_MEDIATED_STRUCTURED_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="harbor_runtime_unavailable"):
        agent.process(None, None, None, None)


@pytest.mark.parametrize("origin", ["sdk_mock", "provider"])
@pytest.mark.parametrize("fault", [None, "unknown_dispatch", "changed_collected_bytes"])
def test_capture_uses_guarded_decision_then_separate_custody_before_original_grading(
    monkeypatch, tmp_path, origin, fault
):
    from anvil import environment_harbor, workspace_execution

    task, manifest, _ = compile_package(RAW)
    output = task.rubric.reference_output  # Manufactured response fixture, not a model result.
    text = json.dumps(output)
    calls, stored, finished = [], [], []
    row = {
        "id": "check",
        "candidate": "agent",
        "agent_plan_id": "plan",
        "cancel_requested": False,
        "invocation_count": 0,
    }
    record = {
        "id": "plan",
        "check_id": "check",
        "config": {
            "workspace_execution_group": "group",
            "episode_timeout_seconds": 60,
            "workspace_model": {"model_id": "synthetic-model"},
        },
    }

    class Connection:
        def execute(self, *args):
            pass

    @contextmanager
    def scoped(*args):
        yield Connection()

    monkeypatch.setenv("ANVIL_HARBOR_HOST_MEDIATED_STRUCTURED_ENABLED", "true")
    monkeypatch.setenv("ANVIL_HARBOR_DOCKER_HOST", "unix:///synthetic-test-only.sock")
    monkeypatch.setenv("ANVIL_ENVIRONMENT_HARBOR_PYTHON", "/synthetic/test/python")
    monkeypatch.setattr(harbor_worker, "scoped", scoped)
    monkeypatch.setattr(harbor_worker, "lease", lambda *args: None)
    monkeypatch.setattr(harbor_worker, "authorized", lambda *args: row)
    monkeypatch.setattr(harbor_worker, "check_workspace", lambda *args: tmp_path / "check")
    monkeypatch.setattr(harbor_agents, "plan", lambda *args: record)
    monkeypatch.setattr(agent.artifacts, "read", lambda *args: RAW)

    def store(c, project, data, *args, **kwargs):
        stored.append(data)
        return "artifact"

    monkeypatch.setattr(agent.artifacts, "store", store)

    def one(c, sql, params):
        if "praxis_sources" in sql:
            return {"source_artifact_id": "source"}
        if sql.startswith("SELECT 1"):
            return None
        return {
            "id": "call",
            "status": "completed",
            "output_json": {"text": text},
            "usage": {"dispatch_origin": origin},
        }

    monkeypatch.setattr(agent, "one", one)

    def decision(*args, **kwargs):
        calls.append((args, kwargs))
        if fault == "unknown_dispatch":
            raise RuntimeError("provider_output_or_usage_unknown_no_retry")
        return text

    monkeypatch.setattr(workspace_execution, "decision", decision)

    def native(folder, public_actor, callback, **kwargs):
        assert "PRIVATE" not in json.dumps(public_actor) and "reference_output" not in json.dumps(
            public_actor
        )
        result, receipt = callback()
        return {
            "collection": {
                "entries": [
                    {
                        "sha256": "0" * 64
                        if fault == "changed_collected_bytes"
                        else hashlib.sha256(
                            json.dumps(result, allow_nan=False).encode()
                        ).hexdigest()
                    }
                ]
            },
            "trusted_receipt": receipt,
        }

    monkeypatch.setattr(environment_harbor, "execute", native)
    monkeypatch.setattr(harbor_worker, "finish", lambda *args, **kwargs: finished.append(args[3]))
    args = (
        {"project_id": "project", "id": "job", "lease_token": "synthetic-lease"},
        "user",
        row,
        {"source_id": "source", "manifest": manifest, "package_sha256": "1" * 64},
    )
    if fault:
        with pytest.raises(RuntimeError, match="unknown_no_retry|verifier_evidence_mismatch"):
            agent.process(*args)
        assert len(calls) == 1 and not stored and not finished
        return
    agent.process(*args)
    assert len(calls) == 1 and calls[0][0] == ("project", "user", "plan", 0)
    assert len(stored) == 1 and len(finished) == 1
    result = finished[0]
    assert result["diagnostics"]["reward"] == 1
    assert result["evidence"][0]["sha256"] == hashlib.sha256(stored[0]).hexdigest()
    assert result["model_performance"] is (origin == "provider")
    assert result["provider_calls"] == (1 if origin == "provider" else 0)


def test_engineer_role_still_requires_live_admission(monkeypatch):
    row = {"agent_plan_id": "plan", "candidate": "agent"}
    monkeypatch.setattr(harbor_worker.auth, "project_roles", lambda *args: ["rl-engineer"])
    monkeypatch.setattr(
        harbor_worker,
        "one",
        lambda c, sql, params: (
            {"config": {"workspace_execution_group": "group"}} if "SELECT config" in sql else row
        ),
    )
    monkeypatch.setattr(harbor_agents, "plan", lambda *args: {})
    monkeypatch.setattr(harbor_agents, "readiness", lambda *args: {"ready": False})
    with pytest.raises(RuntimeError, match="live_agent_gates_revoked"):
        harbor_worker.authorized(None, {"project_id": "project", "target_id": "check"}, "user")
    monkeypatch.setattr(harbor_worker.auth, "project_roles", lambda *args: ["outsider"])
    with pytest.raises(HTTPException) as exc:
        harbor_worker.authorized(None, {"project_id": "project", "target_id": "check"}, "user")
    assert exc.value.status_code == 403
