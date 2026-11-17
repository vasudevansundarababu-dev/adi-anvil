"""Private, source-pinned as-of campaign accounting, never model estimates.

The experiment reservation is capacity inside existing daily media orders.
Component settlement events must not be added to the parent ledger again.
This module performs no persistence, provider calls or qualification.
"""

import hashlib
from copy import deepcopy
from datetime import timedelta

from anvil.dataset_export_contract import json_object
from anvil.marketing_task2_runtime import timestamp
from anvil.praxis_generic_contract import digest

FILES = ("commitments.json", "ledger.jsonl", "budget_envelopes.json", "budget_snapshots.json", "accounting_contract.json")
SCHEMA = "anvil.marketing-private-finance-book.v1"


def _minor(value):
    if type(value) is not int or value < 0:
        raise ValueError("Nonnegative integer USD minor units required")
    return value


def _unique(rows):
    if type(rows) is not list or not 1 <= len(rows) <= 2000:
        raise ValueError("Bounded nonempty financial record set required")
    indexed = {}
    for row in rows:
        if type(row) is not dict or type(row.get("id")) is not str or not 1 <= len(row["id"]) <= 200:
            raise ValueError("Exact financial record identifier required")
        if row["id"] in indexed:
            raise ValueError("Duplicate financial record identifier")
        indexed[row["id"]] = row
    return indexed


def position(book, instant):
    """No future orders, settlements or planned envelopes become obligations."""
    now = timestamp(instant)
    orders = {r["id"]: r for r in book["commitments"]
              if timestamp(r["created_at"]) <= now and timestamp(r["released_at"]) <= now}
    settled = {}
    for row in book["ledger"]:
        if timestamp(row["recorded_at"]) <= now and timestamp(row["released_at"]) <= now:
            if row["commitment_id"] not in orders:
                raise ValueError("Settlement precedes an available binding order")
            settled[row["commitment_id"]] = row["amount_minor"]
    actual = sum(settled.values())
    outstanding = sum(row["committed_minor"] - settled.get(key, 0) for key, row in orders.items())
    reserved = 0
    for event in book.get("reservation_events", []):
        if timestamp(event["at"]) <= now:
            if event["type"] == "RESERVE":
                reserved += event["amount_usd_minor"]
            elif event["type"] in {"RESERVATION_TO_COMMITMENT", "RELEASE_UNUSED_RESERVATION"}:
                reserved -= event["amount_usd_minor"]
    free = book["ceiling"] - actual - outstanding - reserved - book["locked_contingency"]
    if min(actual, outstanding, free) < 0:
        raise ValueError("Campaign authority or locked contingency exceeded")
    return {"settled": actual, "committed": outstanding, "reserved": reserved,
            "spendable_before_reservations": free,
            "locked_contingency": book["locked_contingency"], "as_of": instant}


def normalize(case_id, files, expected_hashes, *, branch=None):
    """Caller must supply the independently qualified inventory, not actor pins."""
    if case_id not in {"GT2-R01", "GT2-R02"}:
        raise ValueError("Exact approved US-pair case required")
    if branch is not None and branch not in {"positive", "null", "negative"}:
        raise ValueError("Host-selected private branch required")
    prefix = f"cases/{case_id}" if branch is None else f"reviewer_only/us-pair/{case_id}/reuse-test-{branch}"
    values, provenance = {}, {}
    for name in (*FILES, *(("reservation_lifecycle.json",) if branch is not None else ())):
        path = f"{prefix}/{name}"
        raw = files.get(path)
        if (type(raw) is not bytes or not 0 < len(raw) <= 1048576
                or hashlib.sha256(raw).hexdigest() != expected_hashes.get(path)):
            raise ValueError("Missing or changed independently pinned finance source")
        if name.endswith("jsonl"):
            lines = raw.splitlines()
            if not lines or len(lines) > 2000 or any(not line.strip() for line in lines):
                raise ValueError("Bounded explicit ledger rows required")
            value = [json_object(line) for line in lines]
        else:
            value = json_object(b'{"value":' + raw + b'}')["value"]
        values[name] = value
        provenance[path] = {"sha256": expected_hashes[path], "bytes": len(raw)}
    orders = _unique(values["commitments.json"])
    ledger = _unique(values["ledger.jsonl"])
    envelopes = _unique(values["budget_envelopes.json"])
    snapshots = _unique(values["budget_snapshots.json"])
    contract = values["accounting_contract.json"]
    if (contract.get("budget_ceiling_usd_minor") != 20000000
            or contract.get("media_ceiling_usd_minor") != 13000000
            or contract.get("planned_envelope_is_not_binding") is not True
            or contract.get("data_only") is not True):
        raise ValueError("Approved campaign accounting contract required")
    costs, paid = set(), set()
    for row in orders.values():
        if row.get("currency") != "USD" or _minor(row["committed_minor"]) == 0:
            raise ValueError("Positive USD binding order required")
        if timestamp(row["released_at"]) != timestamp(row["created_at"]) or timestamp(row["settled_at"]) <= timestamp(row["created_at"]):
            raise ValueError("Exact available order and later settlement required")
        if "cost_id" in row:
            if row["cost_id"] in costs:
                raise ValueError("Global production/localisation/measurement cost counted twice")
            costs.add(row["cost_id"])
    for row in ledger.values():
        order = orders.get(row.get("commitment_id"))
        if (order is None or row["commitment_id"] in paid or row.get("type") != "SETTLEMENT"
                or row.get("currency") != "USD" or row.get("category") != order["category"]
                or _minor(row["amount_minor"]) != order["committed_minor"]
                or timestamp(row["recorded_at"]) != timestamp(order["settled_at"])
                or timestamp(row["released_at"]) != timestamp(row["recorded_at"])):
            raise ValueError("One exact parent settlement per binding order required")
        paid.add(row["commitment_id"])
    if paid != set(orders):
        raise ValueError("Complete parent-order settlement schedule required")
    for row in envelopes.values():
        if (row.get("currency") != "USD" or row.get("financial_state") != "AUTHORISATION_NOT_COMMITMENT"
                or type(row.get("week")) is not int or not 1 <= row["week"] <= 12):
            raise ValueError("Original weekly planning envelope required")
        _minor(row["planned_cap_minor"])
    if sum(r["planned_cap_minor"] for r in envelopes.values()) != 13000000:
        raise ValueError("Original media planning envelope total differs")
    book = {"schema_version": SCHEMA, "case_id": case_id, "source_provenance": provenance,
            "ceiling": 20000000, "locked_contingency": 1500000,
            "commitments": deepcopy(list(orders.values())), "ledger": deepcopy(list(ledger.values())),
            "envelopes": deepcopy(list(envelopes.values()))}
    if branch is not None:
        events = values["reservation_lifecycle.json"]
        _validate_components(case_id, orders, events)
        book["reservation_events"] = deepcopy(events)
    for row in snapshots.values():
        actual = position(book, row["as_of"])
        expected = {"actual_settled_usd_minor": actual["settled"],
                    "binding_outstanding_usd_minor": actual["committed"],
                    "media_remaining_authorisable_usd_minor": actual["spendable_before_reservations"],
                    "campaign_authority_usd_minor": book["ceiling"],
                    "contingency_locked_usd_minor": book["locked_contingency"],
                    "active_reservations_usd_minor": actual["reserved"]}
        if any(type(row.get(k)) is not int or row[k] != v for k, v in expected.items()):
            raise ValueError("As-of reference snapshot disagrees with original parent accounting")
    return book


def _validate_components(case_id, orders, events):
    """All component costs must be inside exact parent orders and settlements."""
    _unique(events)
    if len(events) != 30 or events[0]["type"] != "RESERVE" or events[-1]["type"] != "RELEASE_UNUSED_RESERVATION":
        raise ValueError("Complete bounded experiment reservation lifecycle required")
    reserve = events[0]
    approval = case_id + "_conditional_reuse_campaign_approval"
    if (_minor(reserve["amount_usd_minor"]) != 200000 or reserve.get("approval_ref") != approval
            or reserve.get("not_actual_cost") is not True or reserve.get("scope") != "US Search weeks7-8"):
        raise ValueError("Exact conditional experiment reservation required")
    parents = {timestamp(r["created_at"]): r for r in orders.values()
               if r.get("locale") == "en-US" and r.get("channel") == "search" and r.get("week") in (7, 8)}
    if len(parents) != 14 or timestamp(reserve["at"]) >= min(parents):
        raise ValueError("Reservation must precede all fourteen parent daily orders")
    converted, settled = {}, {}
    previous = timestamp(reserve["at"])
    for event in events[1:-1]:
        at, amount = timestamp(event["at"]), _minor(event["amount_usd_minor"])
        if at < previous or amount == 0:
            raise ValueError("Positive chronological component events required")
        previous = at
        if event["type"] == "RESERVATION_TO_COMMITMENT":
            parent = parents.get(at)
            if (at in converted or parent is None or amount > parent["committed_minor"]
                    or parent.get("additional_campaign_approval_ref") != approval
                    or event.get("not_additional_to_parent_order") is not True):
                raise ValueError("Component conversion must be inside its exact approved parent order")
            converted[at] = amount
        elif event["type"] == "SETTLE_COMPONENT_OF_PARENT_ORDER":
            start = at - timedelta(days=1)
            if (start not in converted or start in settled or converted[start] != amount
                    or timestamp(parents[start]["settled_at"]) != at
                    or event.get("not_additional_to_parent_ledger") is not True):
                raise ValueError("Component settlement must match the parent ledger, never add another cost")
            settled[start] = amount
        else:
            raise ValueError("Unrecognized component event cannot become spend")
    release = events[-1]
    if (set(converted) != set(parents) or settled != converted or timestamp(release["at"]) < previous
            or release.get("not_refund_or_actual_cost") is not True
            or _minor(release["amount_usd_minor"]) + sum(converted.values()) != 200000):
        raise ValueError("Converted components plus unused release must conserve the original reservation")


def reservation_capacity(book, instant, amount, *, existing_reserved=0):
    """Pre-start test capacity is carved from the original US Search caps."""
    _minor(amount)
    _minor(existing_reserved)
    current = position(book, instant)
    caps = [r for r in book["envelopes"] if r.get("locale") == "en-US"
            and r.get("channel") == "search" and r["week"] in (7, 8)]
    if (amount <= 0 or len(caps) != 2 or amount > sum(r["planned_cap_minor"] for r in caps)
            or amount + existing_reserved > current["spendable_before_reservations"]):
        raise ValueError("Reservation exceeds existing scope capacity or spends locked contingency")
    future = [r for r in book["commitments"] if r.get("locale") == "en-US"
              and r.get("channel") == "search" and r.get("week") in (7, 8)
              and timestamp(r["created_at"]) <= timestamp(instant)]
    if future:
        raise ValueError("Experiment approval would follow its first binding daily order")
    return {**current, "reserved": amount, "additional_media_budget": 0,
            "parent_order_components_not_additional_costs": True,
            "finance_book_sha256": digest(book)}
