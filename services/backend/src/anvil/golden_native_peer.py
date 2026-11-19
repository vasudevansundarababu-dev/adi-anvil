"""Kernel peer and owned SDK-container custody for the nonspending bridge.

Bearer tokens are secondary. The actual Unix peer must be the unreaped, fixed
framework child of this coordinator, in the original operator-observed image,
namespace, command and mount profile. Actor/verifier are never such a peer.
"""

import os
import re
import select
import socket
import struct
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


def inspect_sdk(host):
    """Read-only daemon observation; never create/reuse a work config folder."""
    path = Path(host.removeprefix("unix://"))
    if not host.startswith("unix:///") or not path.is_socket() or path.resolve() != path:
        raise ValueError("Exact local Docker socket required")
    identifier = container_id(os.getpid())
    with tempfile.TemporaryDirectory(prefix=".sdk-inspect-", dir="/tmp") as empty:
        result = subprocess.run(["/usr/bin/docker", "--config", empty, "--host", host, "inspect", identifier],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "HOME": empty, "LANG": "C"}, timeout=3)
    if result.returncode or len(result.stdout) > 1048576:
        raise ValueError("Bounded SDK daemon observation failed")
    import json

    values = json.loads(result.stdout)
    if len(values) != 1 or values[0]["Id"] != identifier:
        raise ValueError("One actual current SDK container required")
    return profile(values[0])


def container_id(pid):
    raw = (Path("/proc") / str(pid) / "cgroup").read_bytes()
    if len(raw) > 8192:
        raise ValueError("Bounded SDK cgroup identity required")
    matches = set(re.findall(rb"(?:docker-|/docker/)([a-f0-9]{64})(?:\.scope|/|\n|$)", raw))
    if len(matches) != 1:
        raise ValueError("One actual SDK Docker cgroup required")
    return matches.pop().decode()


def profile(info):
    config, host = info["Config"], info["HostConfig"]
    if (not re.fullmatch(r"us-west1-docker\.pkg\.dev/adi-anvil-mvp-2026/anvil-qa-v1/kyc-runtime@sha256:[a-f0-9]{64}", config["Image"])
            or not info["State"]["Running"] or info["State"]["Pid"] <= 1
            or config["User"] != "0:0" or host["NetworkMode"] != "none" or not host["ReadonlyRootfs"]
            or set(host.get("CapDrop") or []) != {"ALL"} or set(host.get("CapAdd") or []) != {"SYS_PTRACE"}
            or any(host[key] != "host" for key in ("PidMode", "UTSMode", "UsernsMode", "CgroupnsMode"))
            or set(host.get("SecurityOpt") or []) != {"no-new-privileges", "apparmor=unconfined"}
            or host.get("Privileged") or any(value for key, value in (item.split("=", 1) for item in config["Env"])
                                             if any(marker in key for marker in ("DATABASE", "TOKEN", "PASSWORD", "SECRET", "CREDENTIAL", "API_KEY", "PRIVATE_KEY")))):
        raise ValueError("Exact trusted SDK profile without ambient credential variables required")
    mounts = sorted(({key: mount[key] for key in ("Type", "Source", "Destination", "RW")} for mount in info["Mounts"]), key=lambda value: value["Destination"])
    if any(mount["Type"] != "bind" for mount in mounts):
        raise ValueError("Fixed SDK bind profile required")
    return {"schema_version": "anvil.owned-sdk-profile.v1", "image": config["Image"],
            "image_id": info["Image"], "mounts": mounts,
            "tmpfs": host.get("Tmpfs"), "memory": host["Memory"], "pids": host["PidsLimit"], "cpu": host["NanoCpus"]}


def validate_control_mounts(observed, *, proof_root, provider_path, docker, compose):
    """Reviewed fixed two-read control layout, NOT a secret-free paid profile.

    This control's fixed SQL worker is inside the trusted root TCB, so it has
    exactly one private scheduler-provider mount. No other credential/source
    mount is permitted. Production mediated profiles must be independently
    qualified and cannot reuse this allowance.
    """
    private = Path(provider_path).parent
    if (private.parent != proof_root.parent or not re.fullmatch(r"probe-config-[a-f0-9]{7,40}-v[1-9][0-9]*", private.name)
            or private == proof_root):
        raise ValueError("Fixed independent probe provider directory required")
    proxy = private.with_name(private.name.replace("probe-config-", "probe-pg-proxy-", 1))
    expected = {str(proof_root): (str(proof_root), True), str(private): (str(private), False),
                "/var/run/forge-probe-postgresql": (str(proxy), False), "/run/docker.sock": ("/run/docker.sock", False),
                docker: (docker, False), compose: (compose, False)}
    actual = {mount["Destination"]: (mount["Source"], mount["RW"]) for mount in observed["mounts"]}
    if len(observed["mounts"]) != 6 or actual != expected:
        raise ValueError("Actual SDK mounts differ from the reviewed fixed control layout")


def observed_profile(docker, *, init_only=False):
    identifier = container_id(os.getpid())
    info = docker.inspect(identifier)
    if info["Id"] != identifier or init_only and info["State"]["Pid"] != os.getpid():
        raise ValueError("Coordinator must be actual SDK container init")
    return profile(info)


class OwnedSDKPeer:
    def __init__(self, holder, docker, expected_profile, job_id, folder, *, mediated_plan=None):
        self.holder, self.docker, self.expected = holder, docker, expected_profile
        self.job_id, self.folder = job_id, folder
        self.mediated_plan = mediated_plan
        self.observations = []

    @contextmanager
    def __call__(self, connection):
        from anvil.environment_harbor import (
            ROOT,
            _fixed_group_owned,
            operator_proof_module,
            private_json,
        )
        from anvil.harbor_worker import process_identity

        if not hasattr(socket, "SO_PEERCRED") or not hasattr(os, "pidfd_open"):
            raise RuntimeError("Actual Linux peer custody required")
        pid, uid, gid = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
        child = self.holder.get("_framework_child")
        if (type(child) is not subprocess.Popen or child.pid != pid or uid != os.geteuid() or gid != os.getegid()
                or not _fixed_group_owned(child)):
            raise ValueError("Original owned framework peer required")
        descriptor = os.pidfd_open(pid, 0)
        try:
            poller = select.poll()
            poller.register(descriptor, select.POLLIN)

            def check(*, verify_runtime=False):
                if (self.holder["_callback_closing"].is_set() or poller.poll(0) or child._anvil_owned_group.exited()
                        or process_identity(pid) != child._anvil_start_identity
                        or container_id(pid) != container_id(os.getpid())):
                    raise ValueError("Original SDK peer died or changed")
                info = self.docker.inspect(container_id(pid))
                if (self.mediated_plan is None and info["State"]["Pid"] != os.getpid()) or profile(info) != self.expected:
                    raise ValueError("Actual SDK image or mount profile changed")
                command = (Path("/proc") / str(os.getpid()) / "cmdline").read_bytes().split(b"\0")[:-1]
                expected = [b"/opt/anvil-runtime/bin/python", b"-I", b"-B", b"-m", b"anvil.golden_kyc_probe", b"--job", self.job_id.encode()]
                if self.mediated_plan is not None:
                    from anvil.golden_native_mediated import MediatedPlan

                    if type(self.mediated_plan) is not MediatedPlan:
                        raise ValueError("Exact owned mediated plan required")
                    expected = [b"/opt/anvil-runtime/bin/python", b"-I", b"-B", b"-m", b"anvil.golden_native_bridge", b"--once", self.mediated_plan.path.stem.encode()]
                if command != expected:
                    raise ValueError("Fixed installed bridge coordinator command required")
                if self.mediated_plan is None:
                    module = operator_proof_module()
                    with module.TechnicalProbeStore(ROOT) as store:
                        permission = store.load_probe(self.job_id)
                        store._framework_entry(permission)
                else:
                    self.mediated_plan.framework(child, verify_runtime=verify_runtime)

            # Full immutable installed closure at both boundaries. Fresh
            # kernel identity/profile/current plan remains mandatory for
            # every status query inside the held original PIDFD interval.
            check(verify_runtime=True)
            number = len(self.observations)
            if number >= 2:
                raise ValueError("At most actor and verifier peer entries required")
            observation = {"schema_version": "anvil.owned-sdk-peer-observation.v1", "pid": pid,
                           "identity": child._anvil_start_identity, "uid": uid, "gid": gid,
                           "container_id": container_id(pid), "image": self.expected["image"],
                           "job_id": self.job_id, "entry": number,
                           "purpose": "technical_control_only" if self.mediated_plan is None else "worker_collection_only"}
            private_json(self.folder / ("sdk-peer-" + str(number) + ".json"), observation)
            self.observations.append(observation)
            lease = SDKPeerLease(check)
            with self.holder["_callback_lock"]:
                if self.holder["_callback_closing"].is_set() or self.holder.get("_sdk_peer_lease") is not None:
                    raise ValueError("SDK peer closing or already entered")
                self.holder["_sdk_peer_lease"] = lease
            try:
                yield
                check(verify_runtime=True)
            finally:
                with self.holder["_callback_lock"]:
                    lease.closed = True
                    self.holder.pop("_sdk_peer_lease", None)
        finally:
            os.close(descriptor)


class SDKPeerLease:
    def __init__(self, check):
        self._check, self.closed = check, False

    def check(self):
        if self.closed:
            raise ValueError("Original SDK peer released")
        self._check()
        if self.closed:
            raise ValueError("Original SDK peer released during observation")
