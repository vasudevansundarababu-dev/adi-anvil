"""OpenEnv adapter units (plan decision 1b, Part A): the `studio-openenv` recipe, admission, the episode session over
Studio's routes, and the qualification checks. An in-memory simulator stands in for the container; no Docker."""

import hashlib
import json
import time

import pytest

from anvil.rlgym.common import GymError
from anvil.rlgym.runs import openenv, worker

DIGEST = "sha256:" + "5" * 64
SEED = "c" * 64
SPEC = "d" * 64


def _env(**recipe):
    base = {
        "kind": "studio-openenv",
        "image_ref": "adi-utility-local/golden-kyc-openenv:abc",
        "image_digest": DIGEST,
        "port": 8080,
        "environment_key": "golden-kyc-openenv",
        "spec_sha256": SPEC,
        "qualification": {
            "read_operation": "application.read",
            "fixtures": ["kyc-individual-001", "kyc-individual-002"],
            "write_call": {"operation_id": "finding.write", "arguments": {"issue": "probe"}},
        },
    }
    return {
        "id": "golden-kyc-openenv@9",
        "image_digest": DIGEST,
        "seed_sha256": SEED,
        "image_recipe": {**base, **recipe},
    }


class Sim:
    """Studio's simulator routes, in memory. `broken_reset` keeps writes across a reset."""

    def __init__(self, broken_reset=False, key="golden-kyc-openenv"):
        self.gen, self.writes, self.pending, self.calls = 0, [], {}, 0
        self.broken_reset, self.key = broken_reset, key

    def _sha(self, rows):
        return hashlib.sha256(json.dumps(rows).encode()).hexdigest()

    def ready(self):
        return {
            "ready": True,
            "environment_key": self.key,
            "seed_sha256": SEED,
            "spec_sha256": SPEC,
            "reset_generation": self.gen,
            "episode_id": f"ep-{self.gen}",
        }

    def call(self, method, path, body=None):
        if path == "/healthz":
            return {"status": 200, "body": {"status": "ok"}}
        if path == "/readyz":
            return {"status": 200, "body": self.ready()}
        if path == "/state":
            return {
                "status": 200,
                "body": {
                    "reset_generation": self.gen,
                    "writes": len(self.writes),
                    "pending": len(self.pending),
                    "tool_calls": self.calls,
                    "state_sha256": self._sha(self.writes),
                    "seed_state_sha256": self._sha([]),
                },
            }
        if path == "/reset":
            sealed = self.calls
            self.gen += 1
            self.calls = 0
            self.pending = {}
            if not self.broken_reset:
                self.writes = []
            return {
                "status": 200,
                "body": {
                    "observation": self.ready(),
                    "info": {
                        "sealed_generation": self.gen - 1,
                        "sealed_sha256": "e" * 64,
                        "sealed_tool_events": sealed,
                    },
                },
            }
        if path == "/step":
            g = body.get("reset_generation")
            if g is not None and g != self.gen:
                return {"status": 409, "body": {"code": "CONFLICT", "message": "wrong generation"}}
            op, args = body["action"]["operation_id"], body["action"]["arguments"]
            self.calls += 1
            if op == "application.read":
                out = {
                    "status": "completed",
                    "records": [
                        {"application_id": "kyc-individual-001"},
                        {"application_id": "kyc-individual-002"},
                    ],
                }
                state, pending = "completed", None
            elif op == "finding.write":
                self.writes.append(args)
                out, state, pending = {"status": "completed", "id": "f1"}, "completed", None
            elif op == "identity.check":
                key = args.get("idempotency_key")
                if key in self.pending:
                    del self.pending[key]
                    out, state, pending = (
                        {"status": "completed"},
                        "completed",
                        {"calls_remaining": 0},
                    )
                else:
                    self.pending[key] = 1
                    out, state, pending = None, "pending", {"calls_remaining": 1}
            else:
                return {
                    "status": 422,
                    "body": {"code": "UNDECLARED_TOOL", "message": f"{op} is not declared"},
                }
            return {
                "status": 200,
                "body": {
                    "observation": {
                        "state": state,
                        "output": out,
                        "pending": pending,
                        "sequence": self.calls,
                    },
                    "done": False,
                },
            }
        return {"status": 404, "body": {"code": "NOT_FOUND"}}


class FakeSession:
    def __init__(self, sim):
        self.sim, self.deadline, self.closed = sim, time.monotonic() + 30, False

    def request(self, q):
        return self.sim.call(q["method"], q["path"], q.get("body"))

    def close(self):
        self.closed = True


def _bridge(sim):
    return openenv.Bridge(None, 8080, None, session=FakeSession(sim))


def test_the_recipe_must_be_complete_and_agree_with_the_released_digest():
    assert openenv.recipe(_env())["health_path"] == "/healthz"
    with pytest.raises(GymError) as missing:
        openenv.recipe(_env(qualification={"read_operation": "application.read"}))
    assert "qualification.fixtures" in missing.value.details["missing"]
    with pytest.raises(GymError) as differs:
        openenv.recipe(_env(image_digest="sha256:" + "6" * 64))
    assert (
        differs.value.code == "HASH_MISMATCH"
    )  # the recipe cannot move the released, immutable image_digest
    with pytest.raises(GymError):
        openenv.recipe(
            _env(image_digest="adi-utility-local/golden-kyc-openenv:latest")
        )  # a tag, not a digest
    with pytest.raises(GymError):
        openenv.recipe(_env(ready_path="http://elsewhere/readyz"))
    assert not openenv.is_openenv({"image_recipe": {"server": "golden_kyc_env.py"}})


def test_admission_lists_every_identity_difference():
    env, rec = _env(), openenv.recipe(_env())
    assert openenv.admit(env, rec, Sim().ready()) == {}
    wrong = openenv.admit({**env, "seed_sha256": "0" * 64}, rec, Sim(key="other").ready())
    assert set(wrong) == {"environment_key", "seed_sha256"}
    assert wrong["seed_sha256"] == {"registered": "0" * 64, "observed": SEED}
    # Without a stated spec hash only the key and the seed are compared (the version's spec hash is the registry's).
    rec_no_spec = openenv.recipe(_env(spec_sha256=None))
    assert "spec_sha256" not in openenv.expected_identity(env, rec_no_spec)


def test_an_episode_steps_on_its_own_generation_and_seals_with_studios_hash():
    sim = Sim()
    rec = openenv.recipe(_env())
    s = openenv.OpenEnvSession(None, rec, None, bridge=_bridge(sim))
    reset = s.request({"op": "reset", "case_id": "kyc-individual-001", "inject": None})
    assert reset["ok"] and reset["reset_generation"] == 1
    assert s.request({"op": "call", "tool": "finding.write", "args": {"issue": "x"}})["ok"]
    first = s.request({"op": "call", "tool": "identity.check", "args": {"idempotency_key": "k"}})
    assert first["ok"] and first["state"] == "pending"
    assert (
        s.request({"op": "call", "tool": "identity.check", "args": {"idempotency_key": "k"}})[
            "state"
        ]
        == "completed"
    )
    refused = s.request({"op": "call", "tool": "application.write", "args": {}})
    assert refused == {
        "ok": False,
        "error": "UNDECLARED_TOOL",
        "message": "application.write is not declared",
    }
    state = s.request({"op": "state"})
    assert state["writes"] == 1 and state["driver"] == "studio-openenv"
    assert state["studio_sealed"] == {"generation": 1, "sealed_sha256": "e" * 64, "tool_events": 4}
    # The next episode starts clean: nothing written in the last one survives.
    s2 = openenv.OpenEnvSession(None, rec, None, bridge=_bridge(sim))
    s2.request({"op": "reset"})
    assert s2.request({"op": "state"})["writes"] == 0


def test_a_step_on_a_stale_generation_is_refused_not_bound_to_the_wrong_episode():
    sim = Sim()
    s = openenv.OpenEnvSession(None, openenv.recipe(_env()), None, bridge=_bridge(sim))
    s.request({"op": "reset"})
    sim.call("POST", "/reset")  # someone else reset the simulator
    out = s.request({"op": "call", "tool": "finding.write", "args": {}})
    assert out["ok"] is False and out["error"] == "CONFLICT"


def test_a_server_error_is_infrastructure_and_retried():
    class Down(Sim):
        def call(self, method, path, body=None):
            return (
                {"status": 0, "error": "URLError"}
                if path == "/step"
                else super().call(method, path, body)
            )

    s = openenv.OpenEnvSession(None, openenv.recipe(_env()), None, bridge=_bridge(Down()))
    s.request({"op": "reset"})
    with pytest.raises(RuntimeError):
        s.request({"op": "call", "tool": "finding.write", "args": {}})


def test_qualification_runs_identity_and_the_six_checks():
    env, rec = _env(), openenv.recipe(_env())
    checks, failure = openenv.run_checks(_bridge(Sim()), env, rec)
    assert failure is None
    assert [c["name"] for c in checks] == [
        "identity",
        "health",
        "known_fixtures",
        "write_state",
        "reset",
        "state_cleared",
        "pending_cleared",
    ]
    assert all(c["result"] == "pass" for c in checks)


def test_qualification_catches_a_reset_that_keeps_writes():
    env, rec = _env(), openenv.recipe(_env())
    checks, failure = openenv.run_checks(_bridge(Sim(broken_reset=True)), env, rec)
    assert failure == "environment_defect"
    assert checks[-1]["name"] == "state_cleared" and checks[-1]["result"] == "fail"
    assert checks[-1]["likely_cause"] == openenv.LIKELY_CAUSE["state_cleared"]


def test_qualification_stops_at_identity_on_a_different_simulator():
    checks, failure = openenv.run_checks(
        _bridge(Sim(key="someone-else")), _env(), openenv.recipe(_env())
    )
    assert failure == "environment_defect" and [c["name"] for c in checks] == ["identity"]
    assert "environment_key" in checks[0]["evidence"]["mismatches"]


def test_the_runner_drives_a_mock_episode_through_the_adapter():
    env = _env()
    sim = Sim()
    rec = openenv.recipe(env)
    episode = {
        "id": "e1",
        "run_id": "r",
        "kind": "case",
        "system_id": "m",
        "case_id": "kyc-individual-001",
        "task_id": "t",
        "task_revision": 1,
        "attempt": 1,
        "tries": 1,
        "ts_prompt_id": None,
    }
    manifest = {
        "manifest": {
            "models": [
                {
                    "system_id": "m",
                    "version": 1,
                    "model_id": "mock/diligent-v1",
                    "provider": "mock",
                    "config_sha256": "x",
                }
            ],
            "execution_mode": "controlled_mock",
            "note": "synthetic",
            "environment": {"version_id": env["id"]},
        },
        "manifest_sha256": "y",
    }
    instance = {"container": "c", "local_image_id": DIGEST, "env": env}
    bundle = worker.execute(
        episode,
        {"episode_timeout_s": 20},
        manifest,
        instance,
        {"assignment": "Review kyc-individual-001"},
        lambda: openenv.OpenEnvSession(None, rec, None, bridge=_bridge(sim)),
    )
    assert bundle["environment"]["driver"] == "studio-openenv"
    assert bundle["synthetic"] and bundle["cost_usd"] == 0
    assert bundle["environment_state"]["studio_sealed"]["sealed_sha256"] == "e" * 64
    # Until B1 the mock agents name the stub's tools; Studio refuses those it does not declare, and that is recorded.
    assert any(
        t["observation"].get("error") == "UNDECLARED_TOOL"
        for t in bundle["transcript"]
        if "tool" in t
    )


class Sim7(Sim):
    """golden-kyc-openenv@7 shape: application.read requires application_id and returns that one record; a call
    without it is refused as SCHEMA_INVALID. GET /operations carries the input schema."""

    def call(self, method, path, body=None):
        if path == "/operations":
            return {
                "status": 200,
                "body": {
                    "operations": [
                        {
                            "operation_id": "application.read",
                            "input_schema": {
                                "type": "object",
                                "properties": {"application_id": {"type": "string"}},
                                "required": ["application_id"],
                            },
                        }
                    ]
                },
            }
        if path == "/step" and body["action"]["operation_id"] == "application.read":
            app_id = body["action"]["arguments"].get("application_id")
            if not app_id:
                return {
                    "status": 422,
                    "body": {"code": "SCHEMA_INVALID", "message": "application_id required"},
                }
            self.calls += 1
            return {
                "status": 200,
                "body": {
                    "observation": {
                        "state": "completed",
                        "output": {
                            "status": "completed",
                            "count": 1,
                            "records": [{"application_id": app_id}],
                        },
                        "pending": None,
                        "sequence": self.calls,
                    },
                    "done": False,
                },
            }
        return super().call(method, path, body)


def test_qualification_reads_each_fixture_by_id_when_the_read_requires_it():
    env, rec = _env(), openenv.recipe(_env())
    checks, failure = openenv.run_checks(_bridge(Sim7()), env, rec)
    fixtures = next(c for c in checks if c["name"] == "known_fixtures")
    assert fixtures["result"] == "pass" and fixtures["evidence"]["read_by"] == "application_id"
    assert fixtures["evidence"]["found"] == ["kyc-individual-001", "kyc-individual-002"]
    assert failure is None


def test_qualification_keeps_the_listing_read_without_an_id_argument():
    checks, _ = openenv.run_checks(_bridge(Sim()), _env(), openenv.recipe(_env()))
    fixtures = next(c for c in checks if c["name"] == "known_fixtures")
    assert fixtures["result"] == "pass" and fixtures["evidence"]["read_by"] == "listing"


def test_mock_studio_agent_reads_by_id_on_v7_and_is_unchanged_on_v6():
    from anvil.rlgym.systems import mock_provider as mp

    app = {"application_id": "kyc-adult-joint-006", "revision": 1, "submitted_at": "2026-11-01"}
    docs = [
        {
            "party_id": "kyc-adult-joint-006-p1",
            "document_id": "d1",
            "kind": "government_id",
            "content": {},
        },
        {
            "party_id": "kyc-adult-joint-006-p1",
            "document_id": "d2",
            "kind": "proof_of_address",
            "content": {},
        },
    ]

    def drive(v7):
        g = mp.studio_agent("mock/diligent-v1", "k", "kyc-adult-joint-006")
        action, calls = next(g), []
        for _ in range(60):
            calls.append((action.get("tool"), action.get("args")))
            if "final" in action:
                break
            tool, args = action["tool"], action.get("args") or {}
            if tool == "application.read":
                obs = (
                    {"ok": False, "error": "SCHEMA_INVALID"}
                    if v7 and not args
                    else {"ok": True, "output": {"records": [app]}}
                )
            elif tool == "documents.list":
                if v7 and not args:
                    obs = {"ok": False, "error": "SCHEMA_INVALID"}
                else:
                    obs = {"ok": True, "output": {"records": docs}}
            elif tool == "parties.list":
                obs = {"ok": True, "output": {"records": [{"party_id": "kyc-adult-joint-006-p1"}]}}
            else:
                obs = {"ok": True, "state": "completed", "output": {"status": "completed"}}
            action = g.send(obs)
        return calls

    v6 = drive(False)
    assert v6[0] == ("application.read", {}) and v6[1] == ("documents.list", {})
    assert not any(t == "parties.list" for t, _ in v6)
    v7 = drive(True)
    assert ("application.read", {"application_id": "kyc-adult-joint-006"}) in v7
    assert ("parties.list", {"application_id": "kyc-adult-joint-006"}) in v7
    assert ("documents.list", {"party_id": "kyc-adult-joint-006-p1"}) in v7
    assert v7[-1][0] is None or "final" in str(v7[-1])
