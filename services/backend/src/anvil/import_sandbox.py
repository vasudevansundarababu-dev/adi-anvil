"""Disposable supplied-image MCP execution and separate trusted-image generated-code tests.

Only the dedicated Docker worker imports this module. No provider credentials enter a
container, and generated code is never executed by the API or worker interpreter.
"""

import json
import math
import os
import re
import select
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from anvil.config import ROOT
from anvil.import_codegen import SAFE_BUILTINS, score

TRUSTED_IMAGE = "python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e"


def docker_env():
    from anvil.harbor_worker import child_environment

    folder = ROOT / ".local/import-worker-home"
    folder.mkdir(mode=0o700, exist_ok=True)
    return child_environment(folder)


def docker(args, *, timeout=30, data=None):
    result = subprocess.run(
        ["docker", *args],
        input=data,
        capture_output=True,
        timeout=timeout,
        env=docker_env(),
        check=False,
    )
    if result.returncode:
        # Never echo raw container/provider content in operational errors.
        raise RuntimeError("Docker operation failed: " + args[0])
    if len(result.stdout) > 2_000_000:
        raise RuntimeError("Container response exceeds bound")
    return result.stdout


def schema_check(value, schema):
    """Deliberately supported JSON-schema subset; unknown keywords fail qualification."""
    allowed = {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "description",
        "title",
    }
    if set(schema) - allowed:
        raise ValueError(
            "Unsupported tool/output schema keyword: " + ",".join(sorted(set(schema) - allowed))
        )
    kind = schema.get("type")
    matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "number": type(value) in (int, float) and math.isfinite(value),
        "boolean": type(value) is bool,
        "null": value is None,
    }
    if kind and not matches.get(kind, False):
        raise ValueError("Tool/output schema type mismatch")
    if (
        "enum" in schema
        and value not in schema["enum"]
        or "const" in schema
        and value != schema["const"]
    ):
        raise ValueError("Tool/output schema value mismatch")
    if isinstance(value, dict):
        if not set(schema.get("required", [])) <= set(value):
            raise ValueError("Required tool/output field missing")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in props:
                schema_check(item, props[key])
            elif extra is False:
                raise ValueError("Unexpected tool/output field")
            elif isinstance(extra, dict):
                schema_check(item, extra)
    if isinstance(value, list):
        for item in value:
            schema_check(item, schema.get("items", {}))
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 100000):
            raise ValueError("Array length outside schema")
    if isinstance(value, str) and (
        len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1048576)
    ):
        raise ValueError("String length outside schema")
    if type(value) in (int, float) and (
        value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf)
    ):
        raise ValueError("Number outside schema")


RUNNER = """import json,sys
request=json.load(sys.stdin)
safe={k:__builtins__.__dict__[k] for k in request['builtins']}
namespace={'__builtins__':safe}
exec(compile(request['code'],'rules.py','exec'),namespace)
args=request['args']
result=namespace[request['function']](*args)
print(json.dumps(result,allow_nan=False,separators=(',',':')))
"""


def execute_code(bundle, function, args):
    payload = json.dumps(
        {"code": bundle.code, "builtins": SAFE_BUILTINS, "function": function, "args": args},
        allow_nan=False,
    ).encode()
    name = "anvil-rules-" + uuid4().hex
    try:
        raw = docker(
            [
                "run",
                "--name",
                name,
                "--rm",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=32",
                "--cpus=1",
                "--memory=128m",
                "--memory-swap=128m",
                "--user=10001:10001",
                "-i",
                TRUSTED_IMAGE,
                "python3",
                "-I",
                "-c",
                RUNNER,
            ],
            timeout=8,
            data=payload,
        )
        return json.loads(raw)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Generated rule exceeded isolated execution timeout") from None
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name], env=docker_env(), capture_output=True, timeout=10
        )


def input_values(task, *, private=False):
    return {
        a.path: json.loads(a.content) if a.media_type == "application/json" else a.content
        for a in task.inputs
        if a.visibility == "actor" or private
    }


class Environment:
    def __init__(self, task, existing=None):
        self.task = task
        self.existing = existing
        self.name = existing or "anvil-import-" + uuid4().hex
        self.processes = {}
        self.counter = 0
        self.temporary = None

    def __enter__(self):
        task = self.task
        actual = json.loads(docker(["image", "inspect", task.environment.image_reference]))[0]
        if task.environment.digest_kind == "docker_image_id":
            if actual["Id"] != task.environment.digest:
                raise ValueError("Supplied Docker image ID does not match source")
        elif not any(
            d.endswith("@" + task.environment.digest) for d in actual.get("RepoDigests", [])
        ):
            raise ValueError("Supplied OCI manifest digest is unavailable locally")
        image = actual["Id"]
        if self.existing:
            if not re.fullmatch(r"[a-f0-9]{64}", self.existing):
                raise ValueError("Invalid Harbor container identity")
            container = json.loads(docker(["inspect", self.existing]))[0]
            if (
                container["Image"] != image
                or not container["HostConfig"]["ReadonlyRootfs"]
                or container["HostConfig"]["NetworkMode"] != "none"
            ):
                raise ValueError("Harbor container does not match qualified isolation/image")
        self.temporary = tempfile.TemporaryDirectory(prefix="anvil-public-inputs-")
        folder = Path(self.temporary.name)
        mounts = []
        for index, asset in enumerate(task.inputs):
            if asset.visibility != "actor":
                continue
            path = folder / str(index)
            path.write_text(asset.content)
            path.chmod(0o444)
            mounts.extend(
                ["--mount", f"type=bind,src={path},dst=/workspace/inputs/{asset.path},readonly"]
            )
        try:
            if not self.existing:
                docker(
                    [
                        "run",
                        "-d",
                        "--name",
                        self.name,
                        "--network=none",
                        "--read-only",
                        "--cap-drop=ALL",
                        "--security-opt=no-new-privileges",
                        "--pids-limit=64",
                        "--cpus=" + str(task.environment.cpus),
                        "--memory=" + str(task.environment.memory_mb) + "m",
                        "--memory-swap=" + str(task.environment.memory_mb) + "m",
                        "--user=10001:10001",
                        "--tmpfs",
                        "/tmp:rw,nosuid,nodev,noexec,size=32m,uid=10001,gid=10001",
                        "--tmpfs",
                        "/workspace/output:rw,nosuid,nodev,noexec,size=16m,uid=10001,gid=10001",
                        "-e",
                        "ANVIL_ENVIRONMENT_SEED=" + str(task.environment.seed),
                        *mounts,
                        image,
                        "sleep",
                        "infinity",
                    ]
                )
            for asset in task.inputs:
                if asset.visibility == "actor":
                    raw = docker(["exec", self.name, "cat", "/workspace/inputs/" + asset.path])
                    import hashlib

                    if hashlib.sha256(raw).hexdigest() != asset.sha256:
                        raise ValueError("Initial supplied-image input fingerprint mismatch")
            if self.output() is not None:
                raise ValueError("Environment has pre-seeded candidate output")
            for server in task.mcp_servers:
                if any(not isinstance(x, str) or "\x00" in x for x in server.command):
                    raise ValueError("Invalid MCP executable declaration")
                process = subprocess.Popen(
                    ["docker", "exec", "-i", self.name, *server.command],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    env=docker_env(),
                )
                self.processes[server.id] = process
                response = self.rpc(
                    server.id,
                    "initialize",
                    {
                        "protocolVersion": server.protocol_version,
                        "capabilities": {},
                        "clientInfo": {"name": "anvil", "version": "1"},
                    },
                )
                if response.get("protocolVersion") != server.protocol_version:
                    raise ValueError("MCP protocol handshake mismatch: " + server.id)
                self.notify(server.id, "notifications/initialized")
                listing = self.rpc(server.id, "tools/list", {}).get("tools", [])
                required = {t.id: t for t in server.tools}
                advertised = {t.get("name"): t for t in listing}
                if len(advertised) != len(listing) or not set(required) <= set(advertised):
                    raise ValueError("MCP required tool missing/duplicate: " + server.id)
                for key, tool in required.items():
                    actual_tool = advertised[key]
                    if (
                        actual_tool.get("inputSchema") != tool.input_schema
                        or actual_tool.get("outputSchema") != tool.output_schema
                    ):
                        raise ValueError("MCP tool schema mismatch: " + key)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def notify(self, sid, method):
        process = self.processes[sid]
        process.stdin.write((json.dumps({"jsonrpc": "2.0", "method": method}) + "\n").encode())
        process.stdin.flush()

    def rpc(self, sid, method, params):
        self.counter += 1
        process = self.processes[sid]
        process.stdin.write(
            (
                json.dumps(
                    {"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params}
                )
                + "\n"
            ).encode()
        )
        process.stdin.flush()
        end = time.monotonic() + 8
        raw = b""
        while not raw.endswith(b"\n"):
            remaining = end - time.monotonic()
            if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                raise RuntimeError("MCP response timeout: " + sid)
            chunk = os.read(process.stdout.fileno(), 1)
            if not chunk:
                raise RuntimeError("MCP server exited: " + sid)
            raw += chunk
            if len(raw) > 262144:
                raise RuntimeError("MCP response exceeds bound")
        value = json.loads(raw)
        if value.get("id") != self.counter or "error" in value:
            raise ValueError("MCP invocation failed: " + sid)
        return value.get("result", {})

    def call(self, tool, arguments):
        server, definition = next(
            (s, t) for s in self.task.mcp_servers for t in s.tools if t.id == tool
        )
        schema_check(arguments, definition.input_schema)
        value = self.rpc(server.id, "tools/call", {"name": tool, "arguments": arguments})
        if value.get("isError"):
            raise ValueError("Tool reported execution failure: " + tool)
        result = value.get("structuredContent")
        if result is None:
            content = value.get("content", [])
            result = json.loads(next(c["text"] for c in content if c.get("type") == "text"))
        schema_check(result, definition.output_schema)
        return result

    def output(self):
        raw = docker(
            [
                "exec",
                self.name,
                "python3",
                "-I",
                "-c",
                "import json\nfrom pathlib import Path\np=Path('/workspace/output/output.json')\n"
                "error='Output path is a symlink' if p.is_symlink() else 'Output is not a file' if p.exists() and not p.is_file() else 'Output exceeds 65536 bytes' if p.is_file() and p.stat().st_size>65536 else None\n"
                "print(json.dumps({'present':p.exists(),'error':error,'content':p.read_text() if p.is_file() and not error else None}))",
            ]
        )
        captured = json.loads(raw)
        if captured["error"]:
            raise ValueError(captured["error"])
        if not captured["present"]:
            return None
        from anvil.task_parser import json_value

        value = json_value(captured["content"].encode())
        schema_check(value, self.task.output_schema)
        return value

    def __exit__(self, *unused):
        for process in self.processes.values():
            process.kill()
            process.wait(timeout=10)
        if not self.existing:
            subprocess.run(
                ["docker", "rm", "-f", self.name], env=docker_env(), capture_output=True, timeout=10
            )
        if self.temporary:
            self.temporary.cleanup()


def validate(task, bundle, heartbeat=lambda: None):
    inputs = input_values(task, private=True)
    fixtures = []
    for case in bundle.fixtures:
        heartbeat()
        events = [dict(c.model_dump(), status="completed") for c in case.observed_calls]
        results = []
        for _ in range(2):
            heartbeat()
            checks = execute_code(bundle, "evaluate", [inputs, case.output, events])
            results.append(score(task, checks, case.output))
        if results[0] != results[1]:
            raise ValueError("Verifier is nondeterministic: " + case.id)
        actual = results[0]
        if actual["reward_bps"] != case.expected_reward_bps or any(
            actual["checks"].get(k) != v for k, v in case.expected_checks.items()
        ):
            raise ValueError("Fixture expected/actual mismatch: " + case.id)
        # Every attempted action is checked BEFORE side effects. Final-only constraints are excluded.
        before = []
        assertions = {a.action_index: a for a in case.guard_assertions}
        for index, call in enumerate(case.observed_calls):
            heartbeat()
            decision = guard(task, bundle, call.tool, call.arguments, input_values(task), before)
            if index in assertions:
                expected = assertions[index].expected_checks
                if decision["allowed"] != all(expected.values()) or set(decision["violations"]) != {
                    k for k, v in expected.items() if not v
                }:
                    raise ValueError(
                        "Runtime guard expected/actual mismatch: " + case.id + "/" + str(index)
                    )
            before.append(
                dict(call.model_dump(), status="completed" if decision["allowed"] else "denied")
            )
        fixtures.append({"id": case.id, "kind": case.kind, "passed": True, **actual})
    source_qa = []
    # Independently supplied oracle cases are withheld from generation and candidates.
    # They can reject a self-consistent but incorrect model interpretation.
    for case in task.evaluation_private.fixtures if task.evaluation_private else []:
        heartbeat()
        events = [dict(c.model_dump(), status="completed") for c in case.observed_calls]
        actual = score(
            task, execute_code(bundle, "evaluate", [inputs, case.output, events]), case.output
        )
        if actual["reward_bps"] != case.expected_reward_bps or any(
            actual["checks"].get(k) != v for k, v in case.expected_checks.items()
        ):
            raise ValueError("Source QA expected/actual mismatch: " + case.id)
        source_qa.append({"id": case.id, "passed": True, "reward_bps": actual["reward_bps"]})
    probes = []
    # Fresh supplied image for every safe probe. No private fixture is mounted in it.
    for server in task.mcp_servers:
        for tool in server.tools:
            if tool.effect == "prohibited":
                decision = guard(task, bundle, tool.id, {}, inputs, [])
                if decision["allowed"]:
                    raise ValueError("Prohibited tool is not denied")
                probes.append({"tool": tool.id, "status": "denied_before_dispatch"})
                continue
            heartbeat()
            if not tool.probe or not tool.probe.safe_in_disposable_environment:
                raise ValueError("Tool is not safely testable: " + tool.id)
            with Environment(task) as environment:
                for setup in tool.probe.setup_calls:
                    heartbeat()
                    if not guard(task, bundle, setup.tool, setup.arguments, input_values(task), [])[
                        "allowed"
                    ]:
                        raise ValueError("Probe setup violates a runtime constraint")
                    environment.call(setup.tool, setup.arguments)
                value = environment.call(tool.id, tool.probe.arguments)
                if execute_code(bundle, "probe", [tool.id, value]) is not True:
                    raise ValueError("Tool semantic probe failed: " + tool.id)
            probes.append(
                {
                    "tool": tool.id,
                    "status": "passed",
                    "schema_verified": True,
                    "response_bytes": len(json.dumps(value).encode()),
                    "reset": "fresh_image_read_only_inputs",
                }
            )
    return {
        "state": "passed",
        "fixtures": fixtures,
        "source_qa_fixtures": source_qa,
        "tools": probes,
        "image_digest": task.environment.digest,
        "isolation": "network_none_read_only_root_no_credentials",
        "model_performance": False,
        "origin": "generated_software_validation",
    }


def guard(task, bundle, tool, arguments, inputs, events):
    prohibited = [
        c.id
        for c in task.constraints
        if c.phase in ("runtime", "both") and tool in c.prohibited_tools
    ]
    definition = next((t for s in task.mcp_servers for t in s.tools if t.id == tool), None)
    if not definition:
        raise ValueError("Undeclared tool")
    if definition.effect == "prohibited" or prohibited:
        return {"allowed": False, "violations": prohibited}
    result = execute_code(bundle, "guard", [tool, arguments, inputs, events])
    if (
        not isinstance(result, dict)
        or set(result) != {"allowed", "violations"}
        or type(result["allowed"]) is not bool
        or not isinstance(result["violations"], list)
    ):
        raise ValueError("Invalid generated guard result")
    runtime_ids = {c.id for c in task.constraints if c.phase in ("runtime", "both")}
    if not set(result["violations"]) <= runtime_ids or result["allowed"] == bool(
        result["violations"]
    ):
        raise ValueError("Generated guard has inconsistent violation mapping")
    return result
