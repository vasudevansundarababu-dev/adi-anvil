"""Receiver reloads manufactured actual bytes; no physical capture acceptance."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_marketing_capture_evidence import loader, packet

from anvil import marketing_capture_evidence_store as store
from anvil.marketing_capture_evidence import prepare
from anvil.praxis_generic_contract import digest


def receiver():
    context, rows, _ = packet()
    now = datetime.now(timezone.utc)
    context.update(expires_at=(now + timedelta(seconds=120)).isoformat(),
                   materialize_before=(now + timedelta(seconds=90)).isoformat())
    prepared = prepare(context, rows, now=now)
    value = {"enrollment_id": context["enrollment_id"], "manifest_sha256": prepared.sha256,
             "descriptor": deepcopy(prepared.descriptor), "quiescence": deepcopy(context["quiescence"]),
             "quiescence_stored_sha256": digest(context["quiescence"]),
             "canonical_body": prepared.manifest.decode()}
    expected = {"manifest_id": context["manifest_id"], "manifest_sha256": prepared.sha256,
                "descriptor_sha256": digest(prepared.descriptor)}
    intake = {"intent_id": str(uuid4()), "enrollment_id": context["enrollment_id"], "scope": deepcopy(context["scope"])}
    original = loader(rows, prepared.snapshots)
    calls = []

    class Connection:
        def execute(self, sql, args):
            calls.append((sql, args))
            if "capture_evidence_for_intake" in sql:
                assert str(args[0]) == intake["intent_id"] and str(args[1]) == expected["manifest_id"]
                result = value
            else:
                assert "capture_evidence_original" in sql
                raw = original(*args[2:])
                result = None if raw is None else {"encoding": "retained_canonical_utf8", "canonical_body": raw.decode()}
            return SimpleNamespace(fetchone=lambda: {"value": result})

    return Connection(), intake, expected, value, calls


def test_signed_reference_requires_actual_complete_private_content_not_only_ids():
    connection, intake, expected, _, calls = receiver()
    assert store.verify_reference(connection, intake, expected) == {
        "content_verified": True, "capture_accepted": False, "native_qualified": False,
    }
    assert len(calls) == 23


@pytest.mark.parametrize("change", ["missing_hash", "descriptor_hash", "enrollment", "foreign_scope", "stored_quiescence", "quiescence_body", "content"])
def test_reference_substitution_or_missing_actual_bytes_never_accepts(change):
    connection, intake, expected, value, calls = receiver()
    if change == "missing_hash":
        expected.pop("descriptor_sha256")
    elif change == "descriptor_hash":
        expected["descriptor_sha256"] = "f" * 64
    elif change == "enrollment":
        intake["enrollment_id"] = str(uuid4())
    elif change == "foreign_scope":
        intake["scope"]["project_id"] = str(uuid4())
    elif change == "stored_quiescence":
        value["quiescence_stored_sha256"] = "f" * 64
    elif change == "quiescence_body":
        value["quiescence"]["graph_ledger_sha256"] = "f" * 64
    else:
        value["canonical_body"] = value["canonical_body"].replace('"entry_count":22', '"entry_count":21')
    with pytest.raises(ValueError):
        store.verify_reference(connection, intake, expected)
    assert len(calls) <= 1
