# ruff: noqa: F811
"""RL Gym v2: switching the registry mirror between registries (the local Studio stub and the local Studio). Sequence
numbers, event ids and cursors are kept per registry; a version id another registry already released may be confirmed
only with the same identity, otherwise the conflict is recorded and the mirrored release is kept."""

import time
import uuid

import psycopg
from psycopg.rows import dict_row
from test_rlgym_v2 import person, ws  # noqa: F401

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


def _version(vid, digest):
    return {
        "id": vid,
        "contract_id": vid.split("@")[0],
        "version": 1,
        "spec_sha256": "a" * 64,
        "image_digest": digest,
        "seed_ref": "it://seed",
        "seed_sha256": "b" * 64,
        "seed_family": "it-family",
        "runtime_profile": "it",
        "tools": 1,
        "operations": ["noop"],
        "schema_tables": [],
        "image_recipe": None,
        "case_catalog": {"cases": 0},
    }


def test_registry_switch_keeps_sequences_apart_and_refuses_identity_changes(ws, monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    vid = f"it-registry-switch-{suffix}@v1"
    stub, studio = f"http://127.0.0.1:8211/it-{suffix}", f"http://127.0.0.1:8060/it-{suffix}"
    same = _version(vid, "sha256:" + "c" * 64)
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
        renamed = {**same, "id": vid.replace("@v1", "@1")}
        assert registry.apply_event(c, _event(3, "version.registered", renamed), "webhook")
        changed = _version(vid, "sha256:" + "d" * 64)
        assert registry.apply_event(c, _event(4, "version.revoked", changed), "webhook")
    with psycopg.connect(setting("MIGRATION_DATABASE_URL"), row_factory=dict_row) as c:
        row = c.execute("SELECT * FROM catalog.environment_versions WHERE id=%s", (vid,)).fetchone()
        events = c.execute(
            "SELECT registry, seq FROM catalog.registry_events WHERE subject IN (%s,%s) ORDER BY registry, seq",
            (vid, vid.replace("@v1", "@1")),
        ).fetchall()
    assert (
        row["registry"] == studio and row["state"] == "qualified"
    )  # the conflicting revoke was not applied
    assert row["image_digest"] == "sha256:" + "c" * 64
    assert sorted((e["registry"], e["seq"]) for e in events) == sorted(
        [(stub, 1), (stub, 2), (studio, 1), (studio, 2), (studio, 3), (studio, 4)]
    )
    groups = person("admin-1").get(ws["base"] + "/todo").json()["data"]["groups"]
    cards = [
        i
        for g in groups
        for i in g["items"]
        if i["kind"] == "registry_conflict" and i["subject"] == vid
    ]
    assert cards and "image_digest" in cards[0]["reason"]
    renamed_cards = [
        i
        for g in groups
        for i in g["items"]
        if i["kind"] == "registry_conflict" and i["subject"] == vid.replace("@v1", "@1")
    ]
    assert renamed_cards and "already released as" in renamed_cards[0]["reason"]
