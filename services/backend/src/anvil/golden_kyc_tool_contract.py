"""Public native tool schemas. No trial token, scenario controls or answer key."""

from anvil.golden_kyc_data import DECISIONS, VERSION


def obj(properties=None, required=(), *, extra=False):
    return {
        "type": "object",
        "properties": properties or {},
        "required": list(required),
        "additionalProperties": extra,
    }


def text(minimum=1, maximum=2000):
    return {"type": "string", "minLength": minimum, "maxLength": maximum}


def strings(maximum=100):
    return {"type": "array", "items": text(), "maxItems": maximum}


def tools():
    integer = {"type": "integer", "minimum": 0}
    schemas = {
        "application.read": obj({"revision": integer}),
        "policy.read": obj(),
        "documents.list": obj(),
        "document.read": obj({"id": text()}, ["id"]),
        "document.compare": obj(
            {"document_ids": strings(10), "fields": strings(10)}, ["document_ids"]
        ),
        "operation.lookup": obj({"idempotency_key": text(1, 128)}, ["idempotency_key"]),
        "operation.read": obj({"id": text()}, ["id"]),
        "information.request": obj(
            {
                "party_id": text(),
                "items": strings(4),
                "reason": text(10),
                "round_key": text(1, 100),
            },
            ["party_id", "items", "reason"],
        ),
        "information.read": obj({"id": text()}, ["id"]),
        "finding.write": obj(
            {"issue": text(5), "evidence_ids": strings()}, ["issue", "evidence_ids"]
        ),
        "finding.resolve": obj(
            {"id": text(), "reason": text(10), "evidence_ids": strings()},
            ["id", "reason", "evidence_ids"],
        ),
        "specialist.refer": obj(
            {"question": text(10), "evidence_ids": strings()}, ["question", "evidence_ids"]
        ),
        "specialist.read": obj({"id": text()}, ["id"]),
        "search": obj(
            {"query": text(1, 200), "purpose": text(5, 300), "source": text()},
            ["query", "purpose", "source"],
        ),
        "search.read": obj({"resource_id": text()}, ["resource_id"]),
        "recommend": obj(
            {
                "decision": {"type": "string", "enum": list(DECISIONS)},
                "assessed_revision": integer,
                "evidence_ids": strings(),
                "party_assessments": {
                    "type": "array",
                    "items": obj(
                        {
                            "party_id": text(),
                            "role": text(),
                            "status": text(),
                            "verification_evidence_ids": strings(),
                        },
                        ["party_id", "role", "status"],
                        extra=True,
                    ),
                    "maxItems": 10,
                },
                "reason": text(10),
                "policy_bundle": {"type": "string", "const": VERSION},
                "account_type": text(),
                "outstanding_actions": strings(),
            },
            ["decision", "assessed_revision", "evidence_ids", "party_assessments", "reason", "policy_bundle"],
        ),
    }
    for name in ("identity", "document", "address", "screening", "authority"):
        schemas[name + ".check"] = obj(
            {
                "idempotency_key": text(1, 128),
                "party_id": text(),
                "document_ids": strings(10),
                "input_revision": integer,
            },
            ["idempotency_key", "party_id", "input_revision"],
        )
    from anvil.golden_kyc_paid_session import TOOLS

    return [
        {
            "id": name,
            "input_schema": schemas[name],
            # The scheduler returns the runtime's public status/result envelope.
            # Result bodies vary by operation, but are never a private SQL row.
            "output_schema": obj({"status": {"type": "string", "enum": ["completed", "denied"]}}, ["status"], extra=True),
            "error_schema": obj({"status": text()}, extra=True),
            "response_mode": "environment",
            "pending": name.endswith(".check") or name in {"operation.read", "information.read", "specialist.read"},
            "error_statuses": [429, 503] if name.endswith(".check") else [],
            "reset": "new_episode",
            "isolation": "per_episode",
        }
        for name in TOOLS
    ]
