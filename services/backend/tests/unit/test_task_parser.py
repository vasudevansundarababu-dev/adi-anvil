import csv
import io
import json

import pytest

from anvil.task_parser import parse


def row(**changes):
    return {
        "schema_version": "1.0",
        "external_id": "one",
        "instruction": "Solve it",
        "input": {"x": 1},
        **changes,
    }


def parsed(*rows):
    return parse(("\n".join(json.dumps(r) for r in rows)).encode(), "tasks.jsonl", {})


def test_valid_deterministic_and_mapping():
    result = parsed(row(reference={"answer": 1}, metadata={"tags": ["synthetic"]}))
    assert result["counts"] == {"received": 1, "valid": 1, "invalid": 0, "duplicates": 0}
    assert result == parsed(row(reference={"answer": 1}, metadata={"tags": ["synthetic"]}))
    source = io.StringIO()
    writer = csv.writer(source)
    writer.writerow(["ID", "QUESTION", "DATA", "ANSWER"])
    writer.writerow(["one", "Solve it", '{"x":1}', '{"answer":1}'])
    result = parse(
        source.getvalue().encode(),
        "mapped.csv",
        {"external_id": "ID", "instruction": "QUESTION", "input": "DATA", "reference": "ANSWER"},
    )
    assert not result["errors"]
    assert result["normalized"][0]["spec"] == row(reference={"answer": 1})


@pytest.mark.parametrize(
    "change,field,code",
    [
        ({"instruction": None}, "instruction", "REQUIRED"),
        ({"input": []}, "input", "INVALID_TYPE"),
        ({"schema_version": "2.0"}, "schema_version", "UNSUPPORTED_SCHEMA_VERSION"),
        ({"metadata": {"tags": 3}}, "metadata.tags", "INVALID_TYPE"),
    ],
)
def test_validation_codes(change, field, code):
    result = parsed(row(**change))
    assert any(e["field"] == field and e["code"] == code for e in result["errors"])
    assert result["counts"]["invalid"] == 1


def test_duplicate_reports_both_rows_and_complete_file():
    result = parsed(*[row(external_id=str(n)) for n in range(21)], row(external_id="0"))
    assert [e["row"] for e in result["errors"] if e["code"] == "DUPLICATE_EXTERNAL_ID"] == [1, 22]
    assert result["counts"]["duplicates"] == 2
    assert result["counts"]["valid"] == 20


@pytest.mark.parametrize(
    "source",
    [b"{broken}", b'{"a":NaN}', b'{"a":1,"a":2}', b"[]", b'{"a":"\\u0000"}', b'{"a":"\\ud800"}'],
)
def test_bad_json(source):
    result = parse(source, "bad.jsonl", {})
    assert result["errors"]
    assert result["counts"]["valid"] == 0


def test_bad_csv_and_nested_json():
    assert parse(b'id,q,data\n1,x,"unterminated', "x.csv", {})["errors"]
    result = parse(
        b"id,q,data\n1,x,broken",
        "x.csv",
        {"external_id": "id", "instruction": "q", "input": "data"},
    )
    assert any(e["code"] == "INVALID_JSON" and e["field"] == "input" for e in result["errors"])
    assert parse(b"id,id\n1,2", "x.csv", {})["errors"]


def test_encoding_and_size_and_empty():
    assert parse(b"\xff", "x.jsonl", {})["errors"]
    assert parse(b"", "x.jsonl", {})["errors"]
    with pytest.raises(ValueError):
        parse(b"", "x.pdf", {})
    with pytest.raises(ValueError):
        parse(b" " * (25 * 1024 * 1024 + 1), "x.jsonl", {})
