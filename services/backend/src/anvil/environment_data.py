"""Bounded CSV mapping into a new materialized hybrid reference pack.

Input bytes and declarations are retained; declarations are not reviewed data rights.
No URL fetch, policy extraction, code, formulas or automatic schema inference execution.
"""

import copy
import csv
import hashlib
import io
import json
from decimal import Decimal

from anvil import environment_seeds as seeds


def import_csv(
    template, scenario, seed, collection, text, mapping, source_name, usage_basis, base_pack=None
):
    if not isinstance(text, str) or not 1 <= len(text.encode()) <= 262144 or "\x00" in text:
        raise ValueError("CSV source must be UTF-8 text up to 256 KiB")
    if not 1 <= len(source_name) <= 120 or not 10 <= len(usage_basis) <= 2000:
        raise ValueError("Source name and declared usage basis required")
    pack = (
        copy.deepcopy(base_pack)
        if base_pack is not None
        else seeds.generate(template, scenario, seed)
    )
    seeds.validate(pack)
    if (pack["template"], pack["scenario"], pack["seed"]) != (template, scenario, seed):
        raise ValueError("Base pack does not match selected template/scenario/seed")
    if collection not in pack["records"]:
        raise ValueError("Collection is not in the selected component schema")
    # Infer only the fixed reference implementation's field contract, never a
    # supplied document's executable semantics. Empty write tables are excluded.
    examples = [
        r
        for s in seeds.CATALOG[template]["scenarios"]
        for r in seeds.generate(template, s, seed)["records"][collection]
    ]
    if not examples:
        raise ValueError("Initial data import is not supported for this runtime-output collection")
    fields = set(examples[0])
    if (
        not isinstance(mapping, dict)
        or set(mapping) != fields
        or any(not isinstance(v, str) for v in mapping.values())
    ):
        raise ValueError("Map every target field to one explicit source column")
    reader = csv.DictReader(io.StringIO(text))
    if (
        not reader.fieldnames
        or len(set(reader.fieldnames)) != len(reader.fieldnames)
        or not set(mapping.values()) <= set(reader.fieldnames)
    ):
        raise ValueError("Missing or duplicate CSV source columns")
    records = []
    for source in reader:
        if len(records) >= 1000 or None in source or any(v is None for v in source.values()):
            raise ValueError("CSV rows exceed bounds or have inconsistent columns")
        row = {}
        for target, column in mapping.items():
            value = source[column]
            sample = next((r[target] for r in examples if r.get(target) is not None), None)
            if value == "" and any(r.get(target) is None for r in examples):
                row[target] = None
            elif isinstance(sample, bool):
                if value not in ("true", "false"):
                    raise ValueError("Boolean fields require true or false")
                row[target] = value == "true"
            elif type(sample) is int:
                if not value.isdigit() or not 0 <= int(value) <= 1000000:
                    raise ValueError("Invalid bounded integer")
                row[target] = int(value)
            elif isinstance(sample, list):
                parsed = json.loads(value)
                if (
                    not isinstance(parsed, list)
                    or len(parsed) > 100
                    or any(not isinstance(v, str) for v in parsed)
                ):
                    raise ValueError("Array fields require a bounded JSON string array")
                row[target] = parsed
            else:
                if len(value) > 5000:
                    raise ValueError("Source cell exceeds bound")
                if target in {"amount", "share", "unit_scale", "budget", "value"} and value:
                    number = Decimal(value)
                    if not number.is_finite() or abs(number) > Decimal("1000000000000"):
                        raise ValueError("Invalid finite exact decimal")
                row[target] = value
        records.append(row)
    if not records:
        raise ValueError("CSV contains no records")
    pack["records"][collection] = records
    checksum = hashlib.sha256(text.encode()).hexdigest()
    path = f"sources/import-{checksum}.csv"
    if not any(f["path"] == path for f in pack["files"]):
        pack["files"].append(seeds.file(path, text, "text/csv"))
    pack["origin"] = "hybrid_reference"
    pack["input_sources"] = pack.get("input_sources", []) + [
        {
            "name": source_name,
            "sha256": checksum,
            "path": path,
            "usage_basis": usage_basis,
            "rights_status": "declared_unverified",
            "target_collection": collection,
            "field_mapping": mapping,
        }
    ]
    seeds.validate(pack)
    return pack
