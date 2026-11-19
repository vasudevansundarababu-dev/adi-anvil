"""Pure profile negatives; actual peer/Trial custody is tested on Linux QA."""

import copy
import os
import socket
import sys

import pytest

from anvil.golden_native_peer import OwnedSDKPeer, profile


def sdk():
    return {"Id": "a" * 64, "Image": "sha256:" + "b" * 64, "State": {"Running": True, "Pid": 123},
        "Config": {"Image": "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/kyc-runtime@sha256:" + "c" * 64,
                   "User": "0:0", "Env": ["ANVIL_ENV=local"]},
        "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True, "CapDrop": ["ALL"], "CapAdd": ["SYS_PTRACE"],
                       "PidMode": "host", "UTSMode": "host", "UsernsMode": "host", "CgroupnsMode": "host",
                       "SecurityOpt": ["no-new-privileges", "apparmor=unconfined"], "Privileged": False,
                       "Tmpfs": {"/tmp": "rw,noexec,size=128m"}, "Memory": 1536 * 1024**2, "PidsLimit": 256, "NanoCpus": 2_000_000_000},
        "Mounts": [{"Type": "bind", "Source": "/run/docker.sock", "Destination": "/run/docker.sock", "RW": False}]}


@pytest.mark.parametrize("field,value", [("NetworkMode", "host"), ("ReadonlyRootfs", False), ("CapAdd", ["SYS_ADMIN"]),
    ("CapDrop", []), ("Privileged", True), ("PidMode", ""), ("UsernsMode", ""), ("SecurityOpt", [])])
def test_changed_sdk_privilege_network_namespace_is_denied(field, value):
    info = sdk()
    info["HostConfig"][field] = value
    with pytest.raises(ValueError):
        profile(info)


def test_profile_binds_image_id_mount_permissions_and_rejects_ambient_secret():
    original = profile(sdk())
    changed = sdk()
    changed["Image"] = "sha256:" + "d" * 64
    assert profile(changed) != original
    changed = sdk()
    changed["Mounts"][0]["RW"] = True
    assert profile(changed) != original
    changed = sdk()
    changed["Config"]["Env"].append("DATABASE_URL=synthetic-not-a-secret")
    with pytest.raises(ValueError):
        profile(changed)
    changed = copy.deepcopy(sdk())
    changed["Config"]["User"] = "10001:10001"
    with pytest.raises(ValueError):
        profile(changed)


@pytest.mark.skipif(sys.platform != "linux" or not hasattr(os, "pidfd_open"), reason="Actual Linux Unix peer credentials required")
def test_actual_socket_peer_without_owned_framework_is_denied_before_any_effect(tmp_path):
    left, right = socket.socketpair()
    try:
        guard = OwnedSDKPeer({}, None, None, "not-a-job", tmp_path)
        with pytest.raises(ValueError, match="owned framework"):
            with guard(left):
                pytest.fail("Unowned real peer entered worker effect")
        assert not list(tmp_path.iterdir())
    finally:
        left.close()
        right.close()
