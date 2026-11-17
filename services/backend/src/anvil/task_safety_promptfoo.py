"""Real upstream custom-plugin preparation/parsing, no credential or network.

The existing Anvil broker performs at most one SDK request using the exact
framework-prepared prompt. Promptfoo then parses that recorded exact response.
Additional upstream generation callbacks are rejected, never model retries.
"""

import hashlib
import json
import os
import selectors
import subprocess
import tempfile
import time

from anvil.config import ROOT
from anvil.evaluator_runtimes import runtime_version

WORKER = ROOT / "integrations/evaluators/promptfoo/redteam-worker.mjs"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def bounded_process(command, raw, *, directory, env, timeout=15):
    """Concurrent bounded pipes; termination targets only this owned subprocess."""
    child = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=directory,
        env=env,
        bufsize=0,
    )
    output, written = bytearray(), 0
    counts = {"output": 0, "error": 0}
    limits = {"output": 262144, "error": 32768}
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for stream, event, kind in (
                (child.stdin, selectors.EVENT_WRITE, "input"),
                (child.stdout, selectors.EVENT_READ, "output"),
                (child.stderr, selectors.EVENT_READ, "error"),
            ):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, event, kind)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                for key, _ in selector.select(min(0.1, remaining)):
                    stream = key.fileobj
                    if key.data == "input":
                        try:
                            written += os.write(stream.fileno(), raw[written : written + 8192])
                        except BrokenPipeError:
                            written = len(raw)
                        if written == len(raw):
                            selector.unregister(stream)
                            stream.close()
                    else:
                        chunk = os.read(
                            stream.fileno(), min(8192, limits[key.data] - counts[key.data] + 1)
                        )
                        if not chunk:
                            selector.unregister(stream)
                            stream.close()
                            continue
                        counts[key.data] += len(chunk)
                        if counts[key.data] > limits[key.data]:
                            raise ValueError("Promptfoo stream limit exceeded; no inference retry")
                        if key.data == "output":
                            output.extend(chunk)
        code = child.wait(timeout=max(0.001, deadline - time.monotonic()))
        return subprocess.CompletedProcess(command, code, bytes(output), b"")
    except (OSError, TimeoutError, subprocess.TimeoutExpired):
        raise ValueError("Promptfoo process failed; no inference retry") from None
    finally:
        if child.poll() is None:
            child.kill()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            raise ValueError("Promptfoo termination unconfirmed; no inference retry") from None
        finally:
            for stream in (child.stdin, child.stdout, child.stderr):
                stream.close()


def run(payload):
    if runtime_version("promptfoo") != "0.125.1":
        raise ValueError("Exact installed Promptfoo version required")
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
    if len(raw) > 262144:
        raise ValueError("Bounded framework input required")
    with tempfile.TemporaryDirectory(prefix="anvil-promptfoo-generation-") as directory:
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": directory,
            "PROMPTFOO_CONFIG_DIR": directory,
            "PROMPTFOO_DISABLE_TELEMETRY": "1",
            "PROMPTFOO_DISABLE_UPDATE": "1",
            "PROMPTFOO_DISABLE_REMOTE_GENERATION": "true",
            "PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION": "true",
            "PROMPTFOO_SAFE_MODE": "true",
            "PROMPTFOO_LOG_LEVEL": "error",
        }
        try:
            result = bounded_process(
                [os.environ["ANVIL_EVALUATOR_NODE"], str(WORKER)],
                raw,
                directory=directory,
                env=env,
            )
        except (subprocess.TimeoutExpired, OSError):
            raise ValueError("Promptfoo process failed; no inference retry") from None
    if result.returncode or len(result.stdout) > 262144:
        # Upstream errors can quote task text. Expose no raw child error/log.
        raise ValueError("Promptfoo custom generation failed; no inference retry")
    value = json.loads(result.stdout)
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != "anvil.promptfoo-task-generation.v1"
        or value.get("framework") != "promptfoo-custom"
        or value.get("version") != "0.125.1"
        or value.get("framework_api") != "redteam.Base.Plugin.generateTests"
        or value.get("provider_callbacks") != 1
        or value.get("worker_physical_provider_calls") != 0
        or value.get("remote_generation_disabled") is not True
        or value.get("model_performance") is not False
    ):
        raise ValueError("Exact upstream framework receipt required")
    return value


def prepare(purpose, categories):
    value = run({"mode": "prepare", "purpose": purpose, "categories": categories})
    if value.get("mode") != "prepared_only" or sha(value["prompt"]) != value["prompt_sha256"]:
        raise ValueError("Exact framework-prepared prompt required")
    return value


def parse_recorded(purpose, categories, prepared_prompt, response):
    value = run(
        {
            "mode": "generate",
            "purpose": purpose,
            "categories": categories,
            "prepared_prompt_sha256": sha(prepared_prompt),
            "response": response,
        }
    )
    tests = value.get("tests")
    if (
        value.get("mode") != "recorded_response_parsed"
        or value["prompt_sha256"] != sha(prepared_prompt)
        or value["response_sha256"] != sha(response)
        or not isinstance(tests, list)
        or len(tests) != 15
    ):
        raise ValueError("Exact one-shot framework response binding required")
    encoded = json.dumps(
        tests, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    if value.get("tests_sha256_encoding") != "anvil.sorted-json-utf8.v1" or sha(
        encoded
    ) != value.get("tests_sha256"):
        raise ValueError("Actual framework test projection integrity changed")
    return value
