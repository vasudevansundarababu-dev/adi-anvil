"""New offline parent-accounting controls; no SQL, native or paid execution."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from anvil.marketing_world_finance import FILES, normalize, position, reservation_capacity
from anvil.praxis_generic_contract import canonical


def source(case="GT2-R01"):
    root = Path(os.environ["ANVIL_MARKETING_SOURCE_FIXTURE_ROOT"])
    raw = (root / "checksums.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "59539b978994b472495f46786cf5085eae553230d2d7a2356acb165dea9d539a"
    pins = json.loads(raw)
    files = {f"cases/{case}/{name}": (root / f"cases/{case}/{name}").read_bytes() for name in FILES}
    return files, pins


@pytest.mark.parametrize("case", ["GT2-R01", "GT2-R02"])
def test_actual_parent_book_matches_all_reference_snapshots_and_retains_contingency(case):
    files, pins = source(case)
    before = dict(files)
    book = normalize(case, files, pins)
    opening = position(book, "2027-01-04T00:00:00Z")
    assert opening["settled"] == 5500000
    assert opening["committed"] == 154768
    closeout = position(book, "2027-03-29T00:00:00Z")
    assert closeout["settled"] == 18500000 and closeout["committed"] == 0
    assert closeout["spendable_before_reservations"] == 0
    assert closeout["locked_contingency"] == 1500000
    assert files == before


def test_reservation_uses_existing_future_envelopes_without_creating_daily_orders():
    files, pins = source()
    book = normalize("GT2-R01", files, pins)
    before = canonical(book)
    result = reservation_capacity(book, "2027-02-12T12:00:00Z", 200000)
    assert result["settled"] == 11535890
    assert result["committed"] == 154762
    assert result["spendable_before_reservations"] == 6809348
    assert result["additional_media_budget"] == 0
    assert result["parent_order_components_not_additional_costs"] is True
    assert canonical(book) == before


def test_first_daily_order_is_already_too_late_for_new_experiment_authority():
    files, pins = source()
    with pytest.raises(ValueError, match="first binding daily order"):
        reservation_capacity(normalize("GT2-R01", files, pins), "2027-02-15T00:00:00Z", 200000)


def test_reservation_cannot_spend_locked_contingency_or_exceed_original_scope():
    files, pins = source()
    book = normalize("GT2-R01", files, pins)
    with pytest.raises(ValueError, match="scope capacity"):
        reservation_capacity(book, "2027-02-12T12:00:00Z", 333329)
    with pytest.raises(ValueError, match="locked contingency"):
        reservation_capacity(book, "2027-02-12T12:00:00Z", 200000, existing_reserved=6809348)
    with pytest.raises(ValueError, match="integer"):
        reservation_capacity(book, "2027-02-12T12:00:00Z", True)


def test_changed_financial_bytes_fail_independent_pin_before_accounting():
    files, pins = source()
    files["cases/GT2-R01/commitments.json"] = b"[]"
    with pytest.raises(ValueError, match="independently pinned"):
        normalize("GT2-R01", files, pins)


def test_duplicate_parent_settlement_denies_even_if_operator_supplies_matching_new_pin():
    files, pins = source()
    path = "cases/GT2-R01/ledger.jsonl"
    row = json.loads(files[path].splitlines()[0])
    row["id"] += "_duplicate"
    files[path] += canonical(row) + b"\n"
    pins[path] = hashlib.sha256(files[path]).hexdigest()
    with pytest.raises(ValueError, match="One exact parent settlement"):
        normalize("GT2-R01", files, pins)
