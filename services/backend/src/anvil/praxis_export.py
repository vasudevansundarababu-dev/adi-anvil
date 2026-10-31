"""File handoff preserves exact source bytes and unverified lineage metadata."""

import hashlib
from typing import Literal

from pydantic import Field

from anvil.praxis_contract import Model, Text
from anvil.task_parser import json_value


class Source(Model):
    record_id: Text
    record_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    project_id: Text
    client_id: Text
    submission_time: Text
    reviewer_id: Text | None
    review_decision_time: Text | None


class Export(Model):
    schema_version: Literal["praxis.anvil.export.v1"]
    source: Source
    payload_json: str = Field(min_length=1, max_length=1048576)
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def parse_export(raw):
    value = json_value(raw)
    if not isinstance(value, dict) or value.get("schema_version") != "praxis.anvil.export.v1":
        return raw, None
    envelope = Export.model_validate(value)
    payload = envelope.payload_json.encode("utf-8")
    if hashlib.sha256(payload).hexdigest() != envelope.payload_sha256:
        raise ValueError("Export payload_sha256 does not match exact payload_json bytes")
    return payload, envelope
