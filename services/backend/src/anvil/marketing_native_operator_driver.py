"""Once-only outer bootstrap custody. No self-issued admission or SDK retry.

The public operation remains behind native admission. The inner state machine
also serves controlled pipe/SQL conformance tests, explicitly not qualification.
Preparation and asset binding are trusted operator adapters, never caller code
loaded from a request, environment, import string or public HTTP endpoint.
"""

import hashlib
import math
import os
import re
import selectors
from pathlib import Path
from time import monotonic
from uuid import UUID

from anvil.marketing_native_attempt import _owned, _write_at
from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    _bounded_canonical,
    marketing_native_gate,
    prepare_marketing_request,
    validate_prepared_graph_binding,
)
from anvil.marketing_native_job_packet import decode_original_job, encode_original_job
from anvil.marketing_native_operator_observation import bootstrap_frame
from anvil.marketing_native_records import _parse_record

ROOT = Path("/var/lib/anvil-qa-v1/runtime-functional/marketing-operator-driver")


def remaining(deadline):
    value = deadline - monotonic()
    if value <= 0:
        raise TimeoutError("marketing_original_operator_driver_cutoff")
    return value


class DriverJournal:
    def __init__(self):
        if os.geteuid() != 0 or os.uname().nodename != "anvil-qa-v1":
            raise RuntimeError("marketing_original_QA_operator_required")
        self._initialize(ROOT, 0)

    @classmethod
    def for_owned_local_test(cls, folder):
        instance = object.__new__(cls)
        instance._initialize(Path(folder), os.geteuid())
        return instance

    def _initialize(self, root, owner):
        if not root.is_absolute() or root.resolve() != root:
            raise ValueError("marketing_original_canonical_driver_root_required")
        self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            _owned(os.fstat(self.fd), owner, directory=True, private=True)
        except BaseException:
            os.close(self.fd)
            raise

    def close(self):
        os.close(self.fd)

    def begin(self, job, deadline):
        identifier = str(UUID(str(job["id"])))
        raw = _bounded_canonical(encode_original_job(job), DOCUMENT_CAP)
        value = {
            "schema_version": "anvil.marketing-operator-intent.v1",
            "job_id": identifier,
            "job_sha256": hashlib.sha256(raw).hexdigest(),
            "original_deadline": deadline,
            "native_qualified": False,
        }
        # Persist BEFORE any stream write or prepare. Never delete/reuse markers.
        _write_at(self.fd, identifier + ".intent.json", _bounded_canonical(value, 8192))
        return identifier

    def record(self, identifier, stage, value):
        if stage not in {
            "bootstrap_sent",
            "prestarted",
            "prepare_intent",
            "prepared",
            "binding_intent",
            "bound",
            "supply_intent",
            "exit_observed",
            "outcome_unknown",
            "cleanup_intent",
            "cleanup_observed",
            "cleanup_unknown",
        }:
            raise ValueError("marketing_fixed_operator_stage_required")
        raw = _bounded_canonical(value, DOCUMENT_CAP)
        _write_at(
            self.fd,
            identifier + "." + stage + ".json",
            _bounded_canonical(
                {
                    "stage": stage,
                    "content_sha256": hashlib.sha256(raw).hexdigest(),
                    "native_qualified": False,
                },
                8192,
            ),
        )


class BootstrapChannel:
    """The caller retains original container/attach ownership; no name lookup."""

    def __init__(self, incoming, outgoing):
        self.incoming, self.outgoing = incoming, outgoing
        os.set_blocking(incoming, False)
        os.set_blocking(outgoing, False)

    def send(self, raw, deadline):
        view = memoryview(raw)
        with selectors.DefaultSelector() as selected:
            selected.register(self.outgoing, selectors.EVENT_WRITE)
            while view:
                if not selected.select(remaining(deadline)):
                    raise TimeoutError("marketing_original_operator_write_cutoff")
                try:
                    count = os.write(self.outgoing, view[:32768])
                except BlockingIOError:
                    continue
                if count <= 0:
                    raise RuntimeError("marketing_original_operator_write_unknown_no_retry")
                view = view[count:]
        remaining(deadline)

    def _read(self, count, deadline):
        raw = bytearray()
        with selectors.DefaultSelector() as selected:
            selected.register(self.incoming, selectors.EVENT_READ)
            while len(raw) < count:
                if not selected.select(remaining(deadline)):
                    raise TimeoutError("marketing_original_operator_read_cutoff")
                try:
                    chunk = os.read(self.incoming, min(32768, count - len(raw)))
                except BlockingIOError:
                    continue
                if not chunk:
                    raise RuntimeError("marketing_original_operator_reply_unknown_no_retry")
                raw.extend(chunk)
        remaining(deadline)
        return bytes(raw)

    def receive(self, deadline):
        header = self._read(9, deadline)
        if not re.fullmatch(b"[0-9a-f]{8}\n", header):
            raise ValueError("marketing_original_operator_reply_frame_required")
        count = int(header[:8], 16)
        if not 0 < count <= 8192:
            raise ValueError("marketing_operator_public_reply_capacity")
        return _parse_record(self._read(count, deadline))


def _prestarted(value, deadline, work_deadline):
    if (
        type(value) is not dict
        or set(value) != {"schema_version", "processes", "native_qualified"}
        or value["schema_version"] != "anvil.marketing-operator-prestarted.v1"
        or value["native_qualified"] is not False
        or set(value["processes"]) != {"control", "receiver"}
    ):
        raise ValueError("marketing_original_prestarted_processes_required")
    pids = []
    for role, process in value["processes"].items():
        expected = {"pid", "start_ticks", "command_sha256", "input_deadline_monotonic"}
        if role == "control":
            expected.add("environment_sha256")
        if (
            type(process) is not dict
            or set(process) != expected
            or any(
                type(process[key]) is not int or process[key] <= 0 for key in ("pid", "start_ticks")
            )
            or any(
                type(process[key]) is not str or not re.fullmatch("[a-f0-9]{64}", process[key])
                for key in expected
                if key.endswith("_sha256")
            )
            or type(process["input_deadline_monotonic"]) not in (int, float)
            or not work_deadline <= process["input_deadline_monotonic"] <= deadline
        ):
            raise ValueError("marketing_actual_original_prestart_identity_required")
        pids.append(process["pid"])
    if len(set(pids)) != 2:
        raise ValueError("marketing_disjoint_original_processes_required")
    return value["processes"]


def drive_original(
    journal,
    job,
    observation,
    runtime,
    channel,
    *,
    prepare_once,
    bind_original,
    cleanup_owned,
    absolute_deadline,
    cleanup_seconds,
):
    """One original operation; failures retain Unknown and cannot be reacquired.

    Caller already retains admitted container/stream/process custody. A pair-exit
    reply is not capture acceptance, native qualification or benchmark success.
    """
    if (
        type(absolute_deadline) not in (int, float)
        or not math.isfinite(absolute_deadline)
        or not 0 < absolute_deadline - monotonic() <= 600
        or type(cleanup_seconds) is not int
        or not 1 <= cleanup_seconds <= 600
    ):
        raise ValueError("marketing_original_bounded_driver_invocation_required")
    work = absolute_deadline - cleanup_seconds
    remaining(work)
    profile = _parse_record(observation.profile)
    if (
        profile["original_deadline_monotonic"] != absolute_deadline
        or profile["original_cleanup_seconds"] != cleanup_seconds
    ):
        raise ValueError("marketing_original_observation_deadline_changed")
    first = bootstrap_frame(observation, runtime)
    job_packet = _bounded_canonical(encode_original_job(job), DOCUMENT_CAP)
    original = decode_original_job(_parse_record(job_packet))
    identifier = journal.begin(original, absolute_deadline)
    try:
        channel.send(first, work)
        journal.record(
            identifier, "bootstrap_sent", {"frame_sha256": hashlib.sha256(first).hexdigest()}
        )
        processes = _prestarted(channel.receive(work), absolute_deadline, work)
        journal.record(identifier, "prestarted", processes)
        processes_raw = _bounded_canonical(processes, 8192)
        journal.record(identifier, "prepare_intent", processes)
        remaining(work)
        prepared = prepare_once(
            decode_original_job(_parse_record(job_packet)),
            _parse_record(processes_raw),
            absolute_deadline=work,
        )
        if type(prepared) is not bytes:
            raise ValueError("marketing_original_prepared_bytes_required")
        _parse_record(prepared)
        remaining(work)
        journal.record(identifier, "prepared", {"sha256": hashlib.sha256(prepared).hexdigest()})
        journal.record(identifier, "binding_intent", processes)
        second = bind_original(
            decode_original_job(_parse_record(job_packet)),
            _parse_record(processes_raw),
            prepared,
            absolute_deadline=work,
        )
        if (
            type(second) is not dict
            or set(second) != {"schema_version", "request", "job", "once_prepared"}
            or second["schema_version"] != "anvil.marketing-original-private-control-input.v2"
            or type(second["once_prepared"]) is not str
            or second["once_prepared"].encode() != prepared
            or _bounded_canonical(second["job"], DOCUMENT_CAP) != job_packet
            or type(second["request"]) is not str
        ):
            raise ValueError("marketing_original_bound_input_changed_no_retry")
        request = prepare_marketing_request(second["request"].encode())
        public = _parse_record(request.canonical_bytes)
        if any(
            public[field] != str(original[key])
            for field, key in (
                ("project_id", "project_id"),
                ("actor_id", "actor_id"),
                ("job_id", "id"),
                ("plan_id", "plan_id"),
            )
        ):
            raise ValueError("marketing_original_job_request_scope_changed")
        validate_prepared_graph_binding(request, _parse_record(prepared))
        body = _bounded_canonical(second, DOCUMENT_CAP)
        journal.record(identifier, "bound", second)
        journal.record(identifier, "supply_intent", {"sha256": hashlib.sha256(body).hexdigest()})
        channel.send(f"{len(body):08x}\n".encode() + body, work)
        reply = channel.receive(work)
        if (
            type(reply) is not dict
            or reply.get("native_qualified") is not False
            or reply
            != {
                "schema_version": "anvil.marketing-operator-pair-exit.v1",
                "state": "original_pair_exits_observed",
                "native_qualified": False,
            }
        ):
            raise ValueError("marketing_original_pair_exit_observation_required")
        journal.record(identifier, "exit_observed", reply)
        return reply
    except BaseException:
        journal.record(identifier, "outcome_unknown", {"retry_permitted": False})
        raise
    finally:
        recording_error = cleanup_error = None
        try:
            journal.record(identifier, "cleanup_intent", {"retry_permitted": False})
        except BaseException as error:
            recording_error = error
        # Safety cleanup cannot depend on successful logging/fsync/free space.
        try:
            cleanup_owned(absolute_deadline=absolute_deadline)
            remaining(absolute_deadline)
        except BaseException as error:
            cleanup_error = error
        try:
            journal.record(
                identifier,
                "cleanup_unknown" if cleanup_error or recording_error else "cleanup_observed",
                {"retry_permitted": False, "native_qualified": False},
            )
        except BaseException as error:
            recording_error = error
        if cleanup_error is not None:
            raise RuntimeError("marketing_owned_cleanup_unknown_no_retry") from cleanup_error
        if recording_error is not None:
            raise RuntimeError("marketing_operator_journal_unknown_no_retry") from recording_error


def run_admitted_original(*args, **kwargs):
    marketing_native_gate()
    return drive_original(*args, **kwargs)
