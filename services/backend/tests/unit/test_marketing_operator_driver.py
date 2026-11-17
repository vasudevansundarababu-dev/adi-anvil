import json
import os
from threading import Thread
from uuid import uuid4

import pytest
from test_marketing_operator_observation import packet

from anvil import marketing_native_boundary as boundary
from anvil import marketing_native_operator_driver as driver
from anvil.marketing_native_job_packet import encode_original_job
from anvil.marketing_native_operator_observation import OperatorNetworkObservation


def original_observation(deadline):
    import hashlib

    values = packet()
    docs = [json.dumps(values[k * 64], sort_keys=True).encode() for k in "abc"]
    profile = {
        "schema_version": "anvil.marketing-container-operator-network-candidate.v1",
        "operator_container_id": "a" * 64,
        "api_container_id": "b" * 64,
        "network_id": "c" * 64,
        "operator_image_id": "sha256:" + "d" * 64,
        "operator_host_pid": 123,
        "network_namespace": {"device": 4, "inode": 99},
        "original_deadline_monotonic": deadline,
        "original_cleanup_seconds": 5,
        **{
            role + "_inspect_sha256": hashlib.sha256(raw).hexdigest()
            for role, raw in zip(("operator", "api", "network"), docs, strict=True)
        },
    }
    return OperatorNetworkObservation(boundary._bounded_canonical(profile, 8192), *docs)


def task(job):
    graph = {"origin": "manufactured_protocol_control"}
    execution = {"workflow_graph": graph, "workflow_graph_sha256": boundary._digest(graph)}
    case = {"case_id": "manufactured-US-case", "locale": "en-US", "snapshot_sha256": "a" * 64}
    native = {
        "execution_sha256": boundary._digest(execution),
        "workflow_graph_sha256": boundary._digest(graph),
        "case_assignment": case,
    }
    prepared = {
        "mode": "marketing-native",
        "native_binding": native,
        "execution": execution,
        "world_attachment": {"episode_id": "manufactured-episode"},
        "world_attachment_sha256": boundary._digest({"episode_id": "manufactured-episode"}),
        "public_actor": {"origin": "manufactured_software_control"},
        "group_id": "group",
        "max_calls": 20,
        "request_timeout_seconds": 10,
        "episode_timeout_seconds": 60,
        "repetition": 1,
    }
    value = {k: "a" * 64 for k in boundary.HASH_FIELDS}
    value.update({k: "manufactured-" + k for k in boundary.IDENTITY_FIELDS})
    value.update({k: prepared.get(k, 1) for k in boundary.INTEGER_FIELDS})
    value.update(
        schema_version=boundary.SCHEMA,
        purpose=boundary.PURPOSE,
        environment="qa",
        case_assignment=case,
        group_id="group",
        native_binding_sha256=boundary._digest(native),
        execution_sha256=boundary._digest(execution),
        workflow_graph_sha256=boundary._digest(graph),
        public_actor_sha256=boundary._digest(prepared["public_actor"]),
    )
    for field, key in (
        ("project_id", "project_id"),
        ("actor_id", "actor_id"),
        ("job_id", "id"),
        ("plan_id", "plan_id"),
    ):
        value[field] = str(job[key])
    return boundary._bounded_canonical(
        prepared, boundary.DOCUMENT_CAP
    ), boundary._bounded_canonical(value, boundary.DOCUMENT_CAP).decode()


@pytest.fixture
def operation(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(driver, "monotonic", lambda: clock[0])
    root = tmp_path / "operator-journal"
    root.mkdir(mode=0o700)
    journal = driver.DriverJournal.for_owned_local_test(root)
    job = {key: str(uuid4()) for key in ("id", "project_id", "actor_id", "plan_id", "lease_token")}
    prepared, request = task(job)
    processes = {
        role: {
            "pid": pid,
            "start_ticks": 12,
            "command_sha256": "c" * 64,
            "input_deadline_monotonic": 200,
        }
        for role, pid in [("control", 17), ("receiver", 18)]
    }
    processes["control"]["environment_sha256"] = "d" * 64
    ready = {
        "schema_version": "anvil.marketing-operator-prestarted.v1",
        "processes": processes,
        "native_qualified": False,
    }
    final = {
        "schema_version": "anvil.marketing-operator-pair-exit.v1",
        "state": "original_pair_exits_observed",
        "native_qualified": False,
    }
    events = []

    class Channel:
        def send(self, raw, deadline):
            events.append(("send", json.loads(raw[9:]), deadline))

        def receive(self, deadline):
            events.append(("receive", deadline))
            return ready if sum(e[0] == "receive" for e in events) == 1 else final

    def prepare(original, observed, *, absolute_deadline):
        assert (root / (job["id"] + ".prepare_intent.json")).is_file()
        assert observed == processes and original == job and absolute_deadline == 195
        events.append(("prepare",))
        return prepared

    def bind(original, observed, raw, *, absolute_deadline):
        assert (root / (job["id"] + ".prepared.json")).is_file()
        assert raw == prepared and observed == processes and absolute_deadline == 195
        events.append(("bind",))
        return {
            "schema_version": "anvil.marketing-original-private-control-input.v2",
            "request": request,
            "job": encode_original_job(original),
            "once_prepared": raw.decode(),
        }

    def cleanup(*, absolute_deadline):
        assert absolute_deadline == 200
        events.append(("cleanup",))

    kwargs = dict(
        prepare_once=prepare,
        bind_original=bind,
        cleanup_owned=cleanup,
        absolute_deadline=200,
        cleanup_seconds=5,
    )
    try:
        yield (
            journal,
            job,
            original_observation(200),
            Channel(),
            kwargs,
            events,
            clock,
            root,
            ready,
            final,
        )
    finally:
        journal.close()


def run(value):
    journal, job, observation, channel, kwargs, *_ = value
    return driver.drive_original(journal, job, observation, {}, channel, **kwargs)


def test_ordering_and_original_once_prepared_bytes_are_retained(operation):
    result = run(operation)
    _, job, _, _, _, events, _, root, _, _ = operation
    assert [e[0] for e in events] == [
        "send",
        "receive",
        "prepare",
        "bind",
        "send",
        "receive",
        "cleanup",
    ]
    assert result["native_qualified"] is False
    assert (root / (job["id"] + ".exit_observed.json")).is_file()
    assert job["lease_token"] not in "".join(p.read_text() for p in root.iterdir())
    with pytest.raises(FileExistsError):
        run(operation)
    assert sum(e[0] == "prepare" for e in events) == 1


def test_prepare_failure_is_durable_unknown_and_never_retried(operation):
    def fail(*_, **__):
        raise RuntimeError("manufactured_ambiguous_prepare")

    operation[4]["prepare_once"] = fail
    with pytest.raises(RuntimeError, match="ambiguous_prepare"):
        run(operation)
    assert (operation[7] / (operation[1]["id"] + ".outcome_unknown.json")).is_file()
    with pytest.raises(FileExistsError):
        run(operation)
    assert [e[0] for e in operation[5]] == ["send", "receive", "cleanup"]


def test_extended_observation_cutoff_denies_before_any_intent_or_prepare(operation):
    operation[4]["absolute_deadline"] = 201
    with pytest.raises(ValueError, match="observation_deadline_changed"):
        run(operation)
    assert not list(operation[7].iterdir()) and operation[5] == []


def test_mutated_prepare_response_cannot_supply_second_frame(operation):
    original = operation[4]["bind_original"]

    def change(*args, **kwargs):
        value = original(*args, **kwargs)
        value["once_prepared"] = "{}"
        return value

    operation[4]["bind_original"] = change
    with pytest.raises(ValueError, match="bound_input_changed"):
        run(operation)
    assert sum(e[0] == "send" for e in operation[5]) == 1


def test_numeric_false_cannot_claim_pair_exit_or_native_acceptance(operation):
    operation[9]["native_qualified"] = 0
    with pytest.raises(ValueError, match="pair_exit_observation_required"):
        run(operation)


def test_original_input_cutoff_is_checked_after_prepare_and_before_binding(operation):
    original = operation[4]["prepare_once"]

    def slow(*args, **kwargs):
        result = original(*args, **kwargs)
        operation[6][0] = 196
        return result

    operation[4]["prepare_once"] = slow
    with pytest.raises(TimeoutError):
        run(operation)
    assert not any(e[0] == "bind" for e in operation[5])


def test_real_pipes_enforce_frame_size_before_reading_unbounded_body():
    incoming, peer_write = os.pipe()
    peer_read, outgoing = os.pipe()
    channel = driver.BootstrapChannel(incoming, outgoing)
    try:
        os.write(peer_write, b"00002001\n")
        with pytest.raises(ValueError, match="public_reply_capacity"):
            channel.receive(driver.monotonic() + 1)
    finally:
        for descriptor in (incoming, peer_write, peer_read, outgoing):
            os.close(descriptor)


def test_real_pipe_roundtrip_retains_exact_frame_and_handles_fragmented_reply():
    incoming, peer_write = os.pipe()
    peer_read, outgoing = os.pipe()
    channel = driver.BootstrapChannel(incoming, outgoing)
    errors = []

    def peer():
        try:
            assert os.read(peer_read, 11) == b"00000002\n{}"
            for chunk in (b"0000", b"0002\n", b"{", b"}"):
                os.write(peer_write, chunk)
        except BaseException as error:
            errors.append(type(error).__name__)

    thread = Thread(target=peer)
    thread.start()
    try:
        channel.send(b"00000002\n{}", driver.monotonic() + 2)
        assert channel.receive(driver.monotonic() + 2) == {}
        thread.join(timeout=2)
        assert not thread.is_alive() and not errors
    finally:
        for descriptor in (incoming, peer_write, peer_read, outgoing):
            os.close(descriptor)


def test_operational_gate_remains_closed_before_any_adapter_or_effect():
    with pytest.raises(RuntimeError, match="not_admitted"):
        driver.run_admitted_original()


@pytest.mark.parametrize(
    "stage",
    [
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
    ],
)
def test_journal_failures_never_skip_or_repeat_owned_cleanup(operation, monkeypatch, stage):
    original = operation[0].record

    def failed(identifier, name, value):
        if name == stage:
            raise OSError("manufactured_ENOSPC")
        original(identifier, name, value)

    monkeypatch.setattr(operation[0], "record", failed)
    if stage == "outcome_unknown":

        def prepare(*args, **kwargs):
            raise RuntimeError("original_ambiguous_prepare")

        operation[4]["prepare_once"] = prepare
    if stage == "cleanup_unknown":

        def cleanup(*, absolute_deadline):
            assert absolute_deadline == 200
            operation[5].append(("cleanup",))
            raise RuntimeError("original_cleanup_unconfirmed")

        operation[4]["cleanup_owned"] = cleanup
    with pytest.raises((OSError, RuntimeError)):
        run(operation)
    assert sum(e[0] == "cleanup" for e in operation[5]) == 1
    assert (operation[7] / (operation[1]["id"] + ".intent.json")).is_file()
    with pytest.raises(FileExistsError):
        run(operation)
    assert sum(e[0] == "cleanup" for e in operation[5]) == 1
