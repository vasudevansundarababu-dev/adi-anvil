"""Dedicated coordinator only: actual Python in a bounded, secret-free container.

No Docker socket, SQL connection, host directory or provider credential is mounted
into submitted code. Exact preloaded image only; retain stopped containers.
"""

import ast
import hashlib
import json
import os
import re
import selectors
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from anvil.environment_harbor import LocalDocker, private_json
from anvil.native_image_profile import IMAGE, IMAGE_ID, require_cached_image
from anvil.native_process_identity import process_domain

VERSION = "anvil-isolated-python-evaluator-v1"
STATUSES = {"pass", "partial", "fail", "unscored"}

# PID1 supervises a separate process group. If it exits, the kernel terminates
# the namespace. User stdout is discarded; only bounded JSON results are read.
RUNNER = r"""import os,sys,json,time,signal,resource,traceback
from pathlib import Path
request=json.loads(sys.stdin.buffer.read(131073))
if os.getpid()!=1 or os.geteuid()!=10001:raise RuntimeError('isolated_pid1_nonroot_required')
if any('API_KEY' in k or 'DATABASE' in k or 'DOCKER' in k for k in os.environ):raise RuntimeError('ambient_secret_denied')
child=os.fork()
if child==0:
 os.setsid()
 resource.setrlimit(resource.RLIMIT_CPU,(2,2))
 resource.setrlimit(resource.RLIMIT_FSIZE,(32768,32768))
 with open('/dev/null','wb') as sink:
  os.dup2(sink.fileno(),1);os.dup2(sink.fileno(),2)
 try:
  ns={};exec(compile(request['code'],'custom-evaluator.py','exec'),ns)
  outputs=[]
  for case in request['cases']:
   try:
    value=ns['evaluate'](case['actual'],case['expected'])
    if type(value) is not dict or set(value)-{'status','reason'} or value.get('status') not in {'pass','partial','fail','unscored'}:raise ValueError('output_contract')
    if 'reason' in value and (type(value['reason']) is not str or len(value['reason'])>1000):raise ValueError('reason_contract')
    outputs.append({'status':value['status']})
   except BaseException as exc:
    lines=[t.lineno for t in traceback.extract_tb(exc.__traceback__) if t.filename=='custom-evaluator.py']
    outputs.append({'status':'error','error_type':type(exc).__name__[:80],'line':lines[-1] if lines else None})
  raw=json.dumps({'outputs':outputs},allow_nan=False).encode()
  if len(raw)>32768:raise ValueError('output_limit')
  Path('/tmp/result.json').write_bytes(raw)
 except BaseException as exc:
  Path('/tmp/result.json').write_text(json.dumps({'error_type':type(exc).__name__[:80]}))
 os._exit(0)
deadline=time.monotonic()+5
while True:
 done,status=os.waitpid(child,os.WNOHANG)
 if done:break
 if time.monotonic()>deadline:
  os.kill(-1,signal.SIGKILL)
  print(json.dumps({'error_type':'wall_timeout'}),flush=True);sys.exit(0)
 time.sleep(.02)
try:os.kill(-1,signal.SIGKILL)
except ProcessLookupError:pass
path=Path('/tmp/result.json')
if path.is_symlink() or not path.is_file() or path.stat().st_size>32768:
 print(json.dumps({'error_type':'missing_or_oversized_result'}),flush=True)
else:
 raw=path.read_bytes()
 if len(raw)>32768:raise RuntimeError('output_limit')
 value=json.loads(raw);print(json.dumps(value,allow_nan=False),flush=True)
"""


def source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def validate_request(request):
    if not isinstance(request, dict) or set(request) != {"code", "cases"}:
        raise ValueError("Exact code/cases request required")
    code, cases = request["code"], request["cases"]
    if type(code) is not str or not 1 <= len(code.encode()) <= 16384:
        raise ValueError("Python code must be1–16384UTF8bytes")
    if type(cases) is not list or not 1 <= len(cases) <= 30:
        raise ValueError("Supply1–30 explicit test cases")
    tree = ast.parse(code)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "evaluate"]
    if len(functions) != 1:
        raise ValueError("Define evaluate(actual, expected)")
    args = functions[0].args
    if (
        [a.arg for a in args.args] != ["actual", "expected"]
        or args.posonlyargs
        or args.kwonlyargs
        or args.vararg
        or args.kwarg
        or args.defaults
    ):
        raise ValueError("Define evaluate(actual, expected) with exactly two positional arguments")
    for case in cases:
        if (
            type(case) is not dict
            or set(case) != {"actual", "expected", "expected_status"}
            or case["expected_status"] not in STATUSES
        ):
            raise ValueError("Each case requires actual, expected and expected_status")
    raw = json.dumps(request, allow_nan=False).encode()
    if len(raw) > 49152:
        raise ValueError("Code and JSON test inputs exceed49152bytes")
    return raw


def execute(home, request, *, host):
    """No database/provider access; caller persists intent BEFORE this function."""
    validate_request(request)
    # Expected test verdicts stay outside submitted Python, including its parent
    # interpreter globals and inspectable process environment.
    payload = json.dumps(
        {
            "code": request["code"],
            "cases": [{"actual": c["actual"], "expected": c["expected"]} for c in request["cases"]],
        },
        allow_nan=False,
    ).encode()
    domain = process_domain()
    if any(
        v and ("DATABASE" in k or k.endswith("API_KEY") or k.endswith("PRIVATE_KEY"))
        for k, v in os.environ.items()
    ):
        raise RuntimeError("Custom Python coordinator must not receive SQL/provider secrets")
    docker = LocalDocker(home, host)
    require_cached_image(json.loads(docker.run(["image", "inspect", IMAGE]))[0])
    name, label = "anvil-custom-python-" + uuid4().hex, uuid4().hex
    private_json(
        home / "launch-intent.json",
        {
            "container_name": name,
            "label": label,
            "image_id": IMAGE_ID,
            "process_domain": domain,
            "source_sha256": source_hash(),
        },
    )
    command = [
        *docker.command,
        "run",
        "--pull=never",
        "--name",
        name,
        "--label",
        "org.adi.anvil.custom-python=" + label,
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=32",
        "--cpus=0.5",
        "--memory=128m",
        "--memory-swap=128m",
        "--user=10001:10001",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=8m,uid=10001,gid=10001",
        "--log-driver=none",
        "--entrypoint",
        "python3",
        "-i",
        IMAGE,
        "-I",
        "-c",
        RUNNER,
    ]
    child = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=docker.environment,
    )
    output, errors, written = bytearray(), bytearray(), 0
    deadline = time.monotonic() + 15
    failure = None
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
                if time.monotonic() > deadline:
                    raise TimeoutError("isolated_python_timeout")
                for key, event in selector.select(0.1):
                    stream = key.fileobj
                    if key.data == "input":
                        try:
                            written += os.write(stream.fileno(), payload[written : written + 8192])
                        except BrokenPipeError:
                            selector.unregister(stream)
                            stream.close()
                            continue
                        if written == len(payload):
                            selector.unregister(stream)
                            stream.close()
                    else:
                        raw = os.read(stream.fileno(), 8192)
                        if not raw:
                            selector.unregister(stream)
                            stream.close()
                            continue
                        target = output if key.data == "output" else errors
                        target.extend(raw)
                        if len(target) > 32768:
                            raise ValueError("isolated_python_output_limit")
        if child.wait(timeout=2):
            raise RuntimeError("isolated_python_process_failed")
    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.TimeoutExpired) as exc:
        failure = type(exc).__name__
    finally:
        # Inspect before touching a container; stop only this attempt's exact label.
        try:
            info = docker.inspect(name)
            if (
                info["Config"]["Labels"].get("org.adi.anvil.custom-python") != label
                or info["Image"] != IMAGE_ID
                or not re.fullmatch(r"[a-f0-9]{64}", info["Id"])
            ):
                raise RuntimeError("custom_python_cleanup_ownership_mismatch")
            if info["State"]["Running"]:
                docker.run(["stop", "--time", "1", info["Id"]])
            if docker.inspect(info["Id"])["State"]["Running"]:
                raise RuntimeError("custom_python_cleanup_incomplete")
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)
    try:
        result = json.loads(output) if not failure else {"error_type": failure}
        if not isinstance(result, dict):
            raise ValueError("object required")
    except (ValueError, UnicodeError):
        result = {"error_type": "invalid_output_contract"}
    private_json(
        home / "private-process-diagnostics.json",
        {
            "failure_type": failure,
            "return_code": child.returncode,
            "stdout_sha256": hashlib.sha256(output).hexdigest(),
            "stderr_sha256": hashlib.sha256(errors).hexdigest(),
            "stderr_excerpt": bytes(errors[:4096]).decode(errors="replace"),
        },
    )
    statuses = result.get("outputs", [])
    if not isinstance(statuses, list) or len(statuses) != len(request["cases"]):
        statuses = [
            {"status": "error", "error_type": result.get("error_type", "invalid_output_contract")}
            for _ in request["cases"]
        ]
    checked = []
    for index, (case, observed) in enumerate(zip(request["cases"], statuses, strict=True)):
        status = observed.get("status") if isinstance(observed, dict) else None
        if status not in STATUSES:
            status = "error"
        checked.append(
            {
                "case_index": index,
                "expected_status": case["expected_status"],
                "actual_status": status,
                "passed": status == case["expected_status"],
                "input_sha256": hashlib.sha256(
                    json.dumps(
                        {"actual": case["actual"], "expected": case["expected"]},
                        sort_keys=True,
                        allow_nan=False,
                    ).encode()
                ).hexdigest(),
            }
        )
        if status == "error":
            kind = observed.get("error_type") if isinstance(observed, dict) else None
            line = observed.get("line") if isinstance(observed, dict) else None
            checked[-1]["error_type"] = (
                kind
                if type(kind) is str and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", kind)
                else "invalid_output_contract"
            )
            checked[-1]["line"] = (
                line
                if type(line) is int and 1 <= line <= len(request["code"].splitlines())
                else None
            )
    covered = {v["expected_status"] for v in checked if v["passed"]}
    return {
        "schema_version": "anvil.isolated-python-test.v1",
        "runtime": VERSION,
        "source_sha256": source_hash(),
        "image": IMAGE,
        "image_id": IMAGE_ID,
        "process_domain": domain,
        "container_name": name,
        "container_retained_stopped": True,
        "network": "none",
        "readonly_root": True,
        "cases": checked,
        "passed": all(v["passed"] for v in checked),
        "control_coverage_complete": {"pass", "fail", "unscored"} <= covered,
        "deployment_qualified": False,
        "model_calls": 0,
    }
