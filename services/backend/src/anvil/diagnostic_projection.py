"""Mechanical observations from actual role-scoped outputs, never references.

Reviewed selectors locate records; they cannot supply literal expected answers.
Semantic interpretation, safety scoring and logical-effect verification retain
their separate evaluators. This module adds no official rubric points.
"""

import hashlib
import re
import sys
from importlib.metadata import version
from typing import Literal

from pydantic import Field, model_validator

from anvil.campaign_semantic_contract import bounded_json
from anvil.db import digest
from anvil.diagnostic_measures import FIELDS
from anvil.praxis_generic_contract import digest as custody_digest
from anvil.qualification_resources import qualification_path, qualification_root
from anvil.schemas import Strict

SCOPE = "mechanical_role_scoped_observed_records_not_semantic_understanding"
MISSING = object()
SUPPORTED = (
    set(FIELDS)
    - {"K.FILE", "K.COMPARE", "K.ASYNC", "M.VERSION", "M.OUTPUT"}
    - {target for target in FIELDS if target.startswith("M.ROLE.")}
)


def source_hash():
    root = qualification_root()
    return digest(
        {
            "files": {
                name: hashlib.sha256(
                    qualification_path(root, "services/backend/src/anvil/" + name).read_bytes()
                ).hexdigest()
                for name in (
                    "diagnostic_projection.py",
                    "qualification_resources.py",
                    "diagnostic_measures.py",
                    "campaign_semantic_contract.py",
                    "schemas.py",
                    "praxis_generic_contract.py",
                    "dataset_export_contract.py",
                    "db.py",
                    "marketing_task2_tools.py",
                    "marketing_task2_contract.py",
                )
            },
            "lock": hashlib.sha256(
                qualification_path(root, "services/backend/uv.lock").read_bytes()
            ).hexdigest(),
            "packages": {name: version(name) for name in ("pydantic", "rfc8785", "fastapi")},
            "python": sys.version,
        }
    )


def pointer(value, path):
    if (
        type(path) is not str
        or len(path) > 500
        or (path and not path.startswith("/"))
        or re.search(r"~(?![01])", path)
        or len(path.split("/")) > 17
    ):
        raise ValueError("Bounded JSON pointer required")
    if not path:
        return value
    for key in path.split("/")[1:]:
        key = key.replace("~1", "/").replace("~0", "~")
        if type(value) is dict and key in value:
            value = value[key]
        elif (
            type(value) is list
            and key.isascii()
            and key.isdecimal()
            and (key == "0" or not key.startswith("0"))
            and int(key) < len(value)
        ):
            value = value[int(key)]
        else:
            return MISSING
    return value


class FieldSource(Strict):
    source: Literal["payload", "metadata"] = "payload"
    pointer: str = Field(default="", max_length=500)
    kind: Literal["value", "sha256", "field_name", "record_key"] = "value"


class Projection(Strict):
    schema_version: Literal["anvil.diagnostic-observation-projection.v1"]
    target: str = Field(min_length=1, max_length=100)
    context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_kind: Literal["agent_artifact", "tool_result"]
    operations: list[str] = Field(min_length=1, max_length=50)
    records_pointer: str = Field(default="", max_length=500)
    records_mode: Literal["single", "list", "object_entries"]
    fields: dict[str, FieldSource] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def exact(self):
        if self.target not in SUPPORTED or set(self.fields) != set(FIELDS[self.target]):
            raise ValueError("Exact deterministic diagnostic fields required")
        if len(set(self.operations)) != len(self.operations) or any(
            type(value) is not str or not 1 <= len(value) <= 200 for value in self.operations
        ):
            raise ValueError("Exact unique bounded observed operations required")
        pointer({}, self.records_pointer)
        for field in self.fields.values():
            pointer({}, field.pointer)
            if field.kind == "field_name" and not field.pointer:
                raise ValueError("Observed field-name selector must name an actual field")
        return self


def normalize(target, context, reference, sources, *, complete_capture):
    """Sources must be constructed by the private grader from verified seals."""
    unavailable = {"available": False, "records": [], "invalid_record_count": 0, "scope": SCOPE}
    if complete_capture is not True:
        return unavailable | {"reason": "complete_role_scoped_capture_required"}
    if (
        not isinstance(reference, dict)
        or reference.get("status") != "reviewed"
        or reference.get("target") != target
        or reference.get("context_sha256") != digest(context)
    ):
        return unavailable | {"reason": "exact_reviewed_diagnostic_reference_required"}
    recipe = reference.get("observation_projection")
    if not isinstance(recipe, dict):
        return unavailable | {"reason": "reviewed_observation_projection_required"}
    try:
        bounded_json(recipe, 65536, max_nodes=10000)
        spec = Projection.model_validate(recipe)
        if (
            spec.target != target
            or spec.context_sha256 != digest(context)
            or spec.source_sha256 != source_hash()
        ):
            return unavailable | {"reason": "diagnostic_projection_context_or_source_changed"}
        bounded_json(sources, 16777216, max_nodes=200000)
        if type(sources) is not list or len(sources) > 10000:
            raise ValueError("Bounded complete source population required")
        if any(type(source) is not dict for source in sources):
            raise ValueError("Explicit observed source records required")
        records, invalid, evidence = [], 0, []
        for source in sources:
            if (
                source.get("role") != context["role"]
                or source.get("kind") != spec.source_kind
                or source.get("operation") not in spec.operations
            ):
                continue
            if source.get("operational_failure") is True:
                return unavailable | {"reason": "selected_tool_observation_unavailable"}
            if (
                source.get("payload_sha256") != digest(source["payload"])
                or type(source.get("evidence_ref")) is not str
                or not source["evidence_ref"]
            ):
                raise ValueError("Exact immutable observed-source custody required")
            evidence.append({"ref": source["evidence_ref"], "sha256": source["payload_sha256"]})
            if len(evidence) > 1000:
                raise ValueError("Observed source population exceeds bound; no truncation")
            values = pointer(source["payload"], spec.records_pointer)
            if values is MISSING:
                continue  # A complete observed output omitted this record population.
            if spec.records_mode == "single":
                items = [(None, values)]
            elif spec.records_mode == "list" and type(values) is list:
                items = enumerate(values)
            elif spec.records_mode == "object_entries" and type(values) is dict:
                items = values.items()
            else:
                invalid += 1
                continue
            for key, value in items:
                if len(records) + invalid >= 1000:
                    raise ValueError("Diagnostic record population exceeds bound; no truncation")
                row = {}
                for name, field in spec.fields.items():
                    origin = (
                        value
                        if field.source == "payload"
                        else {
                            "role": source["role"],
                            "operation": source["operation"],
                            "evidence_ref": source["evidence_ref"],
                        }
                    )
                    found = pointer(origin, field.pointer)
                    if field.kind == "record_key":
                        found = key if key is not None else MISSING
                    if found is MISSING:
                        break
                    if field.kind == "sha256":
                        found = digest(found)
                    elif field.kind == "field_name":
                        found = (
                            field.pointer.rsplit("/", 1)[1].replace("~1", "/").replace("~0", "~")
                        )
                    row[name] = found
                if set(row) != set(spec.fields):
                    invalid += 1
                else:
                    records.append(row)
        if len(records) + invalid > 1000:
            raise ValueError("Diagnostic record population exceeds bound")
        return {
            "available": True,
            "records": records,
            "invalid_record_count": invalid,
            "scope": SCOPE,
            "projection_sha256": digest(recipe),
            "projection_source_sha256": spec.source_sha256,
            "observed_source_refs": evidence,
        }
    except (ValueError, TypeError, KeyError, RecursionError):
        return unavailable | {"reason": "diagnostic_projection_or_capture_invalid"}


def observation(role, kind, operation, payload, evidence_ref):
    return {
        "role": role,
        "kind": kind,
        "operation": operation,
        "payload": payload,
        "payload_sha256": digest(payload),
        "evidence_ref": evidence_ref,
    }


def kyc_sources(state, events):
    """Only actual actor calls and its committed recommendation, not world facts."""
    sources = []
    final = state.get("final")
    for event in events:
        record = event["record"]
        if record.get("status") != "completed":
            failed = observation(
                "kyc_analyst",
                "tool_result",
                event["action"],
                record.get("result", {}),
                "banking-event:" + str(event["sequence"]),
            )
            failed["operational_failure"] = True
            sources.append(failed)
            continue
        ref = "banking-event:" + str(event["sequence"])
        sources.append(
            observation("kyc_analyst", "tool_result", event["action"], record["result"], ref)
        )
        if (
            event["action"] == "recommend"
            and isinstance(final, dict)
            and record.get("arguments_sha256") == digest(final)
            and isinstance(record["result"], dict)
            and record["result"].get("submitted") is True
        ):
            sources.append(observation("kyc_analyst", "agent_artifact", "recommend", final, ref))
    return sources


def kyc_role_complete(state, events):
    """Closure is a committed actor recommendation, not merely a sealed trial."""
    final = state.get("final")
    return isinstance(final, dict) and any(
        event["action"] == "recommend"
        and event["record"].get("status") == "completed"
        and event["record"].get("arguments_sha256") == digest(final)
        and isinstance(event["record"].get("result"), dict)
        and event["record"]["result"].get("submitted") is True
        for event in events
    )


def campaign_sources(capture, receipts):
    """SQL-verified tool returns and role-created objects; no private fixtures."""
    from anvil.marketing_task2_contract import ROLES, WIRE_ROLES
    from anvil.marketing_task2_tools import WRITES

    sources = []
    for receipt in receipts:
        if (
            custody_digest(receipt["result"]) != receipt["result_sha256"]
            or receipt["role"] not in WIRE_ROLES
        ):
            raise ValueError("Exact immutable Marketing role/tool receipt required")
        item = observation(
            WIRE_ROLES[receipt["role"]],
            "tool_result",
            receipt["operation"],
            receipt["result"],
            "marketing-tool:" + str(receipt["id"]),
        )
        item["operational_failure"] = receipt["result"].get("status") == "unavailable"
        sources.append(item)
        envelope = receipt["result"].get("result", {})
        value = envelope.get("record") if isinstance(envelope, dict) else None
        if receipt["operation"] not in WRITES or not isinstance(value, dict):
            continue
        role = value.get("created_by_role")
        if (
            role in ROLES
            and role == WIRE_ROLES[receipt["role"]]
            and value.get("kind") == WRITES[receipt["operation"]]
            and custody_digest(value) == envelope.get("record_sha256")
            and capture.get("objects", {}).get(value.get("id")) == value
        ):
            # Initial fixtures, obsolete revisions and reads of someone else's
            # artifact cannot become evidence that this agent authored it.
            sources.append(
                observation(
                    role,
                    "agent_artifact",
                    value["kind"],
                    value,
                    "marketing-tool:" + str(receipt["id"]),
                )
            )
    return sources
