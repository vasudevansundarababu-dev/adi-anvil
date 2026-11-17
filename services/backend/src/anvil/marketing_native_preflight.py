"""Closed fixed Compose-config producer; declarations never stand in for output.

Exact resolver assets and real spawn/import/transport/cleanup qualification are
still unavailable. No config command, native start or daemon operation is admitted.
"""

import asyncio
import hashlib
import json
import os
import re
import signal
import stat
from pathlib import Path

from anvil.marketing_native_attempt import MarketingAttemptStore, _owned, _write_at
from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    _bounded_canonical,
    _digest,
    _pairs,
    marketing_native_gate,
)
from anvil.marketing_native_collector import EVENT_FIELDS
from anvil.marketing_native_control import _remaining
from anvil.marketing_native_launcher import _process_identity, _pump
from anvil.marketing_native_mounts import _context_version
from anvil.marketing_native_reconcile import _context_status_version
from anvil.marketing_native_records import (
    _parse_record,
    resolve_marketing_opening_records,
    resolve_marketing_records,
)
from anvil.marketing_native_start import _framework_entry, _profile

ENVIRONMENT = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/nonexistent",
               "DOCKER_CONFIG": "/nonexistent", "DOCKER_HOST": "unix:///run/docker.sock"}
COMMAND_TAIL = ["--env-file", "/dev/null", "--project-directory", "<role_directory>",
                "--project-name", "<role_session>", "--file", "<role_compose_file>",
                "config", "--format", "json", "--no-interpolate", "--no-env-resolution"]


def _resolver(records, context):
    assets = _parse_record(dict(records.records)["runtime"])["payload"]["compose_resolver"]
    if (type(assets) is not dict or set(assets) != {"schema_version", "binary", "bytes", "sha256",
                                                  "command_template_sha256", "environment_sha256"}
            or assets.get("schema_version") != "anvil.marketing-compose-resolver.v1"
            or type(assets.get("binary")) is not str or type(assets.get("bytes")) is not int
            or not 1 <= assets["bytes"] <= 9007199254740991
            or type(assets.get("sha256")) is not str or not re.fullmatch(r"[a-f0-9]{64}", assets["sha256"])
            or assets.get("environment_sha256") != _digest(ENVIRONMENT)
            or assets.get("command_template_sha256") != _digest([assets["binary"], *COMMAND_TAIL])):
        raise ValueError("marketing_independent_fixed_compose_resolver_required")
    path = Path(assets["binary"])
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("marketing_canonical_compose_binary_required")
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _owned(os.fstat(parent), 0, directory=True)
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
            _owned(os.fstat(parent), 0, directory=True)
    finally:
        os.close(parent)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        _owned(before, 0)
        if before.st_size != assets["bytes"] or not before.st_mode & stat.S_IXUSR:
            raise ValueError("marketing_owned_pinned_resolver_executable_required")
        digest, count = hashlib.sha256(), 0
        while True:
            _remaining(context)
            raw = os.read(fd, 65536)
            if not raw:
                break
            count += len(raw)
            if count > before.st_size:
                raise ValueError("marketing_resolver_binary_grew")
            digest.update(raw)
        after = os.fstat(fd)
        if (count != before.st_size or digest.hexdigest() != assets["sha256"]
                or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError("marketing_resolver_binary_changed")
    finally:
        os.close(fd)
    return path, assets


async def _resolve_role(binary, attempt, trial_name, role, bounds, context, trial, *, private=False,
                        store=None, root=None, request=None, records=None):
    if private:
        from anvil.marketing_native_enrollment_client import request_original_helper

        metadata = await request_original_helper(store, root, request, records, 'preflight:' + role,
                                                  work_deadline=context['deadline_monotonic'])
        if metadata.get('returncode') != 0 or type(metadata.get('returncode')) is not int:
            raise RuntimeError('marketing_original_private_preflight_helper_failed_no_retry')
        return metadata
    directory = attempt / "task" / role
    session = trial_name + ("__env" if role == "environment" else "__verifier__trial")
    argv = [str(binary), "--env-file", "/dev/null", "--project-directory", str(directory),
            "--project-name", session, "--file", str(directory / "docker-compose.yaml"),
            "config", "--format", "json", "--no-interpolate", "--no-env-resolution"]
    child = None
    ticks = None
    tasks = []
    try:
        child = await asyncio.wait_for(asyncio.create_subprocess_exec(
            *argv, cwd=directory, env=dict(ENVIRONMENT), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=True, close_fds=True, umask=0o077,
        ), timeout=_remaining(context))
        try:
            ticks = _process_identity(child.pid)
        except FileNotFoundError:
            # A completed child can exit before /proc observation. Its actual
            # return/output can be retained; no process cleanup proof follows.
            ticks = None
        tasks = [asyncio.create_task(child.wait()),
                 asyncio.create_task(_pump(child.stdout, trial, "marketing-preflight-stdout-" + role + ".json",
                                           bounds["stdout_bytes"], context)),
                 asyncio.create_task(_pump(child.stderr, trial, "marketing-preflight-stderr-" + role + ".log",
                                           bounds["stderr_bytes"], context))]
        code, stdout, stderr = await asyncio.wait_for(asyncio.gather(*tasks), timeout=_remaining(context))
        _remaining(context)
        return {"argv_sha256": _digest(argv), "pid": child.pid, "start_ticks": ticks, "returncode": code,
                "stdout_sha256": stdout["sha256"], "stderr_sha256": stderr["sha256"]}
    finally:
        if child is not None and child.returncode is None and ticks is not None:
            try:
                if _process_identity(child.pid) == ticks:
                    os.killpg(child.pid, signal.SIGKILL)
            except (OSError, ValueError):
                pass  # Unknown; no retry or cleanup-success receipt.
        for task in tasks:
            if not task.done():
                task.cancel()
        joins = [asyncio.gather(*tasks, return_exceptions=True)] if tasks else []
        if child is not None and child.returncode is None:
            joins.append(child.wait())
        if joins:
            await asyncio.wait_for(asyncio.gather(*joins), timeout=_remaining(context))


async def _produce(store, request, records, *, opening=False, private=False):
    if type(private) is not bool or private and not opening:
        raise ValueError('marketing_explicit_private_preflight_variant_required')
    root, claim, plan = _context_version(store, request, opening=opening)
    try:
        if records.request_sha256 != claim["request_sha256"]:
            raise ValueError("marketing_preflight_current_root_records_required")
        status = _context_status_version(store, root, claim, plan, opening=opening)
        if status["same_boot_observed"] is not True or status["deadline_elapsed_observed"] is not False:
            raise ValueError("marketing_current_preflight_context_required")
        context = _parse_record(store._read(root, "component-context.json"))
        binary, assets = _resolver(records, context)
        _write_at(root, "paired-preflight-intent.json", _bounded_canonical({
            "schema_version": ('anvil.marketing-paired-preflight-intent.v2' if private else
                               'anvil.marketing-paired-preflight-intent.v1'),
            "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
            "context_sha256": status["context_sha256"], "resolver_sha256": assets["sha256"],
            "deadline_monotonic": context["deadline_monotonic"], "scope": claim["scope"],
            **({'work_deadline_monotonic': context['deadline_monotonic'] - plan['bounds']['cleanup_seconds']
                - plan['bounds']['verifier_seconds']} if private else {}),
        }, DOCUMENT_CAP))
        work_context = ({**context, 'deadline_monotonic': context['deadline_monotonic'] - plan['bounds']['cleanup_seconds']
                         - plan['bounds']['verifier_seconds']} if private else context)
        trial = store._walk(root, ["trials", claim["trial_name"]])
        try:
            results = {}
            for role in ("environment", "tests"):
                process = await _resolve_role(
                    binary, store.parent / claim["trial_name"], claim["trial_name"], role, plan["bounds"], work_context, trial,
                    private=private, store=store, root=root, request=request, records=records)
                stdout = store._read(trial, "marketing-preflight-stdout-" + role + ".json")
                stderr = store._read(trial, "marketing-preflight-stderr-" + role + ".log")
                if (process["returncode"] != 0 or not stdout
                        or hashlib.sha256(stdout).hexdigest() != process["stdout_sha256"]
                        or hashlib.sha256(stderr).hexdigest() != process["stderr_sha256"]):
                    raise RuntimeError("marketing_actual_compose_resolution_failed_no_retry")
                document = json.loads(stdout, object_pairs_hook=_pairs)
                if type(document) is not dict:
                    raise ValueError("marketing_actual_compose_document_required")
                canonical = _bounded_canonical(document, DOCUMENT_CAP)
                _write_at(trial, "marketing-preflight-compose-" + role + ".json", canonical)
                # Validate the ACTUAL resolver output against independent pins
                # and declared isolation. Never construct a success snapshot
                # from the declaration or drop unexpected output fields.
                _profile(store, root, claim, plan, role, "preflight")
                results[role] = {**process, "profile_sha256": hashlib.sha256(canonical).hexdigest()}
            _remaining(context)
            receipt = {"schema_version": ('anvil.marketing-paired-preflight-receipt.v2' if private else
                                         'anvil.marketing-paired-preflight-receipt.v1'),
                       "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
                       "context_sha256": status["context_sha256"], "resolver_sha256": assets["sha256"],
                       "roles": results, "native_qualified": False, "roles_started": False,
                       "replay_permitted": False}
            _write_at(root, "paired-preflight-receipt.json", _bounded_canonical(receipt, DOCUMENT_CAP))
            return receipt
        finally:
            os.close(trial)
    finally:
        os.close(root)


async def produce_paired_preflight(request):
    marketing_native_gate()
    records = resolve_marketing_records(request)
    with MarketingAttemptStore() as store:
        return await _produce(store, request, records)


def _stream_outcome(store, folder, filename, raw, cap):
    if type(cap) is not int or not 1 <= cap <= DOCUMENT_CAP or len(raw) > cap:
        raise ValueError("marketing_original_stream_limit_required")
    outcome = _parse_record(store._read(folder, filename + ".outcome.json"))
    expected = {"schema_version": "anvil.marketing-stream-outcome.v1",
                "state": "complete_stream_bytes_retained", "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(), "prefix_fsynced": True,
                "failure_type": None, "evidence_failure_type": None, "evidence_reserve_seconds": 1,
                "native_qualified": False, "replay_permitted": False}
    if _bounded_canonical(outcome, DOCUMENT_CAP) != _bounded_canonical(expected, DOCUMENT_CAP):
        raise ValueError("marketing_complete_bound_stream_evidence_required")


def _read_pair(store, root, claim, plan, *, opening=False):
    status = _context_status_version(store, root, claim, plan, opening=opening)
    if status["same_boot_observed"] is not True or status["deadline_elapsed_observed"] is not False:
        raise ValueError("marketing_current_retained_preflight_required")
    intent = _parse_record(store._read(root, "paired-preflight-intent.json"))
    receipt = _parse_record(store._read(root, "paired-preflight-receipt.json"))
    private = intent.get('schema_version') == 'anvil.marketing-paired-preflight-intent.v2'
    if (set(intent) != {"schema_version", "request_sha256", "plan_sha256", "context_sha256", "resolver_sha256",
                       "deadline_monotonic", "scope"} | ({'work_deadline_monotonic'} if private else set())
            or private and not opening
            or intent["schema_version"] != ('anvil.marketing-paired-preflight-intent.v2' if private else
                                            'anvil.marketing-paired-preflight-intent.v1')
            or any(intent[key] != claim[key] for key in ("request_sha256", "plan_sha256", "scope"))
            or intent["context_sha256"] != status["context_sha256"]
            or intent["deadline_monotonic"] != _parse_record(store._read(root, "component-context.json"))["deadline_monotonic"]
            or set(receipt) != {"schema_version", "request_sha256", "plan_sha256", "context_sha256", "resolver_sha256",
                                "roles", "native_qualified", "roles_started", "replay_permitted"}
            or receipt["schema_version"] != ('anvil.marketing-paired-preflight-receipt.v2' if private else
                                             'anvil.marketing-paired-preflight-receipt.v1')
            or any(receipt[key] != intent[key] for key in ("request_sha256", "plan_sha256", "context_sha256", "resolver_sha256"))
            or any(receipt[key] is not False for key in ("native_qualified", "roles_started", "replay_permitted"))
            or type(receipt["roles"]) is not dict or set(receipt["roles"]) != {"environment", "tests"}):
        raise ValueError("marketing_original_paired_preflight_receipt_required")
    if private and intent['work_deadline_monotonic'] != intent['deadline_monotonic'] - plan['bounds']['cleanup_seconds'] - plan['bounds']['verifier_seconds']:
        raise ValueError('marketing_original_private_preflight_partition_changed')
    trial = store._walk(root, ["trials", claim["trial_name"]])
    try:
        for role in ("environment", "tests"):
            metadata = receipt["roles"][role]
            if (type(metadata) is not dict or set(metadata) != {"argv_sha256", "pid", "start_ticks", "returncode",
                                                               "stdout_sha256", "stderr_sha256", "profile_sha256"}
                        | ({'stdout', 'stderr', 'helper_receipt_sha256', 'helper_cleanup_receipt_sha256'} if private else set())
                    or type(metadata["returncode"]) is not int or metadata["returncode"] != 0
                    or type(metadata["pid"]) is not int or metadata["pid"] <= 1
                    or metadata["start_ticks"] is not None and (type(metadata["start_ticks"]) is not int or metadata["start_ticks"] <= 0)
                    or any(type(metadata[key]) is not str or not re.fullmatch(r"[a-f0-9]{64}", metadata[key])
                           for key in ("argv_sha256", "stdout_sha256", "stderr_sha256", "profile_sha256"))):
                raise ValueError("marketing_actual_resolver_process_metadata_required")
            if private:
                tag = hashlib.sha256(('preflight:' + role).encode('ascii')).hexdigest()
                for name, pin_name in (('result', 'helper_receipt_sha256'), ('cleanup', 'helper_cleanup_receipt_sha256')):
                    raw = store._read(root, 'helper-exec-' + tag + '-' + name + '.json')
                    if hashlib.sha256(raw).hexdigest() != metadata[pin_name]:
                        raise ValueError('marketing_original_preflight_helper_custody_changed')
                cleanup = _parse_record(store._read(root, 'helper-exec-' + tag + '-cleanup.json'))
                if (cleanup['owned_exit_and_reap_observed'] is not True or cleanup['returncode'] != 0
                        or cleanup['cleanup_failures'] or cleanup['primary_failure_type'] is not None
                        or cleanup['work_deadline_monotonic'] != intent['work_deadline_monotonic']):
                    raise ValueError('marketing_original_preflight_helper_cleanup_unknown')
            stdout = store._read(trial, "marketing-preflight-stdout-" + role + ".json")
            stderr = store._read(trial, "marketing-preflight-stderr-" + role + ".log")
            _stream_outcome(store, trial, "marketing-preflight-stdout-" + role + ".json", stdout, plan["bounds"]["stdout_bytes"])
            _stream_outcome(store, trial, "marketing-preflight-stderr-" + role + ".log", stderr, plan["bounds"]["stderr_bytes"])
            actual = _profile(store, root, claim, plan, role, "preflight")
            if (len(stdout) > plan["bounds"]["stdout_bytes"] or len(stderr) > plan["bounds"]["stderr_bytes"]
                    or hashlib.sha256(stdout).hexdigest() != metadata["stdout_sha256"]
                    or hashlib.sha256(stderr).hexdigest() != metadata["stderr_sha256"]
                    or _digest(actual) != metadata["profile_sha256"]
                    or _bounded_canonical(json.loads(stdout, object_pairs_hook=_pairs), DOCUMENT_CAP)
                    != _bounded_canonical(actual, DOCUMENT_CAP)):
                raise ValueError("marketing_retained_actual_preflight_bytes_changed")
        return receipt
    finally:
        os.close(trial)


async def _event(store, request, raw, *, opening=False):
    event = _parse_record(raw)
    root, claim, plan = _context_version(store, request, opening=opening)
    try:
        _framework_entry(store, root, claim)
        entry = _parse_record(store._read(root, "framework-entry.json"))
        if (set(event) != EVENT_FIELDS or event.get("schema_version") != "anvil.marketing-component-event.v1"
                or event.get("event") != "preflight" or event.get("role") not in {"environment", "tests"}
                or any(event.get(key) != claim[key] for key in ("job_id", "request_sha256", "plan_sha256"))
                or any(event.get(key) != entry[key] for key in ("operation_nonce", "framework_trial_id"))
                or event.get("session_id") != claim["trial_name"] + (
                    "__env" if event["role"] == "environment" else "__verifier__trial")):
            raise ValueError("marketing_bound_preflight_event_required")
        # The qualified operator recipe must produce both actual configs before
        # native launch. Component events only revalidate those retained bytes;
        # no late resolver invocation or repeated prepare/config action.
        _read_pair(store, root, claim, plan, opening=opening)
        return {**event, "status": "recorded"}
    finally:
        os.close(root)


async def produce_opening_paired_preflight(request):
    marketing_native_gate()
    records = resolve_marketing_opening_records(request)
    with MarketingAttemptStore() as store:
        return await _produce(store, request, records, opening=True)
