"""Installed, synthetic non-spending software controls; never qualification.

Run with the installed interpreter -I -B, readonly root, network none and a
writable bounded /tmp. No database, Docker socket, provider or operator secrets.
"""
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def require(condition):
    if not condition:
        raise ValueError("Synthetic control assertion failed")


def main():
    results = {}

    def control(name, operation):
        try:
            results[name] = {"status": "passed", "observation": operation()}
        except Exception as error:
            # Preserve all failures without leaking ambient configuration.
            results[name] = {"status": "failed", "exception_type": type(error).__name__}

    def custody():
        require(sys.flags.isolated == 1 and sys.dont_write_bytecode)
        forbidden = [key for key, value in os.environ.items() if value and (
            "DATABASE" in key or key.endswith(("API_KEY", "PRIVATE_KEY", "ACCESS_TOKEN"))
            or key in {"DOCKER_HOST", "DOCKER_CONFIG", "GOOGLE_APPLICATION_CREDENTIALS"})]
        require(not forbidden)
        require(not Path("/var/run/docker.sock").exists())
        return {"isolated_interpreter": True, "database_provider_docker_credentials_supplied": False}

    control("credential_and_interpreter_custody", custody)
    if results["credential_and_interpreter_custody"]["status"] != "passed":
        print(json.dumps({"schema_version": "anvil.synthetic-component-controls.v1", "controls": results,
                          "native_qualified": False, "model_calls_authorized": 0, "actual_model_calls": None}))
        return 1

    versions = {}
    for package, expected in (("mcp", "1.30.0"), ("zen-engine", "2.1.3")):
        def pinned(package=package, expected=expected):
            actual = importlib.metadata.version(package)
            versions[package] = actual
            require(actual == expected)
            return {"version": actual}
        control("version_" + package, pinned)

    def mcp_controls():
        from anvil.golden_mcp_client import McpEpisode

        class Episode:
            credentials = {"generation": 0}

            def __init__(self):
                self.calls = []

            def step(self, action):
                self.calls.append(action.operation)
                return SimpleNamespace(result={"status": "completed", "synthetic_fixture": True}, done=False)

        episode = Episode()
        with McpEpisode(episode, {"generation": 0, "label": "synthetic-component-control"}, lambda: True,
                        action_factory=lambda **kw: SimpleNamespace(**kw)) as mediator:
            action = SimpleNamespace(operation="policy.read", arguments={}, expected_generation=0)
            require(mediator.step(action).result == {"status": "completed", "synthetic_fixture": True})
            observations = {"valid_read": True}
            for name, arguments, meta in (
                ("wrong_capability", {}, {"anvil_session": "synthetic-wrong", "scope_sha256": mediator.scope_hash}),
                ("invalid_schema", {"unexpected": True}, mediator.meta),
            ):
                async def rejected(arguments=arguments, meta=meta):
                    return await mediator.session.call_tool("policy.read", arguments, meta=meta)
                require(mediator.portal.call(rejected).isError)
                observations[name] = "denied"
            require(episode.calls == ["policy.read"])
            episode.credentials = {"generation": 1}
            try:
                mediator.step(action)
            except ValueError:
                observations["stale_generation"] = "denied"
            else:
                raise ValueError("Stale generation accepted")
            require(episode.calls == ["policy.read"])
            return observations | {"transport_receipt": mediator.public_receipt(),
                                   "sql_episode": False, "reset_scope": "synthetic generation rotation only"}

    control("mcp_stdio_auth_schema_generation", mcp_controls)

    def opa_controls():
        from anvil.policy_rules import Rule, evaluate_opa
        path = Path(os.environ["ANVIL_OPA_BINARY"])
        expected = os.environ["ANVIL_OPA_SHA256"]
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected)
        version = subprocess.run([str(path), "version"], capture_output=True, timeout=5,
                                 env={"PATH": "/usr/bin:/bin", "DO_NOT_TRACK": "1"}, check=True)
        require(len(version.stdout) <= 8192 and version.stdout.decode().splitlines()[0] == "Version: 1.22.2")
        rule = Rule(kind="equals", field="synthetic_supported", value=True)
        actual = [evaluate_opa(rule, facts, path, expected_sha256=expected)["outcome"]
                  for facts in ({"synthetic_supported": True}, {"synthetic_supported": False}, {})]
        require(actual == ["pass", "fail", "unknown"])
        return {"outcomes": actual, "binary_sha256": expected, "version": "1.22.2",
                "missing_evidence": "production preflight returns unknown before invoking engine"}

    def zen_controls():
        from anvil.policy_rules import Rule, evaluate_zen
        rule = Rule(kind="equals", field="synthetic_supported", value=True)
        actual = [evaluate_zen(rule, facts)["outcome"]
                  for facts in ({"synthetic_supported": True}, {"synthetic_supported": False}, {})]
        require(actual == ["pass", "fail", "unknown"])
        return {"outcomes": actual,
                "missing_evidence": "production preflight returns unknown before invoking engine"}

    control("opa_pass_fail_missing", opa_controls)
    control("zen_pass_fail_missing", zen_controls)
    hashes = {"script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    for name in ("anvil.golden_mcp_client", "anvil.golden_mcp_server", "anvil.policy_rules"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "__file__", None):
            hashes[name] = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    from anvil.golden_kyc_source import source_hash

    output = {"schema_version": "anvil.synthetic-component-controls.v1", "fixture": "labelled synthetic in-memory",
              "controls": results, "versions": versions, "source_hashes": hashes,
              "golden_source_sha256": source_hash(),
              "native_qualified": False, "qualification_written": False,
              "model_calls_authorized": 0, "actual_model_calls": None,
              "limitations": ["No SQL, OpenEnv reset, Harbor Trial, physical role mounts, checkpoint recovery or private grading exercised.",
                              "Network isolation must be supplied by the container operator; script does not attest it."]}
    print(json.dumps(output, sort_keys=True))
    return 0 if all(item["status"] == "passed" for item in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
