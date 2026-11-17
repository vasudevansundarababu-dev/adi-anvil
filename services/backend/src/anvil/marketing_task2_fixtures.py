"""Trusted US fixture reader. No raw file or controller rows returned to actors."""

import hashlib
import json
from pathlib import Path

from anvil.marketing_task2_contract import CASES
from anvil.praxis_generic_contract import digest

# Explicit per-collection public columns, not a recursive remove-private blacklist.
COLUMNS = {
    "reports": {
        "week",
        "locale",
        "market",
        "channel",
        "window_start",
        "window_end",
        "coverage_status",
        "spend_usd_minor",
        "impressions",
        "outbound_clicks",
        "verified_visits",
        "engaged_visits",
        "ctr",
        "report_version",
    },
    "questions": {
        "date",
        "week",
        "market",
        "locale",
        "source",
        "question_text",
        "observed_count",
        "coverage",
        "question_origin",
        "language_status",
    },
    "campaigns": {"name", "budget_usd_minor", "actual_cost_at_start_usd_minor", "source"},
    "documents": {"source", "locale", "text"},
    "content": {
        "version",
        "locale",
        "channel",
        "format",
        "reviewed_message_scope",
        "content_bytes_present",
        "content_sha256",
        "review_scope",
        "rights_fixture",
    },
    "budget-envelopes": {
        "locale",
        "channel",
        "week",
        "currency",
        "planned_cap_minor",
        "financial_state",
    },
}
FILES = {
    "reports": "weekly_reports.jsonl",
    "questions": "daily_query_observations.jsonl",
    "campaigns": "campaigns.json",
    "documents": "notices.json",
    "content": "approved_creative_catalogue.json",
    "budget-envelopes": "budget_envelopes.json",
}


def load_us(root, case_id, expected_hashes):
    """The host supplies an approved immutable file hash map, never a candidate path.

    This projection does not activate a private alternative-world branch. Until
    that transition is qualified, only reference/HOLD records are available.
    """
    if case_id not in CASES:
        raise ValueError("US pair only")
    root = Path(root)
    records, verified = {}, {}
    for collection, filename in FILES.items():
        relative = f"cases/{case_id}/{filename}"
        file = root / relative
        if file.is_symlink() or not file.resolve().is_relative_to(root.resolve()):
            raise ValueError("Fixture path outside approved root")
        raw = file.read_bytes()
        if len(raw) > 10 * 1048576 or hashlib.sha256(raw).hexdigest() != expected_hashes.get(
            relative
        ):
            raise ValueError("Exact approved fixture hash required")
        verified[relative] = hashlib.sha256(raw).hexdigest()
        rows = (
            [json.loads(line) for line in raw.splitlines() if line]
            if filename.endswith("jsonl")
            else json.loads(raw)
        )
        if not isinstance(rows, list):
            raise ValueError("Fixture record array required")
        projected = []
        for row in rows:
            if not isinstance(row, dict) or type(row.get("released_at")) is not str:
                raise ValueError("Every public record requires an explicit release time")
            # Outcome/controller labels are never projected, even if an input adds them.
            public = {k: row[k] for k in COLUMNS[collection] if k in row}
            public["id"] = "record-" + digest({"file": relative, "id": row.get("id")})[:24]
            projected.append(
                {"actor_visible": True, "released_at": row["released_at"], "public": public}
            )
        records[collection] = projected
    return records, {
        "source_hashes": verified,
        "scope": "US reference fixtures only",
        "private_outcomes_activated": False,
        "rights_review": "pending",
        "paid_calls": False,
    }
