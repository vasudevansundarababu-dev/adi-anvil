"""Owned, fixed two-read native control. No generic callback or qualification writer."""

import argparse
import hashlib
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

from anvil import environment_harbor as native
from anvil.golden_kyc_harbor import (
    FixedSoftwareRequest,
    SoftwareScriptContext,
    execute_software_script,
    fixed_policy_runtime,
)
from anvil.praxis_generic_contract import canonical


@contextmanager
def framework_lease(store, job_id, plan_sha256):
    """Recheck the original physical permission before work and before commit."""
    def check():
        current = store.load_probe(job_id)
        if current["plan_sha256"] != plan_sha256:
            raise ValueError("Original probe permission changed")
        store._framework_entry(current)

    check()
    yield
    check()


def validate_assets(store, permission):
    """Substantive validation without old business/qualification admissions."""
    if not permission["technical_probe_authorized"]:
        raise ValueError("Actual QA probe custody required")
    assets = store.operation_assets(permission)
    seal = assets["runtime_seal"]
    if seal.get("schema_version") != "anvil.fixed-runtime-seal.v2":
        raise ValueError("Sealed installed-wheel runtime required; no path overlay")
    store.validate_runtime_seal(seal)
    actor, context = FixedSoftwareRequest(canonical(permission["request_capsule"]["actor"]),
                                         canonical(permission["request_capsule"]["business_context"])).validate()
    host = assets["host_image_custody"]
    folder = store.root / "technical-probe-attempts" / permission["operation_nonce"]
    expected_keys = {"schema_version", "folder", "docker_host", "python", "image_digest", "binaries",
                     "database_provider", "host_domain", "operation_nonce", "request_sha256", "limits", "sdk_profile"}
    if (set(host) != expected_keys or host["schema_version"] != "anvil.kyc-probe-host.v2"
            or host["folder"] != str(folder) or host["host_domain"] != permission["host_domain"]
            or host["image_digest"] != native.FIXTURE_IMAGE or host["limits"] != permission["limits"]
            or any(host[key] != permission[key] for key in ("operation_nonce", "request_sha256"))
            or not host["docker_host"].startswith("unix:///")
            or not Path(host["docker_host"][7:]).exists()
            or host["python"] != seal["components"]["harbor"]["interpreter"]):
        raise ValueError("Exact probe host, image, interpreter and caps required")
    from anvil.golden_native_peer import inspect_sdk, validate_control_mounts

    if inspect_sdk(host["docker_host"]) != host["sdk_profile"]:
        raise ValueError("Operator-observed SDK image or mount profile changed")
    validate_control_mounts(host["sdk_profile"], proof_root=store.root, provider_path=host["database_provider"]["path"],
                            docker=host["binaries"]["docker"]["path"], compose=host["binaries"]["compose"]["path"])
    binaries = host["binaries"]
    if set(binaries) != {"docker", "compose", "python", "opa"} or binaries["python"]["path"] != host["python"]:
        raise ValueError("Exact native executable inventory required")
    for name, record in binaries.items():
        if set(record) != {"path", "sha256"}:
            raise ValueError("Exact native binary pin required")
        path = Path(record["path"])
        store._sealed_file(path.resolve() if name == "python" else path, record["sha256"])
        if not path.stat().st_mode & 0o111:
            raise ValueError("Executable native binary required")
    provider = host["database_provider"]
    if (set(provider) != {"path", "sha256", "field", "database", "server_version"}
            or provider["field"] != "env.GOLDEN_SCHEDULER_DATABASE_URL"
            or not 1 <= len(provider["database"]) <= 63 or not 1 <= len(provider["server_version"]) <= 256
            or not Path(provider["path"]).is_relative_to(store.root.parent)):
        raise ValueError("Exact private scheduler provider required")
    store._sealed_file(provider["path"], provider["sha256"])
    recovery = assets["recovery_recipe"]
    if recovery != {"schema_version": "anvil.kyc-probe-recovery.v1", "job_id": permission["job_id"],
                    "operation_nonce": permission["operation_nonce"], "folder": str(folder),
                    "docker_host": host["docker_host"], "mode": "reconcile_only_no_replay",
                    "limits": permission["limits"]}:
        raise ValueError("Exact probe recovery identity required")
    guards = native.prestart_guards()
    name = "anvil-bm-" + permission["operation_nonce"][:20]
    guards.validate_generated_config(assets["trial_config"], attempt_root=str(folder), trial_name=name)
    for role in ("environment", "tests"):
        service = assets[role + "_service"]
        guards.validate_effective_service(service, role=role,
                                         reviewed_service_sha256=permission["service_projection_sha256s"][role])
        allowed = {"/workspace/inputs", "/logs/agent", "/logs/artifacts"} if role == "environment" else {"/private", "/sealed", "/logs/verifier"}
        targets = set()
        for mount in service.get("volumes", []):
            path, target = Path(mount["source"]), mount["target"]
            if (mount["type"] != "bind" or target not in allowed or target in targets
                    or path.resolve() != path or not path.is_relative_to(folder)
                    or target in {"/workspace/inputs", "/private", "/sealed"} and mount.get("read_only") is not True):
                raise ValueError("Probe role mount custody changed")
            targets.add(target)
        if not ({"/workspace/inputs"} if role == "environment" else {"/sealed"}) <= targets:
            raise ValueError("Probe role inputs missing")
    projection = native.layout_projection(folder, actor, actor_seconds=permission["limits"]["wall_seconds"])
    if assets["task_package"] != {"schema_version": "anvil.fixed-native-task.v1",
            "files": {name: hashlib.sha256(content.encode()).hexdigest() for name, content in projection.items()}}:
        raise ValueError("Exact probe task projection required")
    return assets | {"validated_limits": permission["limits"]}


def run(job_id):
    module = native.operator_proof_module()
    with module.TechnicalProbeStore(native.ROOT) as store:
        permission = store.load_probe(job_id)
        assets = validate_assets(store, permission)
        folder = Path(assets["host_image_custody"]["folder"])
        if folder.exists():
            raise ValueError("Fresh probe attempt required; no replay")
        store.reserve_probe_launch(job_id)
        bindings = permission | {"callback_manifest_sha256": hashlib.sha256(canonical({
            "kind": "fixed_two_read_technical_probe", "plan_sha256": permission["plan_sha256"]})).hexdigest()}
        intent = None
        try:
            with native.fixed_alarm(permission["limits"]["lifecycle_seconds"]):
                result = native._execute_lifecycle(folder, permission["request_capsule"]["actor"], None,
                    host=assets["host_image_custody"]["docker_host"], python=Path(assets["host_image_custody"]["python"]),
                    mediated_candidate=False, actor_seconds=permission["limits"]["wall_seconds"], bindings=bindings,
                    fixed_assets=assets, technical_probe_job=job_id)
            result["framework_claimed_provider_calls"] = result.pop("provider_calls", None)
            result["actual_model_calls"] = None
            result["model_calls_authorized"] = 0
            intent = module.sha(store._read("technical-probe-intents", job_id + ".json"))
            packet = {"schema_version": "anvil.kyc-native-probe-evidence.v1", "job_id": job_id,
                      "plan_sha256": permission["plan_sha256"], "result": result,
                      "qualification_granted": False, "task_score": None, "model_performance": False}
            native.private_json(folder / "observed-evidence.json", packet)
            store.finish_probe(job_id, intent, state="observed", evidence_sha256=module.sha(canonical(packet)))
            return {"job_id": job_id, "status": "observed_not_qualified", "evidence_sha256": module.sha(canonical(packet)),
                    "qualification_granted": False, "model_calls_authorized": 0, "actual_model_calls": None}
        except BaseException:
            if folder.is_dir():
                packet = {"job_id": job_id, "status": "unknown_no_replay", "qualification_granted": False,
                          "actual_model_calls": None}
                native.private_json(folder / "unknown-evidence.json", packet)
                try:
                    intent = module.sha(store._read("technical-probe-intents", job_id + ".json"))
                except FileNotFoundError:
                    pass
                if intent:
                    store.finish_probe(job_id, intent, state="unknown", evidence_sha256=module.sha(canonical(packet)))
            raise


def dispatch(job_id, *, folder, assets, deadline, owner_holder):
    """One fixed installed child; no interpreter/code/callback supplied by caller."""
    module = native.operator_proof_module()
    with module.TechnicalProbeStore(native.ROOT) as store:
        permission = store.load_probe(job_id)
        validate_assets(store, permission)
        python = assets["runtime_seal"]["components"]["backend"]["interpreter"]
        environment = {"PATH": "/usr/bin:/bin", "HOME": str(folder), "LANG": "C", "ANVIL_ROOT": str(store.repository),
                       "ANVIL_ENV": "local", "WEB_ORIGIN": "http://127.0.0.1:3202",
                       "ANVIL_FIXED_OPERATION_NONCE": permission["operation_nonce"],
                       "ANVIL_LIVE_PROVIDERS_ENABLED": "false", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "false",
                       "ANVIL_REAL_EMAIL_ENABLED": "false", "DO_NOT_TRACK": "1", "OTEL_SDK_DISABLED": "true"}
        with owner_holder["_callback_lock"]:
            if owner_holder["_callback_closing"].is_set():
                raise RuntimeError("Probe callback closed before entry")
            deadline.remaining(1)
            store.enter_probe(job_id)
            native.private_json(folder / "callback-dispatch-intent.json", {"job_id": job_id, "no_replay": True})
            child = _spawn_owned_child([python, "-I", "-B", "-m", "anvil.golden_kyc_probe", "--worker", job_id],
                                      environment, owner_holder, deadline, permission["operation_nonce"])
        try:
            native.private_json(folder / "callback-process.json", {"pid": child.pid, "identity": child._anvil_start_identity})
            try:
                stdout, stderr = native._collect_fixed_child(child, ends=time.monotonic() + deadline.remaining(permission["limits"]["wall_seconds"]))
            except native.FixedCaptureStopped as error:
                native.retain_fixed_capture_failure(folder, "probe-callback.private.log", error)
                raise
        finally:
            native._stop_fixed_process(child)
        (folder / "probe-callback.private.log").write_bytes(stdout + stderr)
        if child.returncode:
            raise RuntimeError("Probe worker failed; no replay")
        result = module.parse(stdout)
        if set(result) != {"output", "receipt"} or len(result["output"].get("observations", [])) != 2:
            raise ValueError("Actual two-read probe result required")
        return result["output"], result["receipt"]


def _spawn_owned_child(arguments, environment, holder, deadline, nonce):
    """Spawn and publish custody atomically against the cleanup closing fence."""
    with holder["_callback_lock"]:
        if holder["_callback_closing"].is_set():
            raise RuntimeError("Probe callback closed before spawn")
        deadline.remaining(1)
        child = subprocess.Popen(arguments, env=environment, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, start_new_session=True)
        child._anvil_owned_group = native.UnreapedProcessGroup(child)
        child._anvil_stop_lock = native.threading.RLock()
        holder["_owned_callback"] = child
        child._anvil_start_identity = native.process_identity(child.pid)
        child._anvil_group_nonce = nonce
        return child


def worker(job_id):
    with native.fixed_alarm(300):
        return _worker(job_id)


def _worker(job_id):
    """Private fixed SQL effect entry; framework must still be physically live."""
    module = native.operator_proof_module()
    with module.TechnicalProbeStore(native.ROOT) as store:
        permission = store.load_probe(job_id)
        assets = validate_assets(store, permission)
        store.validate_loaded_origins(assets["runtime_seal"], component="backend")
        store.enter_probe_worker(job_id)
        context = permission["request_capsule"]["business_context"]
        host = assets["host_image_custody"]
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        from psycopg.rows import dict_row

        params = conninfo_to_dict(store.scheduler_secret(host["database_provider"]))
        if set(params) - {"host", "port", "user", "password", "dbname", "sslmode"} or params.get("dbname") != host["database_provider"]["database"]:
            raise ValueError("Exact probe database target required")

        @contextmanager
        def connections():
            current_permission = store.load_probe(job_id)
            if current_permission["plan_sha256"] != permission["plan_sha256"]:
                raise ValueError("Original probe permission changed")
            store._framework_entry(current_permission)
            with psycopg.connect(**params, connect_timeout=2, row_factory=dict_row,
                                 options="-c statement_timeout=1500 -c lock_timeout=500") as c:
                from anvil.golden_kyc_identity import enter

                identity = c.execute("SELECT current_database() AS database,version() AS version").fetchone()
                if (identity["database"] != params["dbname"]
                        or host["database_provider"]["server_version"] not in identity["version"]):
                    raise ValueError("Probe server identity changed")
                enter(c, "anvil_golden_scheduler", context["project_id"])
                c.execute("SELECT set_config('anvil.user',%s,true)", (context["user_id"],))
                fence = c.execute("SELECT anvil.golden_scheduler_project_fence(%s) AS allowed",
                                  (context["project_id"],)).fetchone()
                if not fence or fence["allowed"] is not True:
                    raise ValueError("Current scheduler project fence required")
                active = c.execute("SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id "
                                   "WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active "
                                   "AND m.role IN('admin','rl-engineer')", (context["project_id"], context["user_id"])).fetchone()
                if not active:
                    raise ValueError("Current probe project membership required")
                # Remain inside the connection transaction while checking the
                # lease again: detectable framework death/expiry rolls back.
                with framework_lease(store, job_id, permission["plan_sha256"]):
                    yield c

        from anvil.golden_kyc_runtime import create_trial

        with fixed_policy_runtime(store, host):
            with connections() as c:
                original = c.execute("SELECT snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s AND id=%s",
                                     (context["project_id"], context["pack_id"], context["application_id"])).fetchone()
                if not original or original["snapshot_sha256"] != context["snapshot_sha256"]:
                    raise ValueError("Original probe snapshot changed")
                trial = create_trial(c, context["project_id"], context["user_id"], context["pack_id"], context["application_id"],
                                     "harbor-probe-" + permission["operation_nonce"], 1)
            output, receipt = execute_software_script(SoftwareScriptContext(connections, context["project_id"], context["user_id"],
                trial["trial_id"], trial["trial_token"], tuple(module.TechnicalProbeStore.SCRIPT), context["snapshot_sha256"]))
        store.validate_runtime_seal(assets["runtime_seal"])
        raw = canonical({"output": output, "receipt": {**receipt, "trial_id": str(receipt["trial_id"])}})
        if len(raw) > 1048576 or trial["trial_token"].encode() in raw:
            raise ValueError("Probe output bound or credential isolation failed")
        sys.stdout.buffer.write(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--job")
    group.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker)
    else:
        print(canonical(run(args.job)).decode())


def write_safe_failure(error):
    """Private operator stderr only; never emit exception text or source lines."""
    value = {"status": "blocked_or_unknown_no_replay", "error_type": type(error).__name__,
             "frames": [{"file": frame.filename, "line": frame.lineno, "function": frame.name}
                        for frame in traceback.extract_tb(error.__traceback__)[-12:]]}
    sys.stderr.write(canonical(value).decode() + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        write_safe_failure(error)
        raise SystemExit(1) from None
