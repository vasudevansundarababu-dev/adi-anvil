"""Bounded, non-executing inspection of clean actor input files."""

import csv
import io
import json

MAX_BYTES = 262144
MAX_ROWS = 1000
MAX_COLUMNS = 100


def preview(data: bytes, mime: str):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Input preview requires a nonempty file up to 256 KiB")
    text = data.decode("utf-8-sig")
    if "\x00" in text:
        raise ValueError("Input contains unsupported null bytes")
    if mime in {"text/csv", "application/csv"}:
        reader = csv.DictReader(io.StringIO(text))
        fields = reader.fieldnames
        if not fields or len(fields) > MAX_COLUMNS or len(set(fields)) != len(fields):
            raise ValueError("Input needs distinct CSV columns (maximum 100)")
        rows = []
        for row in reader:
            if len(rows) >= MAX_ROWS or None in row or any(v is None for v in row.values()):
                raise ValueError("CSV exceeds 1000 rows or contains inconsistent columns")
            rows.append(row)
    elif mime == "application/json":

        def distinct_keys(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate JSON field")
                result[key] = value
            return result

        def reject_constant(value):
            raise ValueError("Non-finite JSON number")

        rows = json.loads(text, object_pairs_hook=distinct_keys, parse_constant=reject_constant)
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            raise ValueError("JSON input must be an array of at most 1000 records")
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError("Every JSON input record must be an object")
        fields = list(dict.fromkeys(key for row in rows for key in row))
        if not fields or len(fields) > MAX_COLUMNS:
            raise ValueError("Input needs 1 to 100 columns")
    else:
        raise ValueError("Input preview supports CSV and JSON record arrays")
    if not rows:
        raise ValueError("Input contains no records")

    def kind(value):
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, str):
            return "string"
        return "object" if isinstance(value, dict) else "array"

    return {
        "row_count": len(rows),
        "columns": [
            {
                "name": field,
                "types": sorted({kind(row.get(field)) for row in rows}),
                "missing_count": sum(field not in row or row[field] is None for row in rows),
            }
            for field in fields
        ],
        "rows": rows[:10],
        "preview_limit": 10,
        "sampling": None,
        "execution_ready": False,
    }
