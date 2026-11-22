# ruff: noqa: F811
"""RL Gym v2: switching the registry mirror between registries (the local Studio stub and the local Studio). Sequence
numbers, event ids and cursors are kept per registry; a version id already mirrored may be confirmed by another
registry only with the same identity; version numbers are unique per registry, so Studio's own ids for a contract the
stub released sit beside the stub's releases."""

import time
import uuid

import psycopg
from psycopg.rows import dict_row
from test_rlgym_v2 import activated, person, ws  # noqa: F401

from anvil.config import setting
from anvil.rlgym.catalog import registry
from anvil.rlgym.common import system_scope


def _event(seq, kind, version):
    return {
        "specversion": "1.0",
        "id": f"reg-{seq:05d}",
        "type": kind,
        "source": "it",
        "subject": version["id"],
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data": {"seq": seq, "version": version},
    }


def _version(vid, digest, family="it-family"):
    return {
        "id": vid,
        "contract_id": vid.split("@")[0],
        "version": 1,
        "spec_sha256": "a" * 64,
        "image_digest": digest,
        "seed_ref": "it://seed",
        "seed_sha256": "b" * 64,
        "seed_family": family,
        "runtime_profile": "it",
        "tools": 1,
        "operations": ["noop"],
        "schema_tables": [],
        "image_recipe": None,
        "case_catalog": {"cases": 0},
    }


def _cards(ws, subject):
    groups = person("admin-1").get(ws["base"] + "/todo").json()["data"]["groups"]
    return [
        i
        for g in groups
        for i in g["items"]
        if i["kind"] == "registry_conflict" and i["subject"] == subject
    ]


def _rows(contract):
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        return c.execute(
            "SELECT * FROM catalog.environment_versions WHERE contract_id=%s ORDER BY id",
            (contract,),
        ).fetchall()


def test_registry_switch_keeps_sequences_apart_and_refuses_identity_changes(ws, monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    stub, studio = f"http://127.0.0.1:8211/it-{suffix}", f"http://127.0.0.1:8060/it-{suffix}"
    shared = f"it-shared-{suffix}@v1"  # released by the stub, later confirmed by Studio
    same = _version(shared, "sha256:" + "c" * 64)
    monkeypatch.setattr(registry, "registry_id", lambda: stub)
    with system_scope() as c:
        assert registry.apply_event(c, _event(1, "version.registered", same), "webhook")
        assert registry.apply_event(c, _event(2, "version.qualified", same), "webhook")
    monkeypatch.setattr(registry, "registry_id", lambda: studio)
    with system_scope() as c:
        # Studio's log starts at 1 again: not a duplicate of the stub's seq 1, and the same identity is confirmed.
        assert registry.apply_event(c, _event(1, "version.registered", same), "webhook")
        assert registry.apply_event(c, _event(2, "version.qualified", same), "webhook")
        assert not registry.apply_event(
            c, _event(2, "version.qualified", same), "webhook"
        )  # duplicate
        changed = _version(shared, "sha256:" + "d" * 64)
        assert registry.apply_event(c, _event(3, "version.revoked", changed), "webhook")
    (row,) = _rows(shared.split("@")[0])
    assert (
        row["registry"] == studio and row["state"] == "qualified"
    )  # the conflicting revoke was not applied
    assert row["image_digest"] == "sha256:" + "c" * 64
    assert _cards(ws, shared) and "image_digest" in _cards(ws, shared)[0]["reason"]


def test_studio_ids_sit_beside_stub_releases_and_numbers_are_unique_per_registry(ws, monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    stub, studio = f"http://127.0.0.1:8211/it-{suffix}", f"http://127.0.0.1:8060/it-{suffix}"
    contract = f"it-contract-{suffix}"
    monkeypatch.setattr(registry, "registry_id", lambda: stub)
    with system_scope() as c:
        old = _version(f"{contract}@v1", "sha256:" + "e" * 64, "stub-family")
        registry.apply_event(c, _event(1, "version.registered", old), "webhook")
        registry.apply_event(c, _event(2, "version.qualified", old), "webhook")
    monkeypatch.setattr(registry, "registry_id", lambda: studio)
    with system_scope() as c:
        new = _version(f"{contract}@1", "sha256:" + "f" * 64, "studio-family")
        registry.apply_event(c, _event(1, "version.registered", new), "webhook")
        registry.apply_event(c, _event(2, "version.qualified", new), "webhook")
        third = _version(f"{contract}@one", "sha256:" + "f" * 64, "studio-family")
        registry.apply_event(c, _event(3, "version.registered", third), "webhook")
    rows = {r["id"]: r for r in _rows(contract)}
    assert set(rows) == {f"{contract}@v1", f"{contract}@1"}
    assert (
        rows[f"{contract}@v1"]["registry"] == stub and rows[f"{contract}@1"]["registry"] == studio
    )
    assert rows[f"{contract}@v1"]["state"] == rows[f"{contract}@1"]["state"] == "qualified"
    cards = _cards(ws, f"{contract}@one")
    assert cards and "already released as" in cards[0]["reason"]


def test_forge_stub_exports_a_project_for_a_template_another_registry_released(activated):
    """For the Studio link: a template Studio releases (any `tpl_…` id and version) gets an ADI Forge project through the
    ADI Forge stub, and the RL Gym imports it as Ready."""
    import httpx
    from test_rlgym_v2 import FORGE, g, post, service

    from anvil.rlgym.common import sha

    suffix = uuid.uuid4().hex[:6]
    doc = {k: v for k, v in g.template().items() if k not in ("spec_sha256", "template_sha256")}
    doc.update(
        template_id=f"tpl_it{suffix}",
        version=3,
        name="Golden KYC (Studio link test)",
        studio_release="rel-it",
    )
    doc["spec_sha256"] = sha(
        {
            k: v
            for k, v in doc.items()
            if k not in ("forge_template_id", "forge_version", "spec_sha256")
        }
    )
    act = post(service("studio"), activated["base"] + "/templates/activations", doc, 201).json()[
        "data"
    ]
    assert act["state"] == "active"
    pid = f"prj_link{suffix}"
    with httpx.Client(timeout=60, trust_env=False) as client:
        export = client.post(
            FORGE + f"/stub/projects/{pid}/export",
            json={
                "send": False,
                "project_name": "KYC via Studio",
                "template": {
                    "id": doc["template_id"],
                    "version": 3,
                    "spec_sha256": doc["spec_sha256"],
                    "forge_template_id": "wf_118",
                    "forge_version": 1,
                },
            },
        ).json()["export"]
    receipt = post(
        service("forge"), activated["base"] + f"/projects/{pid}/exports", export, 201
    ).json()["data"]
    assert receipt["new"] == 40 and receipt["blocked"] == []
    project = person("admin-1").get(activated["base"] + f"/projects/{pid}").json()["data"]
    assert project["state"] == "ready" and project["template_id"] == doc["template_id"]
