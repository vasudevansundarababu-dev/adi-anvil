# ruff: noqa: F811
"""RL Gym v2, OpenEnv adapter (plan decision 1b, Part A) against Studio's own simulator image in local Docker.

The image is the one Studio built (label ai.adi-labs.utility.environment-key=golden-kyc-openenv); the test reads its
identity from the image's own labels and skips when no such image is present. Nothing is pulled from the network:
qualification and episodes run in containers with no network."""

import json
import shutil
import subprocess
import time
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row
from test_rlgym_v2 import person, ws  # noqa: F401
from test_rlgym_v2_registry import _event

from anvil.config import setting
from anvil.rlgym.catalog import registry
from anvil.rlgym.common import emit, system_scope
from anvil.rlgym.runs import images, openenv

LABEL = "ai.adi-labs.utility.environment-key=golden-kyc-openenv"


def _studio_image():
    if not shutil.which("docker") or not images.docker_status()[0]:
        return None
    ids = subprocess.run(
        ["docker", "images", "-q", "--no-trunc", "--filter", f"label={LABEL}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    if not ids:
        return None
    meta = json.loads(
        subprocess.run(
            ["docker", "image", "inspect", ids[0]], capture_output=True, text=True, check=True
        ).stdout
    )[0]
    labels = meta["Config"]["Labels"]
    return {
        "id": meta["Id"],
        "port": int(next(iter(meta["Config"]["ExposedPorts"])).split("/")[0]),
        "seed": labels["ai.adi-labs.utility.seed-sha256"],
        "spec": labels["ai.adi-labs.utility.spec-sha256"],
    }


IMAGE = _studio_image()
pytestmark = pytest.mark.skipif(
    IMAGE is None, reason="Studio's OpenEnv image is not in local Docker"
)


def _version(vid, seed=None):
    return {
        "id": vid,
        "contract_id": vid.split("@")[0],
        "version": 1,
        "spec_sha256": "a" * 64,
        "image_digest": IMAGE["id"],
        "seed_ref": "studio://seeds/it",
        "seed_sha256": seed or IMAGE["seed"],
        "seed_family": "it-openenv",
        "runtime_profile": "it",
        "tools": 21,
        "operations": ["application.read", "finding.write"],
        "schema_tables": [],
        "image_recipe": {
            "kind": "studio-openenv",
            "image_ref": IMAGE["id"],
            "image_digest": IMAGE["id"],
            "port": IMAGE["port"],
            "health_path": "/healthz",
            "ready_path": "/readyz",
            "environment_key": "golden-kyc-openenv",
            "spec_sha256": IMAGE["spec"],
            "qualification": {
                "read_operation": "application.read",
                "fixtures": ["kyc-individual-001", "kyc-individual-002"],
                "write_call": {
                    "operation_id": "finding.write",
                    "arguments": {"issue": "qualification probe", "evidence_ids": []},
                },
            },
            "limits": {"tool_calls": 100, "wall_seconds": 900},
        },
        "case_catalog": {"cases": 20},
    }


def _mirror(monkeypatch, version):
    reg = f"http://127.0.0.1:8060/it-{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(registry, "registry_id", lambda: reg)
    with system_scope() as c:
        assert registry.apply_event(c, _event(1, "version.registered", version), "webhook")
    return reg


def _receipt(vid):
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        return c.execute(
            "SELECT * FROM catalog.qualification_receipts WHERE subject_id=%s ORDER BY issued_at DESC LIMIT 1",
            (vid,),
        ).fetchone()


def _leftovers(label):
    return subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"label=ai.adi-labs.rlgym.run={label}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()


def test_studio_image_qualifies_over_its_own_routes(monkeypatch):
    vid = f"it-openenv-{uuid.uuid4().hex[:8]}@1"
    _mirror(monkeypatch, _version(vid))
    out = registry.qualify(vid)
    assert out["result"] == "qualified", out["checks"]
    assert out["mode"] == "openenv_http"
    assert [c["name"] for c in out["checks"]][0] == "identity"
    assert all(c["result"] == "pass" for c in out["checks"])
    row = _receipt(vid)
    assert row["mode"] == "openenv_http" and row["result"] == "qualified"
    assert not _leftovers(
        f"qual-{images.SAFE.sub('-', vid.lower())[:24]}"
    )  # the disposable container is gone


def test_a_different_seed_fails_identity_and_is_an_environment_defect(monkeypatch):
    vid = f"it-openenv-{uuid.uuid4().hex[:8]}@1"
    _mirror(monkeypatch, _version(vid, seed="0" * 64))
    out = registry.qualify(vid)
    assert out["result"] == "failed" and out["failure_class"] == "environment_defect"
    assert out["checks"][0]["name"] == "identity"
    assert out["checks"][0]["evidence"]["mismatches"]["seed_sha256"]["observed"] == IMAGE["seed"]


def test_admission_refuses_a_mismatched_simulator_and_removes_the_container():
    label = f"run-it{uuid.uuid4().hex[:6]}"
    env = {**_version("it-openenv@1", seed="0" * 64), "id": "it-openenv@1"}
    with pytest.raises(Exception) as refused:
        openenv.start_instance(label, env, IMAGE["id"])
    assert getattr(refused.value, "code", None) == "HASH_MISMATCH"
    assert "seed_sha256" in refused.value.details["mismatches"]
    assert not _leftovers(label)


def test_two_episodes_on_one_instance_do_not_share_state():
    label = f"run-it{uuid.uuid4().hex[:6]}"
    env = {**_version("it-openenv@1"), "id": "it-openenv@1"}
    rec = openenv.recipe(env)
    container, ready = openenv.start_instance(label, env, IMAGE["id"])
    try:
        inspect = subprocess.run(
            ["docker", "inspect", container], capture_output=True, text=True, check=True
        )
        host = json.loads(inspect.stdout)[0]["HostConfig"]
        assert (
            host["NetworkMode"] == "none" and host["ReadonlyRootfs"] and host["CapDrop"] == ["ALL"]
        )
        assert ready["environment_key"] == "golden-kyc-openenv"
        first = openenv.OpenEnvSession(container, rec, time.monotonic() + 60)
        first.request({"op": "reset", "case_id": "kyc-individual-001"})
        wrote = first.request(
            {
                "op": "call",
                "tool": "finding.write",
                "args": {"issue": "episode one", "evidence_ids": []},
            }
        )
        assert wrote["ok"], wrote
        state = first.request({"op": "state"})
        first.close()
        assert state["writes"] == 1 and state["studio_sealed"]["sealed_sha256"]
        second = openenv.OpenEnvSession(container, rec, time.monotonic() + 60)
        second.request({"op": "reset", "case_id": "kyc-individual-002"})
        assert second.request({"op": "state"})["writes"] == 0
        second.close()
    finally:
        images.stop_instance(container)


def test_an_image_mismatch_opens_an_environment_defect_card(ws):
    vid = f"it-openenv-{uuid.uuid4().hex[:8]}@1"
    with system_scope(ws["id"]) as c:
        emit(
            c,
            ws["id"],
            "environment.image_mismatch",
            vid,
            {
                "version_id": vid,
                "run_id": "run-9999",
                "reason": "The local image differs from the registered environment version",
                "image_digest": {"registered": "sha256:" + "1" * 64, "observed": IMAGE["id"]},
            },
        )
    groups = person("admin-1").get(ws["base"] + "/todo").json()["data"]["groups"]
    cards = [
        i
        for g in groups
        for i in g["items"]
        if i["kind"] == "environment_defect" and i["subject"] == vid
    ]
    assert len(cards) == 1 and "image_digest" in cards[0]["reason"]
