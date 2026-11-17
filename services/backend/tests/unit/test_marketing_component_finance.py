"""New offline component-conservation controls over all six real branches."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from anvil.marketing_world_finance import FILES, normalize, position
from anvil.praxis_generic_contract import canonical


def source(case="GT2-R01", branch="positive"):
    root = Path(os.environ["ANVIL_MARKETING_SOURCE_FIXTURE_ROOT"])
    raw = (root / "checksums.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "59539b978994b472495f46786cf5085eae553230d2d7a2356acb165dea9d539a"
    pins = json.loads(raw)
    prefix = f"reviewer_only/us-pair/{case}/reuse-test-{branch}"
    files = {f"{prefix}/{name}": (root / f"{prefix}/{name}").read_bytes()
             for name in (*FILES, "reservation_lifecycle.json")}
    return files, pins, prefix


@pytest.mark.parametrize("case", ["GT2-R01", "GT2-R02"])
@pytest.mark.parametrize("branch", ["positive", "null", "negative"])
def test_all_source_branch_snapshots_reconcile_without_double_charging_components(case, branch):
    files, pins, prefix = source(case, branch)
    book = normalize(case, files, pins, branch=branch)
    request = position(book, "2027-02-12T12:00:00Z")
    assert request["settled"] == 11535890
    assert request["reserved"] == 200000
    assert request["spendable_before_reservations"] == 6609348
    closed = position(book, "2027-03-29T00:00:00Z")
    ledger = [json.loads(line) for line in files[prefix + "/ledger.jsonl"].splitlines()]
    assert closed["settled"] == sum(r["amount_minor"] for r in ledger)
    assert closed["reserved"] == closed["committed"] == 0
    lifecycle = book["reservation_events"]
    converted = sum(r["amount_usd_minor"] for r in lifecycle if r["type"] == "RESERVATION_TO_COMMITMENT")
    assert converted + lifecycle[-1]["amount_usd_minor"] == 200000
    assert closed["settled"] < sum(r["amount_minor"] for r in ledger) + converted


def test_first_component_reduces_reservation_but_parent_alone_becomes_outstanding():
    files, pins, _ = source()
    book = normalize("GT2-R01", files, pins, branch="positive")
    current = position(book, "2027-02-15T00:00:00Z")
    assert current["reserved"] == 200000 - 12450
    parents = [r for r in book["commitments"] if r["created_at"] == "2027-02-15T00:00:00Z"]
    assert current["committed"] == sum(r["committed_minor"] for r in parents)


@pytest.mark.parametrize("change", ["second_cost", "mismatched_settlement", "lost_unused_cap"])
def test_component_tampering_denies_even_with_a_new_operator_hash(change):
    files, pins, prefix = source()
    path = prefix + "/reservation_lifecycle.json"
    events = json.loads(files[path])
    if change == "second_cost":
        events[1]["not_additional_to_parent_order"] = False
    elif change == "mismatched_settlement":
        events[2]["amount_usd_minor"] += 1
    else:
        events[-1]["amount_usd_minor"] -= 1
    files[path] = canonical(events)
    pins[path] = hashlib.sha256(files[path]).hexdigest()
    with pytest.raises(ValueError):
        normalize("GT2-R01", files, pins, branch="positive")
