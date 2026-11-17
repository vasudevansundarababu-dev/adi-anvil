"""Closed fixed Compose create/start and actual owned-container identity source.

No native admission or actual physical/daemon/process qualification is supplied.
Only exact root assets may select the fixed binary; no caller command/callback.
"""

import asyncio
import hashlib
import json
import os
import re
import signal

from anvil.marketing_native_attempt import MarketingAttemptStore, _write_at
from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    _bounded_canonical,
    _digest,
    _pairs,
    marketing_native_gate,
)
from anvil.marketing_native_collector import EVENT_FIELDS
from anvil.marketing_native_control import _remaining
from anvil.marketing_native_engine import _request
from anvil.marketing_native_launcher import _process_identity, _pump
from anvil.marketing_native_mounts import _context_version, _handoff_actor, _handoff_verifier
from anvil.marketing_native_preflight import ENVIRONMENT, _read_pair, _resolver, _stream_outcome
from anvil.marketing_native_records import _parse_record, resolve_marketing_records
from anvil.marketing_native_start import _check, _framework_entry, _profile

PREFIX = ["--env-file", "/dev/null", "--project-directory", "<role_directory>",
          "--project-name", "<role_session>", "--file", "<role_compose_file>"]
OPERATIONS = {
    "start_config": ["config", "--format", "json", "--no-interpolate", "--no-env-resolution"],
    "before_ids": ["ps", "--all", "--no-trunc", "--quiet", "--orphans=true"],
    "create_main": ["create", "--no-build", "--pull", "never", "--no-recreate", "main"],
    "created_ids": ["ps", "--all", "--no-trunc", "--quiet", "--orphans=true"],
    "start_main": ["start", "main"],
    "started_ids": ["ps", "--all", "--no-trunc", "--quiet", "--orphans=true"],
}
PYTHON_BUILD_ENV = {
    "GPG_KEY": r"[A-Fa-f0-9]{40}",
    "PYTHON_VERSION": r"3\.12\.[0-9]+",
    "PYTHON_SHA256": r"[a-f0-9]{64}",
}


def _assets(records, context):
    binary, resolver = _resolver(records, context)
    payload = _parse_record(dict(records.records)["runtime"])["payload"]["compose_lifecycle"]
    templates = {key: [str(binary), *PREFIX, *value] for key, value in OPERATIONS.items()}
    if (type(payload) is not dict or set(payload) != {"schema_version", "resolver_sha256", "operations_sha256", "environment_sha256"}
            or payload.get("schema_version") != "anvil.marketing-compose-lifecycle.v1"
            or payload.get("resolver_sha256") != resolver["sha256"]
            or payload.get("operations_sha256") != _digest(templates)
            or payload.get("environment_sha256") != _digest(ENVIRONMENT)):
        raise ValueError("marketing_independent_fixed_compose_lifecycle_required")
    image = _parse_record(dict(records.records)["image"])["payload"]
    if (type(image.get("engine_image_id")) is not str or not re.fullmatch(r"sha256:[a-f0-9]{64}", image["engine_image_id"])
            or type(image.get("engine_defaults")) is not dict
            or set(image["engine_defaults"]) != {"Env", "Entrypoint"}
            or image["engine_defaults"]["Entrypoint"] not in (None, [])
            or image.get("renderer_binding", {}).get("digest") != context["image_digest"]):
        raise ValueError("marketing_independent_compatible_image_defaults_required")
    return binary, resolver["sha256"], image


def _image_profile(actual, image, expected_digest):
    config = actual.get("Config")
    if (actual.get("Id") != image["engine_image_id"] or actual.get("Os") != "linux" or actual.get("Architecture") != "amd64"
            or type(actual.get("RepoDigests")) is not list or expected_digest not in actual["RepoDigests"]
            or type(config) is not dict or config.get("Volumes") or config.get("ExposedPorts") or config.get("Healthcheck")
            or _bounded_canonical({key: config.get(key) for key in ("Env", "Entrypoint")}, DOCUMENT_CAP)
            != _bounded_canonical(image["engine_defaults"], DOCUMENT_CAP)):
        raise ValueError("marketing_actual_cached_image_defaults_required")
    _image_environment(config.get("Env"))


async def _operation(binary, attempt, trial_name, role, operation, plan, context, trial, *, helper_owner=None):
    if operation not in OPERATIONS:
        raise ValueError("marketing_fixed_compose_operation_required")
    if helper_owner is not None:
        from anvil.marketing_native_attester_receiver import _ReceiverOperation
        from anvil.marketing_native_helper_process import run_original_helper

        if type(helper_owner) is not _ReceiverOperation:
            raise ValueError('marketing_fixed_independent_helper_owner_required')
        return await run_original_helper(helper_owner, 'physical:' + operation + ':' + role,
                                          absolute_deadline=context['deadline_monotonic'])
    directory = attempt / "task" / role
    session = trial_name + ("__env" if role == "environment" else "__verifier__trial")
    argv = [str(binary), "--env-file", "/dev/null", "--project-directory", str(directory),
            "--project-name", session, "--file", str(directory / "docker-compose.yaml"), *OPERATIONS[operation]]
    child = None
    ticks = None
    tasks = []
    prefix = "marketing-" + operation + "-" + role
    try:
        child = await asyncio.wait_for(asyncio.create_subprocess_exec(
            *argv, cwd=directory, env=dict(ENVIRONMENT), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=True, close_fds=True, umask=0o077,
        ), timeout=_remaining(context))
        try:
            ticks = _process_identity(child.pid)
        except FileNotFoundError:
            ticks = None
        tasks = [asyncio.create_task(child.wait()),
                 asyncio.create_task(_pump(child.stdout, trial, prefix + "-stdout.txt", plan["bounds"]["stdout_bytes"], context)),
                 asyncio.create_task(_pump(child.stderr, trial, prefix + "-stderr.txt", plan["bounds"]["stderr_bytes"], context))]
        code, stdout, stderr = await asyncio.wait_for(asyncio.gather(*tasks), timeout=_remaining(context))
        metadata = {"argv_sha256": _digest(argv), "pid": child.pid, "start_ticks": ticks, "returncode": code,
                    "stdout": stdout, "stderr": stderr}
        _write_at(trial, prefix + "-process.json", _bounded_canonical(metadata, DOCUMENT_CAP))
        _remaining(context)
        if code != 0:
            raise RuntimeError("marketing_compose_operation_unknown_no_retry")
        return metadata
    finally:
        if child is not None and child.returncode is None and ticks is not None:
            try:
                if _process_identity(child.pid) == ticks:
                    os.killpg(child.pid, signal.SIGKILL)
            except (OSError, ValueError):
                pass
        for task in tasks:
            if not task.done():
                task.cancel()
        joins = [asyncio.gather(*tasks, return_exceptions=True)] if tasks else []
        if child is not None and child.returncode is None:
            joins.append(child.wait())
        if joins:
            await asyncio.wait_for(asyncio.gather(*joins), timeout=_remaining(context))


def _stdout(store, trial, role, operation, metadata, bounds):
    raw = store._read(trial, "marketing-" + operation + "-" + role + "-stdout.txt")
    if len(raw) != metadata["stdout"]["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["stdout"]["sha256"]:
        raise ValueError("marketing_actual_compose_output_changed")
    _stream_outcome(store, trial, "marketing-" + operation + "-" + role + "-stdout.txt", raw, bounds["stdout_bytes"])
    stderr = store._read(trial, "marketing-" + operation + "-" + role + "-stderr.txt")
    if len(stderr) != metadata["stderr"]["bytes"] or hashlib.sha256(stderr).hexdigest() != metadata["stderr"]["sha256"]:
        raise ValueError("marketing_actual_compose_error_output_changed")
    _stream_outcome(store, trial, "marketing-" + operation + "-" + role + "-stderr.txt", stderr, bounds["stderr_bytes"])
    return raw


def _environment(items):
    if type(items) is not list:
        raise ValueError("marketing_actual_image_environment_required")
    result = {}
    for item in items:
        if type(item) is not str or "=" not in item:
            raise ValueError("marketing_exact_image_environment_required")
        key, value = item.split("=", 1)
        if key in result:
            raise ValueError("marketing_duplicate_image_environment_denied")
        result[key] = value
    return result


def _image_environment(items):
    base = _environment(items)
    allowed = {"PATH", "LANG", "LC_ALL", "HOME", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED"} | set(PYTHON_BUILD_ENV)
    if set(base) - allowed:
        raise ValueError("marketing_image_environment_extension_denied")
    for name, pattern in PYTHON_BUILD_ENV.items():
        if name in base and not re.fullmatch(pattern, base[name]):
            raise ValueError("marketing_exact_python_build_metadata_required")
    # Public image-build metadata is not a runtime version/binary/rights proof.
    # Caller still matches full defaults against independent frozen image bytes.
    return base


def _inspect_profile(actual, service, image, session, container_id, *, running, private_verifier=False):
    config, host, state = actual.get("Config"), actual.get("HostConfig"), actual.get("State")
    if (actual.get("Id") != container_id or actual.get("Image") != image["engine_image_id"]
            or type(config) is not dict or type(host) is not dict or type(state) is not dict
            or type(actual.get("RestartCount")) is not int or actual["RestartCount"] != 0):
        raise ValueError("marketing_actual_engine_container_identity_required")
    base = _image_environment(image["engine_defaults"]["Env"])
    expected_env = {**base, **service["environment"]}
    if (config.get("Image") != service["image"] or config.get("User") != "10001:10001"
            or config.get("Cmd") != service["command"] or config.get("WorkingDir") != service["working_dir"]
            or config.get("Entrypoint") not in (None, []) or config.get("Healthcheck")
            or config.get("ExposedPorts") or _environment(config.get("Env")) != expected_env
            or type(config.get("Labels")) is not dict
            or config["Labels"].get("com.docker.compose.project") != session
            or config["Labels"].get("com.docker.compose.service") != "main"):
        raise ValueError("marketing_actual_engine_actor_configuration_changed")
    expected = {"ReadonlyRootfs": True, "Privileged": False, "PublishAllPorts": False, "AutoRemove": False,
                "NetworkMode": "none", "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
                "NanoCpus": service["cpus"] * 1000000000, "Memory": service["mem_limit"],
                "MemorySwap": service["memswap_limit"], "PidsLimit": service["pids_limit"]}
    if _bounded_canonical({key: host.get(key) for key in expected}, DOCUMENT_CAP) != _bounded_canonical(expected, DOCUMENT_CAP):
        raise ValueError("marketing_actual_engine_security_resources_changed")
    for key in ("CapAdd", "Devices", "DeviceRequests", "DeviceCgroupRules", "VolumesFrom", "Links", "ExtraHosts",
                "Dns", "DnsOptions", "DnsSearch", "GroupAdd", "PortBindings", "PidMode", "UTSMode", "UsernsMode"):
        if host.get(key):
            raise ValueError("marketing_actual_engine_extension_denied")
    restart = host.get("RestartPolicy")
    if (type(restart) is not dict or restart.get("Name") not in ("", "no")
            or type(restart.get("MaximumRetryCount")) is not int or restart["MaximumRetryCount"] != 0
            or host.get("IpcMode") != "private"):
        raise ValueError("marketing_actual_engine_restart_ipc_denied")
    expected_tmpfs = {}
    for mount in service["tmpfs"]:
        target, options = mount.split(":", 1)
        if target in expected_tmpfs:
            raise ValueError("marketing_duplicate_tmpfs_denied")
        expected_tmpfs[target] = options
    if host.get("Tmpfs") != expected_tmpfs:
        raise ValueError("marketing_actual_engine_tmpfs_changed")
    mounts = actual.get("Mounts")
    if type(mounts) is not list:
        raise ValueError("marketing_actual_engine_mounts_required")
    binds = {row["target"]: row for row in service["volumes"]}
    seen = set()
    for mount in mounts:
        if type(mount) is not dict or mount.get("Destination") in seen:
            raise ValueError("marketing_actual_engine_mount_set_changed")
        destination = mount.get("Destination")
        seen.add(destination)
        if mount.get("Type") == "tmpfs" and destination in expected_tmpfs and mount.get("RW") is True:
            continue
        if (destination not in binds or mount.get("Type") != "bind"
                or mount.get("Source") != binds[destination]["source"]
                or mount.get("RW") is not (not binds[destination]["read_only"])
                or mount.get("Propagation") != "rprivate"):
            raise ValueError("marketing_actual_engine_bind_custody_changed")
    if not set(binds) <= seen:
        raise ValueError("marketing_actual_engine_bind_missing")
    if private_verifier:
        if (running is not True or service['command'] != ['python3', '-I', '-B', '-m', 'anvil_harbor.marketing_private_verifier']
                or state.get('OOMKilled') is not False or state.get('Error') != ''
                or type(state.get('StartedAt')) is not str or state['StartedAt'].startswith('0001-')
                or not state['StartedAt']
                or not (state.get('Running') is True and type(state.get('Pid')) is int and state['Pid'] > 0
                        and state.get('Status') == 'running'
                        or state.get('Running') is False and type(state.get('Pid')) is int and state['Pid'] == 0
                        and state.get('Status') == 'exited' and type(state.get('ExitCode')) is int and state['ExitCode'] == 0)
                or any(state.get(k) is not False for k in ('Paused', 'Restarting', 'Dead'))):
            raise ValueError('marketing_actual_private_verifier_started_or_completed_required')
    elif (state.get("Running") is not running or type(state.get("Pid")) is not int
            or (state["Pid"] <= 0 if running else state["Pid"] != 0)
            or state.get("Status") != ("running" if running else "created")
            or any(state.get(key) is not False for key in ("Paused", "Restarting", "Dead"))):
        raise ValueError("marketing_actual_engine_role_state_required")
    networks = actual.get("NetworkSettings", {}).get("Networks", {})
    if type(networks) is not dict or set(networks) - {"none"}:
        raise ValueError("marketing_actual_engine_network_extension_denied")


def _ownership(claim, entry, role, session, actual):
    return {"schema_version": "anvil.marketing-owned-container.v1",
            **{key: claim[key] for key in ("job_id", "request_sha256", "plan_sha256")},
            **{key: entry[key] for key in ("framework_trial_id", "operation_nonce")},
            "role": role, "session_id": session, "container_id": actual["Id"],
            "image_id": actual["Image"], "inspect_config_sha256": _digest({
                key: actual[key] for key in ("Id", "Image", "Name", "Config", "HostConfig", "Mounts")})}


async def _start(store, request, records, role, *, opening=False, private=False, helper_owner=None):
    root, claim, plan = _context_version(store, request, opening=opening)
    trial = None
    created_owned = False
    try:
        if private and (not opening or helper_owner is None):
            raise ValueError('marketing_private_physical_requires_independent_receiver')
        _framework_entry(store, root, claim)
        _read_pair(store, root, claim, plan, opening=opening)
        _check(store, request, role=role, stage="before_start", opening=opening)
        context = _parse_record(store._read(root, "component-context.json"))
        binary, resolver_sha, image = _assets(records, context)
        if records.request_sha256 != claim["request_sha256"] or role not in {"environment", "tests"}:
            raise ValueError("marketing_bound_physical_role_required")
        cleanup = plan["bounds"]["cleanup_seconds"]
        if type(cleanup) is not int or not 1 <= cleanup < _remaining(context) - 1:
            raise ValueError("marketing_existing_lifecycle_cleanup_reserve_required")
        work_context = {**context, "deadline_monotonic": context["deadline_monotonic"] - cleanup}
        if private:
            work_context['deadline_monotonic'] -= plan['bounds']['verifier_seconds'] if role == 'environment' else 8
        entry = _parse_record(store._read(root, "framework-entry.json"))
        _write_at(root, role + "-physical-start-intent.json", _bounded_canonical({
            "schema_version": ('anvil.marketing-physical-start-intent.v3' if private else
                               'anvil.marketing-physical-start-intent.v2'), "role": role, "job_id": claim["job_id"],
            "framework_trial_id": entry["framework_trial_id"],
            "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
            "resolver_sha256": resolver_sha, "operation_nonce": context["operation_nonce"],
            "deadline_monotonic": context["deadline_monotonic"], "scope": claim["scope"],
            "work_deadline_monotonic": work_context["deadline_monotonic"], "cleanup_reserve_seconds": cleanup,
        }, DOCUMENT_CAP))
        trial = store._walk(root, ["trials", claim["trial_name"]])
        attempt = store.parent / claim["trial_name"]
        async def run(operation):
            metadata = await _operation(binary, attempt, claim["trial_name"], role, operation, plan, work_context, trial,
                                        helper_owner=helper_owner)
            if helper_owner is not None:
                _write_at(trial, 'marketing-' + operation + '-' + role + '-process.json', _bounded_canonical(metadata, DOCUMENT_CAP))
            return _stdout(store, trial, role, operation, metadata, plan["bounds"])

        stdout = await run("start_config")
        document = json.loads(stdout, object_pairs_hook=_pairs)
        _write_at(trial, "marketing-start-compose-" + role + ".json", _bounded_canonical(document, DOCUMENT_CAP))
        actual_profile = _profile(store, root, claim, plan, role, "start")
        if _digest(actual_profile) != _digest(_profile(store, root, claim, plan, role, "preflight")):
            raise ValueError("marketing_actual_start_preflight_changed")
        if (await run("before_ids")).strip():
            raise RuntimeError("marketing_existing_role_project_denied_no_reuse")
        cached = await _request("image_inspect", image["engine_image_id"][7:], deadline=work_context["deadline_monotonic"], private=private)
        _write_at(root, role + "-precreate-image-inspect.json", _bounded_canonical(cached, DOCUMENT_CAP))
        _image_profile(cached, image, context["image_digest"])
        _check(store, request, role=role, stage="before_start", opening=opening)
        await run("create_main")
        raw_id = await run("created_ids")
        if not re.fullmatch(rb"[a-f0-9]{64}\n?", raw_id):
            raise RuntimeError("marketing_exact_created_container_required")
        container_id = raw_id.strip().decode("ascii")
        session = claim["trial_name"] + ("__env" if role == "environment" else "__verifier__trial")
        before = await _request("inspect", container_id, deadline=work_context["deadline_monotonic"], private=private)
        _write_at(root, role + "-created-engine-inspect.json", _bounded_canonical(before, DOCUMENT_CAP))
        _inspect_profile(before, actual_profile["services"]["main"], image, session, container_id, running=False)
        # Keep actual created ownership evidence before the single start action.
        _write_at(root, role + "-created-container.json", _bounded_canonical({
            "schema_version": "anvil.marketing-created-container.v1", "container_id": container_id,
            "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
            "role": role, "session_id": session, "inspect_sha256": _digest(before),
        }, DOCUMENT_CAP))
        _write_at(root, role + "-container-before-start.json", _bounded_canonical({
            "schema_version": "anvil.marketing-created-container-binding.v1",
            "binding": _ownership(claim, entry, role, session, before),
            "created_inspect_sha256": _digest(before), "state": "created_observed_NOT_start_success",
            "native_qualified": False,
        }, DOCUMENT_CAP))
        created_owned = True
        _check(store, request, role=role, stage="before_start", opening=opening)
        await run("start_main")
        if await run("started_ids") != raw_id:
            raise RuntimeError("marketing_started_project_identity_changed")
        after = await _request("inspect", container_id, deadline=work_context["deadline_monotonic"], private=private)
        _write_at(root, role + "-started-engine-inspect.json", _bounded_canonical(after, DOCUMENT_CAP))
        _inspect_profile(after, actual_profile["services"]["main"], image, session, container_id,
                         running=True, private_verifier=private and role == 'tests')
        binding = _ownership(claim, entry, role, session, after)
        _remaining(work_context)
        _write_at(root, role + "-container.json", _bounded_canonical(binding, DOCUMENT_CAP))
        return binding  # Actual identity observation only, not native/whole-tree qualification.
    except BaseException as failure:
        if created_owned:
            from anvil.marketing_native_stop import _stop

            try:
                observed = await _stop(store, request, role, created_only=True, opening=opening, private=private)
                _write_at(root, role + "-partial-start-cleanup.json", _bounded_canonical({
                    "schema_version": "anvil.marketing-partial-start-cleanup.v1",
                    "stop_observation_sha256": _digest(observed), "failure_type": type(failure).__name__,
                    "startup_outcome": "unknown_not_promoted", "whole_actor_stopped": False,
                    "native_qualified": False, "replay_permitted": False,
                }, DOCUMENT_CAP))
            except asyncio.CancelledError:
                raise  # Repeated cancellation cannot become successful cleanup.
            except Exception as cleanup_failure:
                try:
                    _write_at(root, role + "-partial-start-cleanup-unknown.json", _bounded_canonical({
                        "schema_version": "anvil.marketing-partial-start-cleanup-unknown.v1",
                        "failure_type": type(failure).__name__, "cleanup_failure_type": type(cleanup_failure).__name__,
                        "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
                        "native_qualified": False, "replay_permitted": False,
                    }, DOCUMENT_CAP))
                except OSError:
                    pass
        raise  # Retain original startup failure; never return a startup success.
    finally:
        if trial is not None:
            os.close(trial)
        os.close(root)


async def start_owned_role(request, role):
    marketing_native_gate()
    records = resolve_marketing_records(request)
    with MarketingAttemptStore() as store:
        return await _start(store, request, records, role)


async def _event(store, request, raw, *, opening=False, private=False, helper_owner=None):
    if private and helper_owner is None:
        from anvil.marketing_native_enrollment_client import request_original_physical_event
        from anvil.marketing_native_private_records import resolve_private_marketing_records

        records = resolve_private_marketing_records(request)
        root, _, _ = _context_version(store, request, opening=True)
        try:
            return await request_original_physical_event(store, root, request, records, raw)
        finally:
            os.close(root)
    event = _parse_record(raw)
    root, claim, plan = _context_version(store, request, opening=opening)
    try:
        _framework_entry(store, root, claim)
        entry = _parse_record(store._read(root, "framework-entry.json"))
        role = event.get("role")
        if (set(event) != EVENT_FIELDS or event.get("schema_version") != "anvil.marketing-component-event.v1"
                or event.get("event") not in {"before_start", "start", "logs"} or role not in {"environment", "tests"}
                or any(event.get(key) != claim[key] for key in ("job_id", "request_sha256", "plan_sha256"))
                or any(event.get(key) != entry[key] for key in ("operation_nonce", "framework_trial_id"))
                or event.get("session_id") != claim["trial_name"] + ("__env" if role == "environment" else "__verifier__trial")):
            raise ValueError("marketing_bound_fixed_physical_event_required")
        _read_pair(store, root, claim, plan, opening=opening)
        if event["event"] == "before_start":
            try:
                store._read(root, role + "-mount-receipt.json")
            except FileNotFoundError:
                (_handoff_actor if role == "environment" else _handoff_verifier)(store, request, opening=opening)
            _check(store, request, role=role, stage="before_start", opening=opening)
        elif event["event"] == "start":
            from anvil.marketing_native_private_records import resolve_private_marketing_records
            from anvil.marketing_native_records import resolve_marketing_opening_records

            records = (resolve_private_marketing_records(request) if private else
                       resolve_marketing_opening_records(request) if opening else resolve_marketing_records(request))
            await _start(store, request, records, role, opening=opening, private=private, helper_owner=helper_owner)
        else:
            _check(store, request, role=role, stage="before_business" if role == "environment" else "before_collection",
                   opening=opening)
        return {**event, "status": "recorded"}
    finally:
        os.close(root)
