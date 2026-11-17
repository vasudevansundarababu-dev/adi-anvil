"""Closed fixed framework launcher with a pre-module startup pipe.

Neither exec/import closure nor whole-process-tree cleanup is qualified here.
The independent runtime launcher assets do not exist/admit execution yet.
"""

import asyncio
import hashlib
import os
import signal
import stat
from pathlib import Path
from time import monotonic

from anvil.marketing_native_attempt import MarketingAttemptStore, _owned, _write_at
from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    _bounded_canonical,
    _digest,
    marketing_native_gate,
)
from anvil.marketing_native_control import _remaining
from anvil.marketing_native_listener import _listen
from anvil.marketing_native_mounts import _context_version
from anvil.marketing_native_reconcile import _context_status_version
from anvil.marketing_native_records import (
    _parse_record,
    resolve_marketing_opening_records,
    resolve_marketing_records,
)

BOOTSTRAP = """import sys
if sys.version_info[:2]!=(3,12) or sys.platform!='linux' or sys.flags.isolated!=1 or sys.flags.ignore_environment!=1 or sys.flags.no_user_site!=1 or not sys.dont_write_bytecode: raise RuntimeError('qualified_linux_python312_isolated_runtime_required')
import math,os,select,time
if os.uname().machine!='x86_64' or os.geteuid()!=0 or os.getegid()!=0: raise RuntimeError('qualified_QA_root_amd64_runtime_required')
fd=int(sys.argv[1]); deadline=float(sys.argv[2]); trial=sys.argv[3]
left=deadline-time.monotonic()
if not math.isfinite(left) or not 0<left<=600: raise RuntimeError('startup_deadline')
if not select.select([fd],[],[],left)[0] or os.read(fd,2)!=b'G': raise RuntimeError('startup_unknown')
os.close(fd)
if time.monotonic()>=deadline: raise RuntimeError('startup_deadline')
sys.argv=['anvil_harbor.marketing',trial]
import runpy
runpy.run_module('anvil_harbor.marketing',run_name='__main__',alter_sys=True)
"""
OPENING_BOOTSTRAP = BOOTSTRAP.replace("'anvil_harbor.marketing'", "'anvil_harbor.marketing_opening'")
PRIVATE_OPENING_BOOTSTRAP = OPENING_BOOTSTRAP.replace(
    'fd=int(sys.argv[1]); deadline=float(sys.argv[2]); trial=sys.argv[3]',
    "if len(sys.argv)!=6: raise RuntimeError('private_fixed_arguments_required')\n"
    'from anvil.marketing_native_actor_hardening import harden_graph\n'
    'harden_graph()\n'
    "ready=int(sys.argv[5])\nif os.write(ready,b'R')!=1: raise RuntimeError('private_hardening_ready_unknown')\nos.close(ready)\n"
    'private_program_pin=sys.argv[4]\n'
    'fd=int(sys.argv[1]); deadline=float(sys.argv[2]); trial=sys.argv[3]',
).replace("sys.argv=['anvil_harbor.marketing_opening',trial]",
          "sys.argv=['anvil_harbor.marketing_private_runtime',trial,private_program_pin]")
PRIVATE_OPENING_BOOTSTRAP = PRIVATE_OPENING_BOOTSTRAP.replace(
    "runpy.run_module('anvil_harbor.marketing_opening'", "runpy.run_module('anvil_harbor.marketing_private_runtime'"
)
ENVIRONMENT_TEMPLATE = {
    "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "<attempt_root>",
    "ANVIL_MARKETING_ATTEMPT_ROOT": "<attempt_root>", "ANVIL_MARKETING_CONTEXT_SHA256": "<context_sha256>",
}
PRIVATE_ENVIRONMENT_TEMPLATE = {**ENVIRONMENT_TEMPLATE, 'ANVIL_ROOT': '/proc/self/fd'}


def _runtime_assets(records, plan, context, *, opening=False, private=False):
    payload = _parse_record(dict(records.records)["runtime"])["payload"]
    launch = payload["launcher"]
    if type(private) is not bool or private and not opening:
        raise ValueError('marketing_explicit_private_opening_runtime_required')
    bootstrap = PRIVATE_OPENING_BOOTSTRAP if private else OPENING_BOOTSTRAP if opening else BOOTSTRAP
    if (type(launch) is not dict or set(launch) != {"schema_version", "interpreter", "interpreter_bytes", "bootstrap_sha256"}
            | ({'private_program_sha256'} if private else set())
            or launch["schema_version"] != ("anvil.marketing-launcher-assets.v3" if private else
                                            "anvil.marketing-launcher-assets.v2" if opening
                                            else "anvil.marketing-launcher-assets.v1")
            or launch["bootstrap_sha256"] != hashlib.sha256(bootstrap.encode()).hexdigest()
            or type(launch["interpreter"]) is not str or type(launch["interpreter_bytes"]) is not int
            or not 1 <= launch["interpreter_bytes"] <= 9007199254740991):
        raise ValueError("marketing_independent_launcher_assets_required")
    if private:
        from anvil.marketing_native_verifier_renderer import (
            private_context_assets,
            validate_private_program,
        )

        _, program = private_context_assets(records)
        if hashlib.sha256(validate_private_program(program)).hexdigest() != launch['private_program_sha256']:
            raise ValueError('marketing_original_private_program_launcher_pin_changed')
    path = Path(launch["interpreter"])
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("marketing_exact_runtime_interpreter_path_required")
    template = [str(path), "-I", "-B", "-c", bootstrap, "<startup_fd>", "<deadline_monotonic>", "<trial_json>"]
    if private:
        template.extend(['<private_program_sha256>', '<hardening_ready_fd>'])
    if (_digest(template) != plan["runtime"]["command_sha256"]
            or _digest(PRIVATE_ENVIRONMENT_TEMPLATE if private else ENVIRONMENT_TEMPLATE) != plan["runtime"]["environment_sha256"]
            or _bounded_canonical(payload.get("renderer_binding"), DOCUMENT_CAP)
            != _bounded_canonical(plan["runtime"], DOCUMENT_CAP)):
        raise ValueError("marketing_exact_launcher_command_environment_required")
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
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        _owned(before, 0)
        if not before.st_mode & stat.S_IXUSR or before.st_size != launch["interpreter_bytes"]:
            raise ValueError("marketing_pinned_executable_interpreter_required")
        digest = hashlib.sha256()
        count = 0
        while True:
            _remaining(context)
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            count += len(chunk)
            if count > before.st_size:
                raise ValueError("marketing_runtime_interpreter_grew")
            digest.update(chunk)
        after = os.fstat(fd)
        def identity(v):
            return (v.st_dev, v.st_ino, v.st_size, v.st_mtime_ns, v.st_ctime_ns)
        if (identity(before) != identity(after) or count != before.st_size
                or digest.hexdigest() != plan["runtime"]["interpreter_sha256"]):
            raise ValueError("marketing_runtime_interpreter_changed")
        return path, identity(before)
    finally:
        os.close(fd)


def _process_identity(pid):
    with open("/proc/" + str(pid) + "/stat", encoding="ascii") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096 or not raw.startswith(str(pid) + " (") or ") " not in raw:
        raise ValueError("marketing_actual_child_stat_required")
    fields = raw.rsplit(") ", 1)[1].split()
    if (len(fields) < 20 or int(fields[1]) != os.getpid()
            or int(fields[2]) != pid or int(fields[3]) != pid):
        raise ValueError("marketing_owned_child_session_required")
    return int(fields[19])


async def _pump(stream, root, filename, cap, context):
    if type(cap) is not int or not 1 <= cap <= DOCUMENT_CAP:
        raise ValueError("marketing_existing_output_cap_required")
    if type(filename) is not str or "/" in filename or filename in {"", ".", ".."}:
        raise ValueError("marketing_fixed_private_stream_filename_required")
    folder = os.dup(root)
    fd = None
    total, digest = 0, hashlib.sha256()
    complete = False
    failure = None
    # Reserve evidence work INSIDE the original lifecycle, never extend it.
    work_context = {**context, "deadline_monotonic": context["deadline_monotonic"] - 1}
    try:
        fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
        os.fchmod(fd, 0o600)
        while True:
            chunk = await asyncio.wait_for(stream.read(8192), timeout=_remaining(work_context))
            if not chunk:
                break
            allowed = min(len(chunk), cap - total)
            view = memoryview(chunk)[:allowed]
            while view:
                _remaining(work_context)
                written = os.write(fd, view)
                if not 0 < written <= len(view):
                    raise OSError("marketing_framework_output_write_unknown")
                digest.update(view[:written])
                total += written
                view = view[written:]
            if allowed != len(chunk):
                raise ValueError("marketing_framework_output_capacity")
        _remaining(context)
        complete = True
        return {"bytes": total, "sha256": digest.hexdigest()}
    except BaseException as exc:
        failure = exc
        raise
    finally:
        try:
            if fd is not None:
                durable = False
                evidence_error = None
                # Do not let an expired _remaining check skip every evidence
                # attempt. Blocking fsync still requires actual supervisor proof.
                try:
                    os.fsync(fd)
                    os.fsync(folder)
                    durable = True
                except BaseException as exc:
                    evidence_error = exc
                try:
                    _write_at(folder, filename + ".outcome.json", _bounded_canonical({
                        "schema_version": "anvil.marketing-stream-outcome.v1",
                        "state": "complete_stream_bytes_retained" if complete and durable else "incomplete_unknown_no_replay",
                        "bytes": total, "sha256": digest.hexdigest(), "prefix_fsynced": durable,
                        "failure_type": type(failure).__name__ if failure is not None else None,
                        "evidence_failure_type": type(evidence_error).__name__ if evidence_error is not None else None,
                        "evidence_reserve_seconds": 1, "native_qualified": False, "replay_permitted": False,
                    }, DOCUMENT_CAP))
                except BaseException as exc:
                    evidence_error = exc
                if failure is None and evidence_error is not None:
                    raise RuntimeError("marketing_stream_evidence_unknown_no_replay") from None
        finally:
            if fd is not None:
                os.close(fd)
            os.close(folder)


async def _launch(store, request, records, *, opening=False, actor_owner=None, private=False):
    root, claim, plan = _context_version(store, request, opening=opening)
    server = child = None
    read_fd = write_fd = None
    hardened_read = hardened_write = None
    tasks = []
    start_ticks = None
    context = None
    try:
        if type(private) is not bool or private and (not opening or actor_owner is None):
            raise ValueError('marketing_explicit_private_owned_launcher_required')
        if os.getegid() != 0 or records.request_sha256 != claim["request_sha256"]:
            raise ValueError("marketing_root_bound_launcher_required")
        if actor_owner is not None:
            from anvil.marketing_native_actor_owner import _OpeningActorOwner

            if (not opening or type(actor_owner) is not _OpeningActorOwner
                    or actor_owner._store is not store or actor_owner._request.canonical_bytes != request.canonical_bytes
                    or actor_owner._private is not private):
                raise ValueError('marketing_fixed_original_launch_actor_owner_required')
        retained = _context_status_version(store, root, claim, plan, opening=opening)
        if retained["same_boot_observed"] is not True or retained["deadline_elapsed_observed"] is not False:
            raise ValueError("marketing_current_launcher_context_required")
        context = _parse_record(store._read(root, "component-context.json"))
        from anvil.marketing_native_preflight import _read_pair

        _read_pair(store, root, claim, plan, opening=opening)
        interpreter, interpreter_identity = _runtime_assets(records, plan, context, opening=opening, private=private)
        private_pin = None
        if private:
            private_pin = _parse_record(dict(records.records)['runtime'])['payload']['launcher']['private_program_sha256']
            if hashlib.sha256(store._read(root, 'private-verifier-program.json')).hexdigest() != private_pin:
                raise ValueError('marketing_private_launcher_actual_program_bytes_changed')
        if actor_owner is not None:
            if private:
                # Private preflight helpers already ran under this same root
                # and its original outside watchdog. Never restart its timer.
                if actor_owner._watchdog is None:
                    raise ValueError('marketing_private_preflight_original_watchdog_required')
                actor_owner._watchdog.require_live()
            else:
                await actor_owner.start_watchdog(interpreter)
        _write_at(root, "framework-launch-intent.json", _bounded_canonical({
            "schema_version": "anvil.marketing-framework-launch-intent.v1",
            "job_id": claim["job_id"], "request_sha256": claim["request_sha256"],
            "plan_sha256": claim["plan_sha256"], "context_sha256": retained["context_sha256"],
            "deadline_monotonic": context["deadline_monotonic"], "scope": claim["scope"],
        }, DOCUMENT_CAP))
        server = await _listen(store, root, claim, context, request, opening=opening, actor_owner=actor_owner)
        read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
        if private:
            hardened_read, hardened_write = os.pipe2(os.O_CLOEXEC)
        attempt = str(store.parent / claim["trial_name"])
        environment = {**(PRIVATE_ENVIRONMENT_TEMPLATE if private else ENVIRONMENT_TEMPLATE),
                       "HOME": attempt, "ANVIL_MARKETING_ATTEMPT_ROOT": attempt,
                       "ANVIL_MARKETING_CONTEXT_SHA256": retained["context_sha256"]}
        # No inherited provider keys, Python path, preload hook, CLI or shell.
        # Spawn/import hard bounds are NOT proven by this async wait.
        bootstrap = PRIVATE_OPENING_BOOTSTRAP if private else OPENING_BOOTSTRAP if opening else BOOTSTRAP
        child = await asyncio.wait_for(asyncio.create_subprocess_exec(
            str(interpreter), "-I", "-B", "-c", bootstrap,
            str(read_fd), str(context["deadline_monotonic"]), attempt + "/trial.json",
            *([private_pin, str(hardened_write)] if private else []),
            cwd=attempt, env=environment, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=True, close_fds=True,
            pass_fds=((read_fd, hardened_write) if private else (read_fd,)), umask=0o077,
        ), timeout=_remaining(context))
        os.close(read_fd)
        read_fd = None
        start_ticks = _process_identity(child.pid)
        actual = os.stat("/proc/" + str(child.pid) + "/exe")
        if ((actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns, actual.st_ctime_ns) != interpreter_identity
                or os.readlink("/proc/" + str(child.pid) + "/exe") != str(interpreter)):
            raise ValueError("marketing_actual_child_interpreter_changed")
        binding = {
            "schema_version": "anvil.marketing-host-control-binding.v2" if opening
                              else "anvil.marketing-host-control-binding.v1",
            "job_id": claim["job_id"], "request_sha256": claim["request_sha256"],
            "plan_sha256": claim["plan_sha256"], "scope": claim["scope"],
            "context_sha256": retained["context_sha256"], "framework_pid": child.pid,
            "framework_start_ticks": start_ticks, "boot_id": context["boot_id"],
        }
        if opening:
            binding['operator_program_sha256'] = plan['operator_program_sha256']
        _write_at(root, "host-control-binding.json", _bounded_canonical(binding, DOCUMENT_CAP))
        if actor_owner is not None:
            actor_owner.bind_framework(child.pid, start_ticks)
        if private:
            from anvil.marketing_native_actor_hardening import harden_private_control
            from anvil.marketing_native_enrollment_client import _prepare_original_attester
            from anvil.marketing_native_watchdog import _pipe_bytes

            os.close(hardened_write)
            hardened_write = None
            preG_deadline = context['deadline_monotonic'] - plan['bounds']['cleanup_seconds'] - plan['bounds']['verifier_seconds']
            if await _pipe_bytes(hardened_read, cap=1, deadline=preG_deadline) != b'R':
                raise RuntimeError('marketing_private_sdk_hardening_unknown_no_retry')
            os.close(hardened_read)
            hardened_read = None
            await actor_owner._graph.observe_private_hardening_ready(deadline=preG_deadline)
            harden_private_control()
            await _prepare_original_attester(actor_owner)
        _remaining(context)
        if os.write(write_fd, b"G") != 1:
            raise RuntimeError("marketing_framework_startup_unknown")
        os.close(write_fd)
        write_fd = None
        tasks = [asyncio.create_task(child.wait()),
                 asyncio.create_task(_pump(child.stdout, root, "framework-stdout.log", plan["bounds"]["stdout_bytes"], context)),
                 asyncio.create_task(_pump(child.stderr, root, "framework-stderr.log", plan["bounds"]["stderr_bytes"], context))]
        if actor_owner is not None:
            results = await actor_owner.watch_framework(asyncio.gather(*tasks))
        else:
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=_remaining(context))
        _remaining(context)
        receipt = {"schema_version": "anvil.marketing-framework-exit-observed.v1",
                   "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
                   "pid": child.pid, "start_ticks": start_ticks, "returncode": results[0],
                   "stdout": results[1], "stderr": results[2], "observed_monotonic": monotonic(),
                   "whole_actor_stopped": False, "native_qualified": False, "replay_permitted": False}
        _write_at(root, "framework-exit-observed.json", _bounded_canonical(receipt, DOCUMENT_CAP))
        if private:
            from anvil.marketing_native_enrollment_client import request_original_final_capture

            if type(results[0]) is not int or results[0] != 0:
                raise RuntimeError('marketing_original_private_sdk_nonzero_no_final_capture')
            await request_original_final_capture(actor_owner)
        return receipt
    finally:
        try:
            # Pipe EOF prevents a child still behind the startup fence from
            # entering the module. Ambiguous spawn never authorizes relaunch.
            for fd in (read_fd, write_fd, hardened_read, hardened_write):
                if fd is not None:
                    os.close(fd)
            if server is not None:
                server.close()
            if child is not None and child.returncode is None:
                try:
                    if start_ticks is not None and _process_identity(child.pid) == start_ticks:
                        os.killpg(child.pid, signal.SIGKILL)
                except (OSError, ValueError):
                    pass  # Still await owned child; never assert group cleanup.
            for task in tasks:
                if not task.done():
                    task.cancel()
            # Joins consume existing remaining budget. Timeout/cancellation
            # propagates; it cannot turn failed cleanup into successful return.
            if context is not None:
                joins = [asyncio.gather(*tasks, return_exceptions=True)] if tasks else []
                if child is not None and child.returncode is None:
                    joins.append(child.wait())
                if server is not None:
                    joins.append(server.wait_closed())
                if joins:
                    try:
                        await asyncio.wait_for(asyncio.gather(*joins),
                                               timeout=max(0, context["deadline_monotonic"] - monotonic()))
                    except TimeoutError:
                        raise RuntimeError("marketing_launcher_cleanup_unknown_no_replay") from None
        finally:
            os.close(root)


async def launch_fixed_framework(request):
    marketing_native_gate()
    records = resolve_marketing_records(request)
    with MarketingAttemptStore() as store:
        return await _launch(store, request, records)


async def launch_opening_framework(request):
    marketing_native_gate()
    records = resolve_marketing_opening_records(request)
    with MarketingAttemptStore() as store:
        return await _launch(store, request, records, opening=True)


async def launch_opening_actor_framework(connections, job, prepared_raw, request):
    """Original trusted worker invocation only; no socket-supplied business input."""
    marketing_native_gate()
    from anvil.marketing_native_actor_owner import _OpeningActorOwner

    records = resolve_marketing_opening_records(request)
    with MarketingAttemptStore() as store:
        owner = _OpeningActorOwner(store, connections, job, prepared_raw, request, records)
        try:
            try:
                result = await _launch(store, request, records, opening=True, actor_owner=owner)
            except BaseException as original:
                try:
                    await owner.shutdown()
                except BaseException as cleanup:
                    raise original from cleanup
                raise
            else:
                await owner.shutdown()
                return result
        finally:
            owner.close()  # Closing custody is not stop or capture proof.


async def launch_private_actor_framework(job, prepared_raw, request):
    marketing_native_gate()
    from anvil.marketing_native_actor_owner import _OpeningActorOwner
    from anvil.marketing_native_private_records import resolve_private_marketing_records

    records = resolve_private_marketing_records(request)
    with MarketingAttemptStore() as store:
        owner = _OpeningActorOwner(store, None, job, prepared_raw, request, records, private=True)
        try:
            try:
                from anvil.marketing_native_preflight import _produce

                context = _parse_record(store._read(owner._root, 'component-context.json'))
                interpreter, _ = _runtime_assets(records, owner._plan, context, opening=True, private=True)
                await owner.start_watchdog(interpreter)
                # The scope exists before helper enrollment. This is the only
                # paired preflight attempt and consumes the original deadline.
                await _produce(store, request, records, opening=True, private=True)
                result = await _launch(store, request, records, opening=True, actor_owner=owner, private=True)
            except BaseException as original:
                try:
                    await owner.shutdown()
                except BaseException as cleanup:
                    raise original from cleanup
                raise
            else:
                await owner.shutdown()
                return result
        finally:
            owner.close()
