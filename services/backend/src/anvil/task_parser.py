"""Bounded, deterministic text parsing. Never executes cells, templates or URLs."""

import csv
import io
import json
from collections import defaultdict

from anvil.db import digest

FIELDS = (
    "schema_version",
    "external_id",
    "title",
    "instruction",
    "input",
    "reference",
    "metadata",
    "metadata.domain",
    "metadata.difficulty",
    "metadata.locale",
    "metadata.tags",
)
MAX_BYTES = 25 * 1024 * 1024
MAX_ROWS = 10000
EXTRACTION_VERSION = "task-text-v1"


def json_value(value):
    def pairs(items):
        out = {}
        for key, item in items:
            if key in out:
                raise ValueError("Duplicate JSON key")
            out[key] = item
        return out

    def invalid(_):
        raise ValueError("Non-finite JSON number")

    result = json.loads(value, object_pairs_hook=pairs, parse_constant=invalid)

    # Bound nesting even for syntactically valid payloads before storing/rendering them.
    def check(item, depth=0):
        if depth > 32:
            raise ValueError("JSON exceeds 32 levels")
        if isinstance(item, dict):
            for key, child in item.items():
                check(key, depth + 1)
                check(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                check(child, depth + 1)
        elif isinstance(item, float):
            import math

            if not math.isfinite(item):
                raise ValueError("Non-finite number")
        elif isinstance(item, str):
            if "\x00" in item:
                raise ValueError("NUL values are unsupported")
            item.encode("utf-8")

    check(result)
    return result


def parse(data, filename, mapping):
    errors, rows, columns = [], [], []

    def error(row, field, code, message):
        errors.append({"row": row, "field": field, "code": code, "message": message})

    if len(data) > MAX_BYTES:
        raise ValueError("File exceeds 25 MiB")
    extension = filename.rsplit(".", 1)[-1].lower()
    if extension not in ("csv", "jsonl"):
        raise ValueError("Use a .csv or .jsonl file")
    try:
        source = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        error(0, "file", "INVALID_TYPE", "Use UTF-8 text")
        source = ""
    if "\x00" in source:
        error(0, "file", "INVALID_TYPE", "NUL bytes are not supported")
        source = ""
    if extension == "jsonl":
        for number, line in enumerate(source.splitlines(), 1):
            if not line.strip():
                continue
            if len(rows) == MAX_ROWS:
                error(number, "file", "INVALID_TYPE", "Maximum 10,000 tasks per import")
                break
            try:
                row = json_value(line)
                if not isinstance(row, dict):
                    error(number, "row", "INVALID_TYPE", "Each line must be a JSON object")
                    row = {}
                columns.extend(k for k in row if k not in columns)
            except (ValueError, RecursionError, UnicodeError):
                error(number, "row", "INVALID_JSON", "Malformed JSON object")
                row = {}
            rows.append((number, row))
    else:
        # csv's process-global field limit stays bounded; no per-request mutation.
        try:
            reader = csv.reader(io.StringIO(source, newline=""), strict=True)
            columns = next(reader, [])
            if len(set(columns)) != len(columns) or any(not c for c in columns):
                error(1, "header", "INVALID_TYPE", "CSV headers must be nonempty and unique")
            for values in reader:
                if not values:
                    continue
                if len(rows) == MAX_ROWS:
                    error(
                        reader.line_num, "file", "INVALID_TYPE", "Maximum 10,000 tasks per import"
                    )
                    break
                if len(values) != len(columns):
                    error(
                        reader.line_num, "row", "INVALID_TYPE", "Cell count must match the header"
                    )
                rows.append((reader.line_num, dict(zip(columns, values))))
        except csv.Error:
            error(reader.line_num, "row", "INVALID_TYPE", "Malformed CSV or cell exceeds 128 KiB")
    if not rows:
        error(0, "file", "REQUIRED", "Supply at least one task")
    for field, column in mapping.items():
        if field not in FIELDS or not isinstance(column, str) or column not in columns:
            error(0, field, "REQUIRED", "Select an existing source column")
    if extension == "csv":
        for field in ("external_id", "instruction", "input"):
            if not mapping.get(field):
                error(0, field, "REQUIRED", "CSV requires an explicit column mapping")
    normalized, ids = [], defaultdict(list)
    for number, raw in rows:
        spec = {}
        for field in FIELDS:
            key = mapping.get(field, field if extension == "jsonl" else None)
            if key is None or key not in raw:
                continue
            value = raw[key]
            if (
                extension == "csv"
                and value == ""
                and field not in ("external_id", "instruction", "input")
            ):
                continue
            if extension == "csv" and field in ("input", "reference", "metadata", "metadata.tags"):
                try:
                    value = json_value(value)
                except (ValueError, RecursionError, UnicodeError):
                    error(number, field, "INVALID_JSON", "Cell must contain valid JSON")
                    continue
            if field.startswith("metadata."):
                if not isinstance(spec.get("metadata", {}), dict):
                    error(number, "metadata", "INVALID_TYPE", "Metadata must be an object")
                    spec["metadata"] = {}
                spec.setdefault("metadata", {})[field.split(".")[1]] = value
            else:
                spec[field] = value
        if extension == "csv" and "schema_version" not in spec:
            spec["schema_version"] = "1.0"
        for field in ("schema_version", "external_id", "instruction", "input"):
            if field not in spec or spec[field] is None or spec[field] == "":
                error(number, field, "REQUIRED", "Required field is missing")
        if "schema_version" in spec and spec["schema_version"] != "1.0":
            error(
                number, "schema_version", "UNSUPPORTED_SCHEMA_VERSION", "Supported version is 1.0"
            )
        for field in ("external_id", "instruction", "title"):
            if field in spec and (not isinstance(spec[field], str) or not spec[field].strip()):
                error(number, field, "INVALID_TYPE", "Expected nonempty text")
        for field in ("input", "reference", "metadata"):
            if field in spec and not isinstance(spec[field], dict):
                error(number, field, "INVALID_TYPE", "Expected a JSON object")
        metadata = spec.get("metadata", {})
        if isinstance(metadata, dict):
            for field in metadata:
                if field not in ("domain", "difficulty", "locale", "tags"):
                    error(number, "metadata." + field, "INVALID_TYPE", "Unsupported metadata field")
                elif field == "tags":
                    if not isinstance(metadata[field], list) or any(
                        not isinstance(t, str) for t in metadata[field]
                    ):
                        error(
                            number, "metadata.tags", "INVALID_TYPE", "Expected an array of strings"
                        )
                elif not isinstance(metadata[field], str):
                    error(number, "metadata." + field, "INVALID_TYPE", "Expected text")
        if isinstance(spec.get("external_id"), str):
            ids[spec["external_id"]].append(number)
        normalized.append({"row": number, "spec": spec})
    duplicate_rows = set()
    for numbers in ids.values():
        if len(numbers) > 1:
            for number in numbers:
                duplicate_rows.add(number)
                error(
                    number,
                    "external_id",
                    "DUPLICATE_EXTERNAL_ID",
                    "External ID appears on multiple rows",
                )
    invalid = {e["row"] for e in errors if e["row"] > 0}
    invalid_count = (
        len(rows) if any(e["row"] == 0 for e in errors) else sum(n in invalid for n, _ in rows)
    )
    return {
        "extraction_version": EXTRACTION_VERSION,
        "columns": columns,
        "errors": errors,
        "normalized": normalized,
        "normalized_sha256": digest(normalized),
        "counts": {
            "received": len(rows),
            "valid": len(rows) - invalid_count,
            "invalid": invalid_count,
            "duplicates": len(duplicate_rows),
        },
    }
