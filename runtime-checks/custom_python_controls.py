"""Fixed synthetic custom-Python controls; no model, approval or qualification.

Physical QA: installed Python -I -B, secret-free operator profile, explicit Unix
Docker socket, private retained evidence directory. --validate-only is portable
request validation only and never reports physical controls passed.
The fixed core/resources suites each use a fresh original85-second cutoff.
"""

import argparse
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from time import monotonic

SOURCE_ROOT = Path("/opt/anvil-runtime-source")
BUDGET_SECONDS = 85

VALID = '''import os,inspect,socket
def evaluate(actual, expected):
 assert os.geteuid()==10001
 assert os.statvfs('/').f_flag & os.ST_RDONLY
 assert not os.path.exists('/var/run/docker.sock') and not os.path.exists('/run/docker.sock')
 assert not any('DATABASE' in key or 'DOCKER' in key or key.endswith(('API_KEY','PRIVATE_KEY','ACCESS_TOKEN')) for key in os.environ)
 assert int(next(line.split()[1] for line in open('/proc/self/status') if line.startswith('CapEff:')),16)==0
 frame=inspect.currentframe()
 while frame:
  for mapping in (frame.f_globals,frame.f_locals):
   request=mapping.get('request')
   if type(request) is dict and 'cases' in request:
    assert all(set(case)=={'actual','expected'} for case in request['cases'])
  frame=frame.f_back
 with socket.socket() as probe:
  probe.settimeout(.25)
  assert probe.connect_ex(('198.51.100.1',9))!=0
 return {'status':actual['choice'],'reason':'Labelled synthetic sandbox control only'}
'''
ERRORS = '''def evaluate(actual, expected):
 if actual=='exception':raise ValueError('synthetic exception, not customer data')
 return {'status':'pass','reason':[]}
'''
CPU = '''def evaluate(actual, expected):
 while True:pass
'''
WALL = '''import time
def evaluate(actual, expected):
 time.sleep(30)
 return {'status':'pass'}
'''
FLOOD = '''def evaluate(actual, expected):
 for _ in range(20):print('synthetic stdout '*65536)
 return {'status':'pass'}
'''
PIDS = '''import os,time,errno
def evaluate(actual, expected):
 assert os.getpid()!=1 and os.readlink('/proc/self/ns/pid')==os.readlink('/proc/1/ns/pid')
 children=[]
 limited=False
 for _ in range(40):
  try:child=os.fork()
  except OSError as error:
   if error.errno!=errno.EAGAIN:raise
   limited=True
   break
  if child==0:
   time.sleep(30)
   os._exit(0)
  children.append(child)
 assert limited and 1<=len(children)<=30
 assert len([name for name in os.listdir('/proc') if name.isdecimal()])==32
 # Leave bounded sleepers for the actual PID1 supervisor/namespace cleanup.
 return {'status':'pass','reason':'Synthetic PID32 saturation; blocked children require supervisor cleanup'}
'''
MEMORY = '''import os,signal
def evaluate(actual, expected):
 child=os.fork()
 if child==0:
  try:
   data=bytearray(256*1024*1024)
   for index in range(0,len(data),4096):data[index]=1
  except MemoryError:os._exit(77)
  os._exit(0)
 _,outcome=os.waitpid(child,0)
 denied=(os.WIFSIGNALED(outcome) and os.WTERMSIG(outcome)==signal.SIGKILL) or (os.WIFEXITED(outcome) and os.WEXITSTATUS(outcome)==77)
 if denied:return {'status':'unscored','reason':'Synthetic 256MiB child allocation denied under 128MiB container cap'}
 return {'status':'pass','reason':'Unexpected allocation success; negative control must fail'}
'''


def cases(suite="core"):
    def request(code, values, expected):
        return {"code": code, "cases": [{"actual": actual, "expected": {"synthetic_only": True},
                "expected_status": status} for actual, status in zip(values, expected, strict=True)]}

    controls = [
        ("statuses_sandbox_and_expected_status_privacy", request(VALID,
            [{"choice": s} for s in ("pass", "partial", "fail", "unscored")],
            ["pass", "partial", "fail", "unscored"]), ["pass", "partial", "fail", "unscored"], None),
        ("exception_and_invalid_reason", request(ERRORS, ["exception", "invalid_reason"], ["unscored"] * 2),
            ["error", "error"], {"ValueError"}),
        ("bounded_cpu_negative", request(CPU, [None], ["unscored"]), ["error"],
            {"missing_or_oversized_result", "wall_timeout"}),
        ("bounded_wall_negative", request(WALL, [None], ["unscored"]), ["error"], {"wall_timeout"}),
        ("discarded_stdout_flood", request(FLOOD, [None], ["pass"]), ["pass"], None),
        ("pid_limit_and_supervisor_cleanup", request(PIDS, [None], ["pass"]), ["pass"], None),
        ("memory_limit_negative", request(MEMORY, [None], ["unscored"]), [["unscored", "error"]],
            {"MemoryError", "missing_or_oversized_result", "RuntimeError"}),
    ]
    if suite == "core":
        selected, expected_count = controls[:5], 5
    elif suite == "resources":
        selected, expected_count = controls[5:], 2
    else:
        raise ValueError("Fixed core or resources suite required")
    require(len(selected) == expected_count and len({item[0] for item in selected}) == expected_count,
            "Complete fixed control suite required")
    return selected


def require(condition, message):
    if not condition:
        raise ValueError(message)


def secret_name(key):
    # GPG_KEY is the public signing-key fingerprint in the exact base image.
    key = key.upper()
    return key != "GPG_KEY" and ("DATABASE" in key or key.endswith(
        ("_KEY", "_KEY_ID", "_TOKEN", "PASSWORD", "SECRET", "CREDENTIALS")))


def custody(*, physical):
    forbidden = [key for key, value in os.environ.items() if value and secret_name(key)]
    require(not forbidden, "Secret-free technical process required")
    require(sys.flags.isolated == 1 and sys.dont_write_bytecode, "Installed isolated Python -I -B required")
    if physical:
        require(sys.platform == "linux" and not (SOURCE_ROOT / ".env").exists(), "Fixed secret-free QA source required")
        os.environ["ANVIL_ROOT"] = str(SOURCE_ROOT)
    os.environ.update(ANVIL_ENV="local", WEB_ORIGIN="http://127.0.0.1:3202")


def read(path, cap=131072):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and info.st_uid == os.getuid() and not info.st_mode & 0o077 and info.st_size <= cap,
            "Private bounded original technical record required")
    raw = path.read_bytes()
    require(len(raw) <= cap, "Technical record grew beyond bound")
    return raw


def worker(home, host, suite):
    custody(physical=True)
    from anvil.custom_python_executor import execute, source_hash, validate_request
    from anvil.environment_harbor import private_json
    from anvil.praxis_generic_contract import canonical

    intent_raw = read(home / "technical-intent.json")
    intent = json.loads(intent_raw)
    intent_sha256 = hashlib.sha256(intent_raw).hexdigest()
    require(json.loads(read(home / "technical-intent-sha256.json"))["sha256"] == intent_sha256
            and intent["executor_source_sha256"] == source_hash()
            and intent["control_source_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "Original technical intent and source hashes required")
    raw = read(home / "request.json")
    require(hashlib.sha256(raw).hexdigest() == intent["request_sha256"], "Original request changed")
    request = json.loads(raw)
    controls = {name: expected for name, expected, _, _ in cases(suite)}
    require(intent["suite"] == suite and intent["expected_control_count"] == len(controls)
            and intent["control"] in controls
            and canonical(request) == canonical(controls[intent["control"]]),
            "Only the exact fixed-suite synthetic request may execute")
    validate_request(request)
    execution = home / "execution"
    execution.mkdir(mode=0o700)
    try:
        result = execute(execution, request, host=host)
        result["framework_claimed_model_calls"] = result.pop("model_calls", None)
        result.update(model_calls_authorized=0, actual_model_calls=None, technical_intent_sha256=intent_sha256)
        private_json(home / "framework-result.json", result)
        return 0
    except Exception as error:
        private_json(home / "framework-failure.json", {"exception_type": type(error).__name__,
                     "model_calls_authorized": 0, "actual_model_calls": None})
        return 1


def inspect_container(home, host, cutoff):
    from anvil.environment_harbor import LocalDocker, private_json
    from anvil.native_image_profile import IMAGE, IMAGE_ID

    intent = json.loads(read(home / "execution/launch-intent.json"))
    name, label = intent["container_name"], intent["label"]
    require(re.fullmatch(r"anvil-custom-python-[a-f0-9]{32}", name)
            and re.fullmatch(r"[a-f0-9]{32}", label), "Exact attempt container identity required")
    folder = home / "independent-inspection"
    folder.mkdir(mode=0o700)
    docker = LocalDocker(folder, host)

    def command(args):
        remaining = cutoff - monotonic()
        require(remaining > 0, "Original technical cutoff exceeded")
        return docker.run(args, timeout=min(2, remaining), limit=1048576)

    info = json.loads(command(["inspect", name]))[0]
    require(info["Name"] == "/" + name and info["Image"] == IMAGE_ID
            and info["Config"]["Image"] == IMAGE
            and info["Config"]["Labels"].get("org.adi.anvil.custom-python") == label
            and re.fullmatch(r"[a-f0-9]{64}", info["Id"]), "Original retained container ownership changed")
    if info["State"]["Running"]:
        command(["stop", "--time", "1", info["Id"]])  # Cleanup only this exact labelled attempt, never retry execution.
        info = json.loads(command(["inspect", info["Id"]]))[0]
    host_config, config = info["HostConfig"], info["Config"]
    names = [entry.split("=", 1)[0] for entry in config.get("Env", [])]
    secret_free = not any(secret_name(key) or "DOCKER" in key.upper() for key in names)
    projection = {"id": info["Id"], "name": name, "image_id": info["Image"],
        "running": info["State"]["Running"], "exit_code": info["State"]["ExitCode"],
        "pid": info["State"].get("Pid"), "oom_killed": info["State"].get("OOMKilled"),
        "user": config.get("User"), "network": host_config.get("NetworkMode"),
        "readonly_root": host_config.get("ReadonlyRootfs"), "cap_drop": host_config.get("CapDrop"),
        "pids_limit": host_config.get("PidsLimit"), "memory": host_config.get("Memory"),
        "memory_swap": host_config.get("MemorySwap"), "nano_cpus": host_config.get("NanoCpus"),
        "tmpfs": host_config.get("Tmpfs"), "pid_mode": host_config.get("PidMode"),
        "binds_absent": not host_config.get("Binds"), "environment_names": names,
        "environment_secret_names_absent": secret_free,
        "mounts": [{"type": m.get("Type"), "destination": m.get("Destination")} for m in info.get("Mounts", [])],
        "security_opt": host_config.get("SecurityOpt"), "privileged": host_config.get("Privileged")}
    private_json(home / "independent-inspection.json", projection)
    require(not projection["running"] and projection["pid"] == 0 and config.get("User") == "10001:10001"
        and host_config.get("NetworkMode") == "none" and host_config.get("ReadonlyRootfs") is True
        and set(host_config.get("CapDrop") or []) == {"ALL"} and not host_config.get("CapAdd")
        and host_config.get("PidsLimit") == 32 and host_config.get("Memory") == 128 * 1024 * 1024
        and host_config.get("MemorySwap") == 128 * 1024 * 1024 and host_config.get("NanoCpus") == 500000000
        and not host_config.get("PidMode")
        and set(host_config.get("Tmpfs") or {}) == {"/tmp"}
        and set(host_config["Tmpfs"]["/tmp"].split(",")) == {"rw", "nosuid", "nodev", "noexec", "size=8m", "uid=10001", "gid=10001"}
        and not host_config.get("Binds") and not host_config.get("Privileged")
        and "no-new-privileges" in (host_config.get("SecurityOpt") or []) and secret_free
        and all(m.get("Type") == "tmpfs" and m.get("Destination") == "/tmp" for m in info.get("Mounts", [])),
        "Independent retained-container sandbox control failed")
    return projection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host")
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--suite", choices=("core", "resources"), default="core")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    custody(physical=not args.validate_only)
    if args.worker:
        return worker(args.worker, args.host, args.suite)
    from anvil.custom_python_executor import source_hash, validate_request
    from anvil.environment_harbor import private_json
    from anvil.praxis_generic_contract import canonical

    selected = cases(args.suite)
    for _, request, _, _ in selected:
        validate_request(request)
    if args.validate_only:
        print(json.dumps({"scope": "synthetic_request_validation_only", "suite": args.suite,
            "request_groups": len(selected),
            "physical_controls": "not_run", "native_qualified": False, "model_calls_authorized": 0,
            "actual_model_calls": None}))
        return 0
    from anvil.native_process_identity import process_domain
    from anvil.qualification_resources import qualification_root

    require(qualification_root() == SOURCE_ROOT, "Fixed installed QA custody required")
    domain = process_domain()
    require(type(args.host) is str and args.host.startswith("unix:///"), "Explicit Unix Docker socket required")
    root = args.evidence_root
    require(root is not None and root.is_absolute() and root.resolve() == root, "Canonical private evidence root required")
    root.mkdir(mode=0o700, exist_ok=True)
    metadata = root.lstat()
    require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == os.getuid()
            and not metadata.st_mode & 0o077, "Owner-only evidence root required")
    run = Path(tempfile.mkdtemp(prefix="custom-python-controls-", dir=root))
    cutoff = monotonic() + BUDGET_SECONDS
    common = {"scope": "labelled_synthetic_operator_controls_only", "native_qualified": False,
              "suite": args.suite, "expected_control_count": len(selected),
              "model_calls_authorized": 0, "actual_model_calls": None, "process_domain": domain,
              "executor_source_sha256": source_hash(), "control_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    private_json(run / "technical-run-intent.json", common | {"cutoff_monotonic": cutoff, "retries": False})
    results = []
    for index, (name, request, statuses, error_types) in enumerate(selected):
        home = run / f"{index:02d}-{name}"
        home.mkdir(mode=0o700)
        private_json(home / "request.json", request)
        intent = common | {"control": name, "request_sha256": hashlib.sha256(canonical(request)).hexdigest(),
                           "cutoff_monotonic": cutoff, "expected_technical_statuses": statuses}
        private_json(home / "technical-intent.json", intent)  # Durable before each actual execute call.
        intent_sha256 = hashlib.sha256(canonical(intent)).hexdigest()
        private_json(home / "technical-intent-sha256.json", {"sha256": intent_sha256})
        try:
            require(cutoff - monotonic() >= 20, "Insufficient original budget for a new control")
            worker_env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL") if key in os.environ}
            child = subprocess.Popen([sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                "--worker", str(home), "--host", args.host, "--suite", args.suite], env=worker_env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            try:
                child.wait(timeout=min(17, cutoff - monotonic() - 5))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)  # The original child is still unreaped here.
                except ProcessLookupError:
                    pass
                finally:
                    child.wait(timeout=1)
            inspection = inspect_container(home, args.host, cutoff)
            result = json.loads(read(home / "framework-result.json"))
            require(result["technical_intent_sha256"] == intent_sha256
                    and result["source_sha256"] == common["executor_source_sha256"]
                    and result["container_name"] == inspection["name"]
                    and result["process_domain"] == domain and result["deployment_qualified"] is False,
                    "Actual returned execution differs from original technical intent")
            observed = result["cases"]
            require(len(observed) == len(statuses) and all(
                item["actual_status"] in wanted if type(wanted) is list else item["actual_status"] == wanted
                for item, wanted in zip(observed, statuses, strict=True)), "Synthetic verdict control failed")
            if error_types:
                require(all(item.get("error_type") in error_types for item in observed if item["actual_status"] == "error"),
                        "Synthetic error/timeout control failed")
            if name == "memory_limit_negative" and observed[0].get("error_type") == "RuntimeError":
                require(inspection["oom_killed"] is True or inspection["exit_code"] == 137,
                        "Memory control failed before an observed memory-denial outcome")
            results.append({"control": name, "status": "passed", "framework_passed": result["passed"]})
        except Exception as error:
            results.append({"control": name, "status": "failed", "exception_type": type(error).__name__})
        private_json(home / "technical-result.json", common | results[-1] | {"technical_intent_sha256": intent_sha256})
    summary = common | {"controls": results, "passed": len(results) == len(selected)
                        and all(item["status"] == "passed" for item in results),
                        "evidence": str(run)}
    private_json(run / "technical-summary.json", summary)
    print(json.dumps(summary))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as failure:
        print(json.dumps({"scope": "synthetic_custom_python_controls_blocked", "exception_type": type(failure).__name__,
                          "native_qualified": False, "model_calls_authorized": 0, "actual_model_calls": None}))
        raise SystemExit(1) from None
