"""Bounded read-only original Engine/process observations, never admission.

Fixed inspect projections exclude Config.Env, logs and provider material. Only
retained exact IDs are accepted. No create/start/exec/namespace mutation or retry.
"""

import hashlib
import os
import re
import selectors
import signal
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import monotonic

from anvil.marketing_native_boundary import _bounded_canonical
from anvil.marketing_native_operator_network import validate_container_operator_network
from anvil.owned_process_group import UnreapedProcessGroup

CAP = 1048576
CONTAINER_FORMAT = (
    '{"Id":{{json .Id}},"Image":{{json .Image}},'
    '"State":{"Running":{{json .State.Running}},"Pid":{{json .State.Pid}}},'
    '"HostConfig":{'
    + ",".join(
        '"' + name + '":{{json .HostConfig.' + name + "}}"
        for name in (
            "NetworkMode",
            "PidMode",
            "CgroupnsMode",
            "ReadonlyRootfs",
            "Privileged",
            "PortBindings",
            "PublishAllPorts",
            "ExtraHosts",
            "Dns",
            "DnsSearch",
            "DnsOptions",
        )
    )
    + '},"NetworkSettings":{"Networks":{{json .NetworkSettings.Networks}}}}'
)
NETWORK_FORMAT = (
    '{"Id":{{json .Id}},"Driver":{{json .Driver}},"Scope":{{json .Scope}},'
    '"Ingress":{{json .Ingress}},"Containers":{{json .Containers}}}'
)


def _remaining(deadline):
    value = deadline - monotonic()
    if value <= 0:
        raise TimeoutError("marketing_operator_original_observation_deadline")
    return value


def _inspect(kind, identifier, deadline):
    """One fixed CLI metadata query with byte/time bounds and owned cleanup."""
    _remaining(deadline)
    work_deadline = deadline - min(1, _remaining(deadline) / 2)
    template = CONTAINER_FORMAT if kind == "container" else NETWORK_FORMAT
    child = subprocess.Popen(
        [
            "/usr/bin/docker",
            "--host",
            "unix:///run/docker.sock",
            kind,
            "inspect",
            "--format",
            template,
            identifier,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        start_new_session=True,
    )
    group = UnreapedProcessGroup(child)
    raw = bytearray()
    try:
        os.set_blocking(child.stdout.fileno(), False)
        with selectors.DefaultSelector() as selected:
            selected.register(child.stdout, selectors.EVENT_READ)
            while True:
                if not selected.select(_remaining(work_deadline)):
                    raise TimeoutError("marketing_operator_inspect_deadline")
                chunk = os.read(child.stdout.fileno(), min(65536, CAP + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > CAP:
                    raise ValueError("marketing_operator_inspect_capacity")
        while not group.exited():
            # Wait without reaping, so cleanup cannot signal a reused PGID.
            import time

            time.sleep(min(0.01, _remaining(work_deadline)))
    finally:
        errors = []
        try:
            group.signal(signal.SIGKILL)
        except BaseException as error:
            errors.append(error)
        try:
            child.stdout.close()
        except BaseException as error:
            errors.append(error)
        try:
            group.reap(max(0, deadline - monotonic()))
        except BaseException as error:
            errors.append(error)
        if errors:
            raise RuntimeError("marketing_operator_inspect_cleanup_unknown") from errors[0]
    if child.returncode != 0:
        raise RuntimeError("marketing_operator_inspect_unavailable")
    _remaining(deadline)
    return bytes(raw)


@contextmanager
def _process(pid, deadline):
    """Retain one live Linux PID identity and its actual network namespace."""
    _remaining(deadline)
    pidfd = os.pidfd_open(pid, 0)
    descriptor = proc = None
    try:
        proc = os.open(f"/proc/{pid}", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptor = os.open("ns/net", os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc)
        original = os.fstat(descriptor)

        def read():
            _remaining(deadline)
            with selectors.DefaultSelector() as selected:
                selected.register(pidfd, selectors.EVENT_READ)
                if selected.select(0):
                    raise ValueError("marketing_operator_original_process_exited")
            statfd = os.open("stat", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=proc)
            namespace = None
            try:
                raw = os.read(statfd, 8193)
                namespace = os.open("ns/net", os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc)
                actual = os.fstat(namespace)
            finally:
                os.close(statfd)
                if namespace is not None:
                    os.close(namespace)
            if len(raw) > 8192 or b") " not in raw:
                raise ValueError("marketing_operator_original_pid_stat_required")
            parts = raw.rsplit(b") ", 1)[1].split()
            if len(parts) < 20 or parts[0] in (b"Z", b"X"):
                raise ValueError("marketing_operator_live_process_required")
            if (actual.st_dev, actual.st_ino) != (original.st_dev, original.st_ino):
                raise ValueError("marketing_operator_network_namespace_changed")
            _remaining(deadline)
            return {"device": actual.st_dev, "inode": actual.st_ino}, int(parts[19])

        yield read
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if proc is not None:
            os.close(proc)
        os.close(pidfd)


@dataclass(frozen=True, slots=True, repr=False)
class OperatorNetworkObservation:
    profile: bytes = field(repr=False)
    operator_inspect: bytes = field(repr=False)
    api_inspect: bytes = field(repr=False)
    network_inspect: bytes = field(repr=False)


def observe_container_operator_network(
    operator_id, api_id, network_id, image_id, *, absolute_deadline, cleanup_seconds
):
    import math

    if (
        any(
            type(v) is not str or not re.fullmatch("[0-9a-f]{64}", v)
            for v in (operator_id, api_id, network_id)
        )
        or operator_id == api_id
        or type(image_id) is not str
        or not re.fullmatch("sha256:[0-9a-f]{64}", image_id)
        or type(absolute_deadline) not in (int, float)
        or not math.isfinite(absolute_deadline)
        or type(cleanup_seconds) is not int
        or not 1 <= cleanup_seconds <= 600
    ):
        raise ValueError("marketing_exact_original_operator_invocation_required")
    deadline = absolute_deadline - cleanup_seconds
    if absolute_deadline - monotonic() > 600:
        raise ValueError("marketing_operator_lifecycle_bound_required")
    _remaining(deadline)
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("marketing_existing_linux_root_observer_required")
    operator = _inspect("container", operator_id, deadline)
    api = _inspect("container", api_id, deadline)
    network = _inspect("network", network_id, deadline)
    # The existing parser rejects duplicates/nonfinite/oversized input before
    # any PID is selected. No untrusted PID or executable path comes from a caller.
    from anvil.marketing_native_operator_network import _document

    value = _document(operator, CAP)
    pid = value.get("State", {}).get("Pid")
    if (
        value.get("Id") != operator_id
        or value.get("Image") != image_id
        or type(pid) is not int
        or pid <= 0
    ):
        raise ValueError("marketing_original_operator_image_and_pid_required")
    with _process(pid, deadline) as read_process:
        namespace, ticks = read_process()
        for kind, identifier, original in (
            ("container", operator_id, operator),
            ("container", api_id, api),
            ("network", network_id, network),
        ):
            if original != _inspect(kind, identifier, deadline):
                raise ValueError("marketing_operator_changed_during_observation")
        if (namespace, ticks) != read_process():
            raise ValueError("marketing_operator_pid_or_namespace_changed")
    profile = {
        "schema_version": "anvil.marketing-container-operator-network-candidate.v1",
        "operator_container_id": operator_id,
        "api_container_id": api_id,
        "network_id": network_id,
        "operator_image_id": image_id,
        "operator_host_pid": pid,
        "network_namespace": namespace,
        "original_deadline_monotonic": absolute_deadline,
        "original_cleanup_seconds": cleanup_seconds,
        **{
            role + "_inspect_sha256": hashlib.sha256(raw).hexdigest()
            for role, raw in (("operator", operator), ("api", api), ("network", network))
        },
    }
    raw = _bounded_canonical(profile, 8192)
    validate_container_operator_network(raw, operator, api, network)
    _remaining(deadline)
    return OperatorNetworkObservation(raw, operator, api, network)


def bootstrap_frame(observation, runtime):
    if type(observation) is not OperatorNetworkObservation or type(runtime) is not dict:
        raise ValueError("marketing_original_typed_bootstrap_input_required")
    validate_container_operator_network(
        observation.profile,
        observation.operator_inspect,
        observation.api_inspect,
        observation.network_inspect,
    )
    value = {
        "schema_version": "anvil.marketing-original-operator-bootstrap.v1",
        "runtime": runtime,
        "network_profile": observation.profile.decode("utf-8"),
        "operator_inspect": observation.operator_inspect.decode("utf-8"),
        "api_inspect": observation.api_inspect.decode("utf-8"),
        "network_inspect": observation.network_inspect.decode("utf-8"),
    }
    raw = _bounded_canonical(value, CAP)
    return f"{len(raw):08x}\n".encode() + raw
