"""Root-only QA preparation of a fixed two-read control; never starts a trial."""

import argparse
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from anvil import environment_harbor as native
from anvil.golden_kyc_harbor import FixedSoftwareRequest
from anvil.golden_kyc_probe import validate_assets

PREFIX = Path("/opt/anvil-runtime")
REQUEST_SCHEMA = "anvil.kyc-technical-probe-request.v1"


def require(condition):
    if not condition:
        raise ValueError("Fixed root-owned QA probe preparation required")


def private_read(path, *, limit=16384):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0
                and not before.st_mode & 0o077 and before.st_nlink == 1)
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        require(len(raw) <= limit and (before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_ino, after.st_size, after.st_mtime_ns))
        return raw


def measured(path):
    """Measure original bytes; never interpret provider files or print contents."""
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0
                and not before.st_mode & 0o022 and before.st_nlink == 1)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = os.fstat(stream.fileno())
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
    return digest


def exclusive_json(store, directory, name, value, *, reuse=False):
    raw = native.canonical(value)
    require(len(raw) <= 1048576)
    folder = store._directory(directory)
    try:
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=folder)
        except FileExistsError:
            require(reuse and store._read(directory, name) == raw)
        else:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(folder)
    finally:
        os.close(folder)
    return hashlib.sha256(raw).hexdigest()


def asset(store, value):
    pin = hashlib.sha256(native.canonical(value)).hexdigest()
    return exclusive_json(store, "operation-assets", pin + ".json", value, reuse=True)


def request_capsule(module, request):
    require(type(request) is dict and set(request) == {
        "schema_version", "business_context", "request_reference", "docker_host",
        "binaries", "database_provider"} and request["schema_version"] == REQUEST_SCHEMA)
    supplied = request["business_context"]
    require(type(supplied) is dict and set(supplied) == {
        "project_id", "user_id", "pack_id", "application_id", "environment_version", "snapshot_sha256"})
    context = dict(supplied, kind="golden_kyc_software_v1", paid_calls=False,
                   script_sha256=hashlib.sha256(native.canonical(module.TechnicalProbeStore.SCRIPT)).hexdigest())
    module.validate_business_context(context)
    actor = {key: context[key] for key in (
        "application_id", "environment_version", "snapshot_sha256", "script_sha256", "paid_calls")}
    FixedSoftwareRequest(native.canonical(actor), native.canonical(context)).validate()
    require(type(request["request_reference"]) is str and 1 <= len(request["request_reference"]) <= 1000)
    require(type(request["docker_host"]) is str and request["docker_host"].startswith("unix:///"))
    socket = Path(request["docker_host"][7:])
    require(socket.resolve() == socket and stat.S_ISSOCK(socket.stat().st_mode))
    require(type(request["binaries"]) is dict and set(request["binaries"]) == {"docker", "compose", "opa"})
    provider = request["database_provider"]
    require(type(provider) is dict and set(provider) == {"path", "database", "server_version"}
            and type(provider["database"]) is str and 1 <= len(provider["database"]) <= 63
            and type(provider["server_version"]) is str and 1 <= len(provider["server_version"]) <= 256)
    return {"actor": actor, "business_context": context}


# This program runs only with the fixed installed interpreter, isolated and with
# bytecode disabled. It reads metadata/files without importing installed SDKs.
INVENTORY = r'''
import hashlib,importlib.metadata,json,pathlib,re,sys,sysconfig
P=pathlib.Path
def hashes(paths):
 return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}
prefix=P(sys.prefix).resolve();site=P(sysconfig.get_path('purelib')).resolve()
assert prefix==P('/opt/anvil-runtime') and site.is_relative_to(prefix)
distributions={}
for d in importlib.metadata.distributions(path=[str(site)]):
 n=re.sub(r'[-_.]+','-',d.metadata['Name']).lower()
 assert n not in distributions and d.files is not None
 distributions[n]={'version':d.version,'files':{str(f):hashlib.sha256(P(d.locate_file(f)).read_bytes()).hexdigest() for f in d.files}}
stdlib=P(sysconfig.get_path('stdlib')).resolve()
print(json.dumps({'prefix':str(prefix),'site_packages':str(site),'python_version':'.'.join(map(str,sys.version_info[:3])),
 'distributions':distributions,'stdlib_root':str(stdlib),'stdlib_files':hashes(p for p in stdlib.rglob('*') if 'site-packages' not in p.relative_to(stdlib).parts),
 'source_files':{n:hashes((site/n).rglob('*')) for n in ('anvil','anvil_harbor')}}))
'''


def runtime_seal(store):
    interpreter = PREFIX / "bin/python"
    require(interpreter.exists() and PREFIX.resolve() == PREFIX)
    result = subprocess.run([str(interpreter), "-I", "-B", "-c", INVENTORY],
                            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=True)
    require(len(result.stdout) <= 20 * 1048576)
    observed = json.loads(result.stdout)
    distributions = {name: {"version": record["version"], "files_sha256": asset(store, record["files"])}
                     for name, record in observed["distributions"].items()}
    common = {key: observed[key] for key in ("prefix", "site_packages", "python_version", "stdlib_root")}
    common.update(interpreter=str(interpreter), interpreter_sha256=measured(interpreter.resolve()),
                  venv_config_sha256=measured(PREFIX / "pyvenv.cfg"), distributions=distributions,
                  stdlib_files_sha256=asset(store, observed["stdlib_files"]))
    components = {}
    for component, package in (("backend", "anvil"), ("harbor", "anvil_harbor")):
        files = observed["source_files"][package]
        require(files)
        source = store.repository / ("services/backend/src" if component == "backend" else "services/harbor/src") / package
        installed = Path(observed["site_packages"]) / package
        expected = {str(p.relative_to(source)): measured(p) for p in source.rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
        actual = {str(Path(p).relative_to(installed)): pin for p, pin in files.items()}
        require(expected == actual)
        components[component] = dict(common, source_packages={package: str(Path(observed["site_packages"]) / package)},
                                     source_files_sha256=asset(store, files))
    seal = {"schema_version": "anvil.fixed-runtime-seal.v2", "components": components}
    # Validates complete RECORD/site/stdlib closure, custody, installed/source
    # byte equality, Python version and venv settings before any plan is written.
    store.validate_runtime_seal(seal)
    return seal


COMPOSE_FILES = r'''
import json,sys
from pathlib import Path
from harbor.environments.docker import COMPOSE_PREBUILT_PATH,write_env_compose_file,write_mounts_compose_file,write_resources_compose_file
from harbor.models.trial.paths import TrialPaths
from harbor.models.task.config import TaskOS
from harbor.trial.trial import _harbor_log_bind_mount
p=json.load(sys.stdin);stage=Path(p['staging']);folder=Path(p['folder']);name=p['name']
paths=TrialPaths(trial_dir=folder/'trials'/name)
result={}
for role in ('environment','tests'):
 d=stage/role;d.mkdir(mode=0o700)
 mounts=([_harbor_log_bind_mount(source=str(paths.agent_dir),target='/logs/agent',os=TaskOS.LINUX),
          _harbor_log_bind_mount(source=str(paths.host_artifact_path('main','/logs/artifacts')),target='/logs/artifacts',os=TaskOS.LINUX)]
         if role=='environment' else [_harbor_log_bind_mount(source=str(paths.verifier_dir),target='/logs/verifier',os=TaskOS.LINUX)])
 resource=write_resources_compose_file(d/'resources.json',cpu_limit=1,memory_limit_mb=512,gpus=0)
 env=write_env_compose_file(d/'environment.json',{})
 mount=write_mounts_compose_file(d/'mounts.json',mounts)
 result[role]=list(map(str,[resource,COMPOSE_PREBUILT_PATH,stage/(role+'.json'),env,mount]))
print(json.dumps(result))
'''


def compose_services(store, request, projection, *, folder, name):
    """Config only: no daemon operation, build, pull, start or volume action."""
    result = {}
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=store.root / "technical-probe-attempts") as staging:
        for role in ("environment", "tests"):
            path = Path(staging) / (role + ".json")
            path.write_text(projection[role + "/docker-compose.yaml"])
            path.chmod(0o600)
        generated = subprocess.run([str(PREFIX / "bin/python"), "-I", "-B", "-c", COMPOSE_FILES],
                                   input=native.canonical({"staging": staging, "folder": str(folder), "name": name}),
                                   env={"PATH": "/usr/bin:/bin", "LANG": "C"},
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=True)
        require(len(generated.stdout) <= 16384)
        paths = json.loads(generated.stdout)
        require(set(paths) == {"environment", "tests"})
        for role in ("environment", "tests"):
            arguments = [request["binaries"]["compose"], "--project-name",
                         name + ("__env" if role == "environment" else "__verifier__trial")]
            for path in paths[role]:
                arguments.extend(["--file", path])
            output = subprocess.run([*arguments, "config", "--format", "json"],
                                    env={"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": staging,
                                         "DOCKER_HOST": request["docker_host"], "PREBUILT_IMAGE_NAME": native.FIXTURE_IMAGE},
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True)
            require(len(output.stdout) <= 1048576)
            document = json.loads(output.stdout)
            require(set(document["services"]) == {"main"})
            result[role] = document["services"]["main"]
    return result


def prepare(request_path):
    require(os.geteuid() == 0 and os.uname().nodename == "anvil-qa-v1")
    module = native.operator_proof_module()
    request = module.parse(private_read(request_path))
    capsule = request_capsule(module, request)
    with module.TechnicalProbeStore(native.ROOT) as store:
        require(store._qa_custody() and Path(request_path).is_relative_to(store.root.parent))
        for name in store.DIRECTORIES | {"operation-assets"}:
            try:
                os.mkdir(name, mode=0o700, dir_fd=store.fd)
            except FileExistsError:
                pass
            fd = store._directory(name)
            os.close(fd)
        job, nonce = str(uuid4()), secrets.token_hex(32)
        folder = store.root / "technical-probe-attempts" / nonce
        require(not folder.exists())
        now = store._clock()
        expiry = min(now + timedelta(minutes=30), module.STOP)
        require(now < expiry)
        seal = runtime_seal(store)
        binaries = {}
        for name, path in request["binaries"].items():
            require(type(path) is str and Path(path).stat().st_mode & 0o111)
            binaries[name] = {"path": path, "sha256": measured(path)}
        python = seal["components"]["harbor"]["interpreter"]
        binaries["python"] = {"path": python, "sha256": measured(Path(python).resolve())}
        provider = request["database_provider"]
        provider_path = Path(provider["path"])
        require(provider_path.is_relative_to(store.root.parent))
        # Enforce private custody without parsing its secret-bearing content.
        info = provider_path.lstat()
        store._private(info)
        provider = dict(provider, field="env.GOLDEN_SCHEDULER_DATABASE_URL", sha256=measured(provider_path))
        domain = store._domain()
        from anvil.golden_native_peer import inspect_sdk

        sdk_profile = inspect_sdk(request["docker_host"])
        host = {"schema_version": "anvil.kyc-probe-host.v2", "folder": str(folder), "sdk_profile": sdk_profile,
                "docker_host": request["docker_host"], "python": python, "image_digest": native.FIXTURE_IMAGE,
                "binaries": binaries, "database_provider": provider, "host_domain": domain,
                "operation_nonce": nonce, "request_sha256": hashlib.sha256(native.canonical(capsule)).hexdigest(),
                "limits": store.LIMITS}
        projection = native.layout_projection(folder, capsule["actor"], actor_seconds=store.LIMITS["wall_seconds"])
        services = compose_services(store, request, projection, folder=folder, name="anvil-bm-" + nonce[:20])
        config = {"task": {"path": str(folder / "task")}, "trial_name": "anvil-bm-" + nonce[:20],
                  "trials_dir": str(folder / "trials"), "agent": {"import_path": "anvil_harbor.sme:SMEAgent"},
                  "environment": {"import_path": "anvil_harbor.environment:LocalComponentsDocker", "delete": False},
                  "verifier": {"import_path": "anvil_harbor.sme:SMEVerifier"}}
        profiles = {role: hashlib.sha256(native.canonical(service)).hexdigest() for role, service in services.items()}
        assets = {"runtime_seal": seal, "trial_config": config,
                  "task_package": {"schema_version": "anvil.fixed-native-task.v1", "files": {
                      name: hashlib.sha256(content.encode()).hexdigest() for name, content in projection.items()}},
                  "host_image_custody": host, "environment_service": services["environment"], "tests_service": services["tests"],
                  "recovery_recipe": {"schema_version": "anvil.kyc-probe-recovery.v1", "job_id": job,
                                      "operation_nonce": nonce, "folder": str(folder), "docker_host": request["docker_host"],
                                      "mode": "reconcile_only_no_replay", "limits": store.LIMITS}}
        pins = {name: asset(store, value) for name, value in assets.items()}
        dependencies = {relative: measured(store.repository / relative)
                        for relative in module.REQUIRED_DEPENDENCIES | {
                            "services/harbor/src/anvil_harbor/operator_proof.py",
                            "services/backend/src/anvil/golden_kyc_probe_prepare.py"}}
        store._dependencies(dependencies)
        plan = {"schema_version": "anvil.kyc-technical-probe-plan.v1", "job_id": job, "operation_nonce": nonce,
                "authorization_scope": "fixed_two_read_software_control_only", "request_reference": request["request_reference"],
                "created_at": now.isoformat(), "expires_at": expiry.isoformat(), "host_domain": domain,
                "request_capsule": capsule, "dependency_source_sha256s": dependencies, "asset_sha256s": pins,
                "service_projection_sha256s": profiles, "limits": store.LIMITS}
        validate_assets(store, dict(plan, technical_probe_authorized=True, request_sha256=host["request_sha256"]))
        require(not folder.exists() and store._clock() < expiry)
        pin = exclusive_json(store, "technical-probe-plans", job + ".json", plan)
        permission = store.load_probe(job)
        require(permission["technical_probe_authorized"])
        return {"job_id": job, "plan_sha256": pin, "status": "prepared_not_launched",
                "qualification_granted": False, "model_calls_authorized": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Root-private fixed QA request JSON")
    arguments = parser.parse_args()
    print(native.canonical(prepare(arguments.request)).decode())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("probe_preparation_blocked\n")
        raise SystemExit(1) from None
