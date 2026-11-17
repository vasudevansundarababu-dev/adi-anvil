"""Pinned public report projection; private branch names never become row IDs.

Compilation prepares data only. It grants no activation, decision or spending.
"""

import hashlib
from copy import deepcopy

from anvil.dataset_export_contract import json_object
from anvil.praxis_generic_contract import canonical, digest

BASE_FILES = ("daily_performance.jsonl", "weekly_reports.jsonl", "daily_performance_detail.jsonl", "weekly_performance_detail.jsonl")
ALTERNATIVE_FILES = ("alternative_daily_performance.jsonl", "alternative_weekly_performance.jsonl",
                     "experiment_and_background_daily.jsonl", "experiment_and_background_weekly.jsonl")


def _read(path, files, pins):
    raw = files.get(path)
    if (type(raw) is not bytes or not 0 < len(raw) <= 1048576
            or hashlib.sha256(raw).hexdigest() != pins.get(path)):
        raise ValueError("Exact independently pinned report bytes required")
    lines = raw.splitlines()
    if not 1 <= len(lines) <= 2000 or any(not line.strip() for line in lines):
        raise ValueError("Bounded explicit report rows required")
    return [json_object(line) for line in lines]


def _key(row, grain, detail):
    required = ("locale", "channel", "date" if grain == "daily" else "week")
    if detail:
        required += ("keyword_id", "creative_version_id", "experiment_id", "arm")
    if any(name not in row for name in required):
        raise ValueError("Explicit semantic report scope required")
    return {name: row[name] for name in required}


def _project(case_id, row, grain, detail):
    value = deepcopy(row)
    identity = {"case_id": case_id, "grain": grain, "detail": detail, **_key(row, grain, detail)}
    if detail:
        # Source detail IDs contain positive/null/negative: do not forward them.
        value["id"] = case_id + ":report:" + digest(identity)
    elif "id" not in value:
        raise ValueError("Aggregate report must retain its original source identity")
    value["report_grain"] = grain
    value["report_detail"] = detail
    return value


def _indexed(rows, grain, detail):
    result = {}
    for row in rows:
        key = digest(_key(row, grain, detail))
        if key in result:
            raise ValueError("Duplicate semantic report row")
        result[key] = row
    return result


def compile_reports(case_id, files, pins, *, branch):
    if case_id not in {"GT2-R01", "GT2-R02"} or branch not in {"positive", "null", "negative"}:
        raise ValueError("Exact case and private host-selected branch required")
    baseline, selected, provenance = [], [], {}
    for index, (base_name, alt_name) in enumerate(zip(BASE_FILES, ALTERNATIVE_FILES)):
        grain, detail = ("daily" if index % 2 == 0 else "weekly"), index >= 2
        base_path = f"cases/{case_id}/{base_name}"
        alt_path = f"reviewer_only/us-pair/{case_id}/reuse-test-{branch}/{alt_name}"
        base = _read(base_path, files, pins)
        alt = _read(alt_path, files, pins)
        provenance.update({path: pins[path] for path in (base_path, alt_path)})
        original = _indexed(base, grain, detail)
        alternative = _indexed(alt, grain, detail)
        if not detail and set(original) != set(alternative):
            raise ValueError("Alternative aggregate reports must retain complete original coverage")
        for row in base:
            baseline.append(_project(case_id, row, grain, detail))
        if detail:
            # Only the authorized test strata replace the reference schedule.
            for row in base:
                if row.get("locale") != "en-US" or row.get("channel") != "search" or row.get("week") not in (7, 8):
                    selected.append(_project(case_id, row, grain, True))
            for row in alt:
                if (row.get("case_id") != case_id or row.get("locale") != "en-US" or row.get("channel") != "search"
                        or row.get("week") not in (7, 8)):
                    raise ValueError("Alternative detail report escaped approved case/market/channel/windows")
                selected.append(_project(case_id, row, grain, True))
        else:
            for key, row in original.items():
                alternate = alternative[key]
                # Weekly alternative sources omit stable case/market/coverage
                # metadata. Retain those actual original fields, overlay only
                # values explicitly supplied by the alternative source.
                merged = {**row, **alternate}
                allowed = row.get("locale") == "en-US" and row.get("channel") == "search" and row.get("week") in (7, 8)
                if not allowed:
                    if any(v != row.get(k) for k, v in alternate.items() if k != "provenance"):
                        raise ValueError("Alternative aggregate changed an unauthorized report")
                    merged = row
                if merged["id"] != row["id"] or merged["released_at"] != row["released_at"]:
                    raise ValueError("Alternative aggregate changed identity or publication time")
                selected.append(_project(case_id, merged, grain, False))
    if len({r["id"] for r in baseline}) != len(baseline) or len({r["id"] for r in selected}) != len(selected):
        raise ValueError("Global report identities must remain distinct")
    # Outcome labels may occur in private source paths, never in public records.
    for row in selected:
        raw = canonical(row)
        if any(label in raw for label in (b"_positive_", b"_negative_", b"_null_", b"reuse-test-")):
            raise ValueError("Private outcome label in public report")
    return {"schema_version": "anvil.marketing-private-report-transition.v1", "case_id": case_id,
            "branch": branch, "source_provenance": provenance, "baseline": baseline, "selected": selected}
