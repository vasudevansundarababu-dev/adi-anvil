"""Fixed independent-receiver helpers, enrolled before exec in original scope.

SOURCE ONLY. No caller argv/env/binary/factory, source qualification, native
admission or retry authority. The privileged receiver has no signer key heap;
the isolated exec child inherits only its startup pipe and bounded stdio.
"""

import asyncio
import ctypes
import hashlib
import math
import os
import select
import signal
import sys
from pathlib import Path
from time import monotonic


def _operation(owner, operation_id):
    from anvil.marketing_native_physical import OPERATIONS, _assets
    from anvil.marketing_native_preflight import ENVIRONMENT, _resolver

    if type(operation_id) is not str:
        raise ValueError("marketing_fixed_original_helper_operation_required")
    parts = operation_id.split(":")
    if len(parts) == 2 and parts[0] == "preflight" and parts[1] in {"environment", "tests"}:
        role, kind = parts[1], "preflight"
        binary, _ = _resolver(owner._records, owner._context)
        tail = ["config", "--format", "json", "--no-interpolate", "--no-env-resolution"]
        output = "marketing-preflight-stdout-" + role + ".json"
        error = "marketing-preflight-stderr-" + role + ".log"
    elif (len(parts) == 3 and parts[0] == "physical" and parts[1] in OPERATIONS
          and parts[2] in {"environment", "tests"}):
        kind, operation, role = parts
        binary, _, _ = _assets(owner._records, owner._context)
        tail = OPERATIONS[operation]
        output = "marketing-" + operation + "-" + role + "-stdout.txt"
        error = "marketing-" + operation + "-" + role + "-stderr.txt"
    else:
        raise ValueError("marketing_fixed_original_helper_operation_required")
    attempt = Path(owner._context["attempt_root"])
    directory = attempt / "task" / role
    session = owner._claim["trial_name"] + ("__env" if role == "environment" else "__verifier__trial")
    argv = [str(binary), "--env-file", "/dev/null", "--project-directory", str(directory),
            "--project-name", session, "--file", str(directory / "docker-compose.yaml"), *tail]
    return argv, directory, dict(ENVIRONMENT), output, error


def _deadline(owner, value):
    from anvil.marketing_native_kernel_scope import _remaining

    original = owner._context["deadline_monotonic"]
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value > original or value > owner._phase_deadline):
        raise ValueError("marketing_helper_original_phase_deadline_required")
    _remaining(value)
    return value


def _scope(owner, *, child=False):
    """Reopen actual original scope/subgroup; never trust control's object FDs."""
    from anvil.marketing_native_kernel_scope import _directory, _fd_mount, _open_scope, _read
    from anvil.marketing_native_records import _parse_record
    from anvil.marketing_native_verifier_renderer import private_context_assets
    from anvil.marketing_native_world_binding import _read_source_file

    deadline, context = owner._phase_deadline, owner._context
    binding_raw = owner._store._read(owner._root, "actor-scope-binding.json")
    binding = _parse_record(binding_raw)
    children = _parse_record(owner._store._read(owner._root, "actor-scope-children.json"))
    profile = _parse_record(dict(owner._records.records)["host"])["payload"]["actor_scope"]
    assets, _ = private_context_assets(owner._records)
    resources = assets["resources"]
    if (binding.get("schema_version") != "anvil.marketing-original-kernel-scope.v1"
            or any(binding[k] != owner._claim[k] for k in ("request_sha256", "plan_sha256"))
            or binding["operation_nonce"] != context["operation_nonce"]
            or binding["boot_id"] != context["boot_id"]
            or binding["original_deadline_monotonic"] != context["deadline_monotonic"]
            or profile.get("schema_version") != "anvil.marketing-actor-scope-profile.v3"
            or profile.get("profile_id") != "opening-framework-graph-host-helpers-cgroup2-v1"
            or profile.get("scope_root") != "/sys/fs/cgroup/anvil-marketing"
            or children.get("schema_version") != "anvil.marketing-original-actor-scope-children.v2"
            or children.get("binding_sha256") != hashlib.sha256(binding_raw).hexdigest()
            or children.get("native_qualified") is not False
            or set(children.get("children", {})) != {"framework", "graph", "host_helpers"}):
        raise ValueError("marketing_helper_disjoint_original_private_scope_required")
    _read_source_file(Path(__file__).name, profile["helper_process_sha256"])
    _read_source_file("marketing_native_actor_hardening.py", profile["child_hardening_sha256"])
    proc = root = node = None
    try:
        proc = os.open("/proc", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        if _read(proc, "sys/kernel/random/boot_id", 64, deadline).strip() != binding["boot_id"]:
            raise ValueError("marketing_helper_original_boot_changed")
        path = "/anvil-marketing/" + context["operation_nonce"][:20]
        own = _read(proc, "self/cgroup", 4096, deadline).strip()
        if child:
            if own != "0::" + path + "/host_helpers":
                raise ValueError("marketing_helper_child_not_in_original_subgroup")
        elif not own.startswith("0::/") or "\n" in own or own[3:] == path or own[3:].startswith(path + "/"):
            raise ValueError("marketing_helper_receiver_must_stay_outside_scope")
        root = _open_scope(context["operation_nonce"])
        info = os.fstat(root)
        if ((info.st_dev, info.st_ino) != (binding["cgroup_device"], binding["cgroup_inode"])
                or _fd_mount(proc, root, deadline)[0] != binding["cgroup_mount_id"]):
            raise ValueError("marketing_helper_original_scope_replaced")
        if _read(root, "cgroup.freeze", 32, deadline).strip() != "0":
            raise ValueError("marketing_helper_original_scope_already_fenced")
        for key, expected in (("cpu.max", str(resources["cpus"] * 100000) + " 100000"),
                              ("memory.max", str(resources["memory_mb"] * 1048576)),
                              ("pids.max", str(resources["pids_limit"])),
                              ("cgroup.max.depth", "1"), ("cgroup.max.descendants", "3")):
            if _read(root, key, 128, deadline).strip() != expected:
                raise ValueError("marketing_helper_original_aggregate_limits_changed")
        for key in ("cpus", "memory_mb", "pids_limit"):
            if type(profile[key]) is not int or profile[key] <= 0 or profile[key] != resources[key]:
                raise ValueError("marketing_helper_qualified_resource_profile_changed")
        node = _directory(root, "host_helpers")
        actual, expected = os.fstat(node), children["children"]["host_helpers"]
        if ((actual.st_dev, actual.st_ino) != (expected["device"], expected["inode"])
                or _fd_mount(proc, node, deadline)[0] != expected["mount_id"]):
            raise ValueError("marketing_helper_original_subgroup_replaced")
        result = (proc, root, node, binding_raw)
        proc = root = node = None
        return result
    finally:
        for fd in (node, root, proc):
            if fd is not None:
                os.close(fd)


async def run_original_helper(owner, operation_id, *, absolute_deadline):
    from anvil.marketing_native_actor_scope import _pid_identity, _write_control
    from anvil.marketing_native_attempt import _write_at
    from anvil.marketing_native_attester_receiver import _ReceiverOperation
    from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical, _digest, marketing_native_gate
    from anvil.marketing_native_kernel_scope import _read, _remaining
    from anvil.marketing_native_launcher import _process_identity, _pump, _runtime_assets

    marketing_native_gate()
    if type(owner) is not _ReceiverOperation:
        raise ValueError("marketing_exact_independent_receiver_helper_owner_required")
    deadline = _deadline(owner, absolute_deadline)
    argv, directory, environment, output_name, error_name = _operation(owner, operation_id)
    interpreter, _ = _runtime_assets(owner._records, owner._plan, owner._context, opening=True, private=True)
    proc, scope, node, binding_raw = _scope(owner)
    trial = gate_r = gate_w = pidfd = None
    child, tasks, primary_error, reply = None, [], None, None
    tag = hashlib.sha256(operation_id.encode("ascii")).hexdigest()
    stem = "helper-exec-" + tag
    context = {**owner._context, "deadline_monotonic": deadline}
    try:
        parent_ticks = _pid_identity(proc, os.getpid(), deadline)[1]
        intent = {"schema_version": "anvil.marketing-original-helper-intent.v1", "operation_id": operation_id,
                  "request": owner._request.canonical_bytes.decode("utf-8"),
                  "parent_pid": os.getpid(), "parent_start_ticks": parent_ticks,
                  "absolute_deadline": deadline, "original_deadline_monotonic": owner._context["deadline_monotonic"],
                  "binding_sha256": hashlib.sha256(binding_raw).hexdigest(), "argv_sha256": _digest(argv),
                  "replay_permitted": False, "native_qualified": False}
        raw = _bounded_canonical(intent, DOCUMENT_CAP)
        # Exclusive first intent, before any spawn. Every later failure is final.
        _write_at(owner._root, stem + "-intent.json", raw, mode=0o400)
        trial = owner._store._walk(owner._root, ["trials", owner._claim["trial_name"]])
        gate_r, gate_w = os.pipe2(os.O_CLOEXEC)
        command = [str(interpreter), "-I", "-B", "-m", "anvil.marketing_native_helper_process",
                   str(gate_r), owner._context["attempt_root"], operation_id, hashlib.sha256(raw).hexdigest(), repr(deadline)]
        child = await asyncio.wait_for(asyncio.create_subprocess_exec(
            *command, cwd=directory, env={**environment, "ANVIL_ROOT": "/proc/self/fd"},
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            pass_fds=(gate_r,), close_fds=True, start_new_session=True, umask=0o077,
        ), timeout=max(0, deadline - monotonic()))
        os.close(gate_r)
        gate_r = None
        ticks = _process_identity(child.pid)
        pidfd = os.pidfd_open(child.pid, 0)
        if _pid_identity(proc, child.pid, deadline) != (os.getpid(), ticks):
            raise ValueError("marketing_original_direct_helper_child_required")
        _write_control(node, "cgroup.procs", str(child.pid).encode(), deadline)
        expected = "0::/anvil-marketing/" + owner._context["operation_nonce"][:20] + "/host_helpers"
        if (select.select([pidfd], [], [], 0)[0]
                or _pid_identity(proc, child.pid, deadline) != (os.getpid(), ticks)
                or _read(proc, str(child.pid) + "/cgroup", 4096, deadline).strip() != expected):
            raise RuntimeError("marketing_helper_enrollment_unknown_no_exec_release")
        enrollment = {"schema_version": "anvil.marketing-original-helper-enrollment.v1",
                      "operation_id": operation_id, "pid": child.pid, "start_ticks": ticks,
                      "intent_sha256": hashlib.sha256(raw).hexdigest(),
                      "binding_sha256": hashlib.sha256(binding_raw).hexdigest(),
                      "absolute_deadline": deadline, "native_qualified": False}
        _write_at(owner._root, stem + "-enrollment.json", _bounded_canonical(enrollment, 4096), mode=0o400)
        # Parent keeps all writable kernel FDs; child inherited none of them.
        if os.write(gate_w, b"G") != 1:
            raise RuntimeError("marketing_helper_startup_release_unknown")
        os.close(gate_w)
        gate_w = None
        tasks = [asyncio.create_task(child.wait()),
                 asyncio.create_task(_pump(child.stdout, trial, output_name, owner._plan["bounds"]["stdout_bytes"], context)),
                 asyncio.create_task(_pump(child.stderr, trial, error_name, owner._plan["bounds"]["stderr_bytes"], context))]
        code, stdout, stderr = await asyncio.wait_for(asyncio.gather(*tasks), timeout=max(0, deadline - monotonic()))
        _remaining(deadline)
        if not select.select([pidfd], [], [], 0)[0]:
            raise RuntimeError("marketing_helper_owned_exit_not_observed")
        result = {"schema_version": "anvil.marketing-original-helper-result.v1", "operation_id": operation_id,
                  "argv_sha256": _digest(argv), "pid": child.pid, "start_ticks": ticks, "returncode": code,
                  "stdout": stdout, "stderr": stderr, "stdout_sha256": stdout["sha256"], "stderr_sha256": stderr["sha256"],
                  "intent_sha256": hashlib.sha256(raw).hexdigest(),
                  "enrollment_sha256": hashlib.sha256(_bounded_canonical(enrollment, 4096)).hexdigest(),
                  "whole_operation_stopped": False, "native_qualified": False}
        receipt = _bounded_canonical(result, DOCUMENT_CAP)
        _write_at(owner._root, stem + "-result.json", receipt, mode=0o400)
        if code != 0:
            raise RuntimeError("marketing_original_helper_failed_no_retry")
        reply = {"argv_sha256": result["argv_sha256"], "pid": child.pid, "start_ticks": ticks,
                 "returncode": code, "stdout": stdout, "stderr": stderr,
                 "stdout_sha256": stdout["sha256"], "stderr_sha256": stderr["sha256"],
                 "helper_receipt_sha256": hashlib.sha256(receipt).hexdigest()}
        return reply
    except BaseException as error:
        primary_error = error
        raise
    finally:
        # Work timeout is not a new cleanup clock. Use only the remainder of
        # the unchanged ORIGINAL aggregate cutoff, including its reserved tail.
        cleanup_end = owner._context["deadline_monotonic"]
        cleanup_failures, cleanup_cause = [], None
        exit_observed, exit_code, termination = False, None, None

        def failed(stage, error):
            nonlocal cleanup_cause
            cleanup_failures.append({"stage": stage, "failure_type": type(error).__name__})
            if cleanup_cause is None:
                cleanup_cause = error

        # Close the pre-exec release capability FIRST, before any acquisition
        # failure recovery. EOF never authorizes the child's business exec.
        for fd in (gate_w, gate_r):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError as error:
                    failed("startup_fence_close", error)
        if child is not None and child.returncode is None:
            signalled = False
            if pidfd is not None:
                try:
                    signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    signalled, termination = True, "owned_pidfd_SIGKILL_requested"
                except OSError as error:
                    # A pidfd acquisition/signal failure is retained even if
                    # the exact owned child handle subsequently allows recovery.
                    failed("owned_pidfd_signal", error)
            if not signalled and child.returncode is None:
                try:
                    # Only this returned, still-owned, unreaped subprocess
                    # handle. Never signal an adopted PID/name/process group.
                    child.kill()
                    termination = "original_owned_child_handle_kill_requested"
                except ProcessLookupError:
                    termination = "owned_child_handle_reported_exit_wait_required"
                except BaseException as error:
                    failed("original_owned_child_handle_kill", error)
        for task in tasks:
            if not task.done():
                task.cancel()
        try:
            if child is not None:
                left = cleanup_end - monotonic()
                if not 0 < left <= 600:
                    raise TimeoutError("marketing_helper_original_cleanup_cutoff_exhausted")
                # Process.wait is the original transport's actual owned exit /
                # child-watcher reap observation, including when ticks/pidfd
                # acquisition failed. Never infer this from startup EOF alone.
                exit_code = await asyncio.wait_for(child.wait(), timeout=left)
                if type(exit_code) is not int or child.returncode != exit_code:
                    raise RuntimeError("marketing_helper_original_child_exit_unknown")
                exit_observed = True
            else:
                failed("spawn_ownership", RuntimeError("marketing_helper_spawn_did_not_return_owned_handle"))
            if tasks:
                left = cleanup_end - monotonic()
                if not 0 < left <= 600:
                    raise TimeoutError("marketing_helper_original_stream_cleanup_cutoff_exhausted")
                retained = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=left)
                for item in retained:
                    if isinstance(item, BaseException) and not isinstance(item, asyncio.CancelledError):
                        failed("retained_child_or_stream_task", item)
        except BaseException as error:
            failed("owned_child_reap_or_stream_cleanup", error)
        finally:
            for fd in (pidfd, trial, node, scope, proc):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError as error:
                        failed("owned_descriptor_close", error)
        cleanup = {"schema_version": "anvil.marketing-original-helper-cleanup.v1", "operation_id": operation_id,
                   "known_returned_child": child is not None, "pid": child.pid if child is not None else None,
                   "termination_request": termination, "owned_exit_and_reap_observed": exit_observed,
                   "returncode": exit_code, "original_deadline_monotonic": cleanup_end,
                   "work_deadline_monotonic": deadline,
                   "state": "owned_child_exit_observed_NOT_subtree_empty" if exit_observed and not cleanup_failures
                   else "cleanup_unknown_blocked_no_retry",
                   "primary_failure_type": type(primary_error).__name__ if primary_error is not None else None,
                   "cleanup_failures": cleanup_failures, "whole_operation_stopped": False, "native_qualified": False}
        try:
            cleanup_raw = _bounded_canonical(cleanup, DOCUMENT_CAP)
            _write_at(owner._root, stem + "-cleanup.json", cleanup_raw, mode=0o400)
            if reply is not None:
                reply["helper_cleanup_receipt_sha256"] = hashlib.sha256(cleanup_raw).hexdigest()
        except BaseException as error:
            failed("cleanup_receipt_retention", error)
        if not exit_observed or cleanup_failures:
            if primary_error is not None:
                primary_error.add_note("marketing_helper_cleanup_unknown_blocked: " + ",".join(
                    item["stage"] + ":" + item["failure_type"] for item in cleanup_failures))
                # Preserve the FIRST failure with its traceback and the actual
                # cleanup cause. A primary failure never becomes a success.
                if primary_error.__cause__ is None and cleanup_cause is not None:
                    primary_error.__cause__ = cleanup_cause
            else:
                raise RuntimeError("marketing_helper_owned_cleanup_unknown_blocked") from cleanup_cause
        # Surviving descendants remain within the original aggregate group.
        # Receiver/watchdog whole-root freeze/kill remains mandatory even exit0.


def _child():
    # Only fixed stdlib startup/fence work before enrollment release. No backend
    # imports, original request reads, resolver work or privileged business exec.
    if len(sys.argv) != 6 or not sys.argv[1].isascii() or not sys.argv[1].isdecimal():
        raise ValueError("marketing_fixed_helper_child_arguments_required")
    gate, attempt, operation_id, pin = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
    deadline = float(sys.argv[5])
    if (not 3 <= gate <= 1048576 or not math.isfinite(deadline)
            or not 0 < deadline - monotonic() <= 600):
        raise ValueError("marketing_helper_owned_startup_descriptor_and_cutoff_required")
    parent_pid = os.getppid()
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or parent_pid <= 1 or os.getppid() != parent_pid:
        raise RuntimeError("marketing_helper_original_parent_lost_before_fence")
    if not select.select([gate], [], [], max(0, deadline - monotonic()))[0] or os.read(gate, 2) != b"G":
        raise RuntimeError("marketing_helper_startup_fence_not_released")
    os.close(gate)

    from types import SimpleNamespace

    from anvil.marketing_native_actor_hardening import harden_graph
    from anvil.marketing_native_actor_scope import _pid_identity
    from anvil.marketing_native_attempt import MarketingAttemptStore
    from anvil.marketing_native_boundary import marketing_native_gate, prepare_marketing_request
    from anvil.marketing_native_kernel_scope import _read, _remaining
    from anvil.marketing_native_mounts import _opening_context
    from anvil.marketing_native_records import _parse_record
    from anvil.marketing_native_private_records import resolve_private_marketing_records

    marketing_native_gate()
    tag = hashlib.sha256(operation_id.encode("ascii")).hexdigest()
    stem = "helper-exec-" + tag
    with MarketingAttemptStore() as store:
        if str(Path(attempt)) != attempt or Path(attempt).parent != store.parent:
            raise ValueError("marketing_original_helper_attempt_required")
        root = store._walk(store.fd, [Path(attempt).name])
        try:
            raw = store._read(root, stem + "-intent.json")
            if hashlib.sha256(raw).hexdigest() != pin:
                raise ValueError("marketing_original_helper_intent_pin_changed")
            intent = _parse_record(raw)
            if (set(intent) != {"schema_version", "operation_id", "request", "parent_pid", "parent_start_ticks",
                                "absolute_deadline", "original_deadline_monotonic", "binding_sha256", "argv_sha256",
                                "replay_permitted", "native_qualified"}
                    or intent["schema_version"] != "anvil.marketing-original-helper-intent.v1"
                    or intent["absolute_deadline"] != deadline or intent["parent_pid"] != parent_pid):
                raise ValueError("marketing_helper_exact_original_intent_required")
            request = prepare_marketing_request(intent["request"].encode("utf-8"))
            context_root, claim, plan = _opening_context(store, request)
            os.close(context_root)
            context = _parse_record(store._read(root, "component-context.json"))
            if context["attempt_root"] != attempt or claim["trial_name"] != Path(attempt).name:
                raise ValueError("marketing_helper_original_request_attempt_changed")
            owner = SimpleNamespace(_store=store, _root=root, _request=request,
                                    _records=resolve_private_marketing_records(request), _claim=claim,
                                    _plan=plan, _context=context, _phase_deadline=intent["absolute_deadline"])
            deadline = _deadline(owner, intent["absolute_deadline"])
            if (intent["operation_id"] != operation_id or intent["original_deadline_monotonic"] != context["deadline_monotonic"]
                    or intent["replay_permitted"] is not False or intent["native_qualified"] is not False
                    or os.getppid() != intent["parent_pid"]):
                raise ValueError("marketing_original_helper_parent_or_intent_changed")
            proc, scope, node, binding = _scope(owner, child=True)
            try:
                enrollment = _parse_record(store._read(root, stem + "-enrollment.json"))
                if (set(enrollment) != {"schema_version", "operation_id", "pid", "start_ticks", "intent_sha256",
                                       "binding_sha256", "absolute_deadline", "native_qualified"}
                        or enrollment["schema_version"] != "anvil.marketing-original-helper-enrollment.v1"
                        or enrollment["operation_id"] != operation_id or enrollment["native_qualified"] is not False
                        or enrollment["pid"] != os.getpid()
                        or _pid_identity(proc, os.getpid(), deadline) != (intent["parent_pid"], enrollment["start_ticks"])
                        or _pid_identity(proc, intent["parent_pid"], deadline)[1] != intent["parent_start_ticks"]
                        or enrollment["intent_sha256"] != pin or enrollment["binding_sha256"] != intent["binding_sha256"]
                        or hashlib.sha256(binding).hexdigest() != intent["binding_sha256"]
                        or enrollment["absolute_deadline"] != deadline or os.getppid() != intent["parent_pid"]):
                    raise ValueError("marketing_original_helper_child_identity_changed")
                argv, directory, environment, _, _ = _operation(owner, operation_id)
                from anvil.marketing_native_boundary import _digest

                if _digest(argv) != intent["argv_sha256"]:
                    raise ValueError("marketing_original_helper_fixed_argv_changed")
                _remaining(deadline)
            finally:
                for fd in (node, scope, proc):
                    os.close(fd)
        finally:
            os.close(root)
    # Close ALL extra descriptors, including store and any cgroup path handles,
    # before installing the readonly view. No writable cgroup FD survives exec.
    import resource

    limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    if limit == resource.RLIM_INFINITY or not 3 <= limit <= 1048576:
        raise ValueError("marketing_helper_fixed_descriptor_bound_required")
    os.closerange(3, int(limit))
    harden_graph()
    proc = os.open("/proc", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        expected = "0::/anvil-marketing/" + context["operation_nonce"][:20] + "/host_helpers"
        if (_read(proc, "self/cgroup", 4096, deadline).strip() != expected
                or _read(proc, "sys/kernel/random/boot_id", 64, deadline).strip() != context["boot_id"]):
            raise ValueError("marketing_hardened_helper_original_membership_changed")
        status = {}
        for line in _read(proc, "self/status", 16384, deadline).splitlines():
            key, separator, value = line.partition(":")
            if separator:
                status[key] = value.strip()
        if (status.get("NoNewPrivs") != "1" or status.get("Seccomp") != "2"
                or any(not status.get(key) or set(status[key]) != {"0"}
                       for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"))):
            raise ValueError("marketing_helper_actual_privilege_drop_required")
        rows = [line.split() for line in _read(proc, "self/mountinfo", 65536, deadline).splitlines()]
        mounts = [row for row in rows if len(row) > 6 and row[4] == "/sys/fs/cgroup"]
        if (not mounts or any("-" not in row or row[row.index("-") + 1] != "cgroup2"
                              or "ro" not in row[5].split(",") for row in mounts)):
            raise ValueError("marketing_helper_readonly_cgroup_view_required")
    finally:
        os.close(proc)
    _remaining(deadline)
    os.chdir(directory)
    os.execve(argv[0], argv, environment)


if __name__ == "__main__":
    try:
        _child()
    except BaseException:
        # No original request, private input, context token or traceback in logs.
        os._exit(43)
