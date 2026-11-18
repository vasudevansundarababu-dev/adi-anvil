"""Explicit v2 prompt receipts over an unchanged durable tool transcript.

Only older verified chunk text is replaced; ordinary observations and ordering
remain intact. This is not a summary or proof of reading/comprehension.
"""
import hashlib
import re
from copy import deepcopy

import rfc8785

from anvil.golden_kyc_policy_chunks import (
    CHUNK_SCHEMA,
    PAGE_SCHEMA,
    PROTOCOL,
    ROOT_SCHEMA,
    validate_document,
)

VERSION = "anvil.kyc-policy-observation-projection.v1"
RECEIPT_SCHEMA = "anvil.policy-source-chunk-receipt.v2"
RECENT_CHUNKS = 1
NOTICE = (
    "Earlier policy chunks and manifest pages are represented by immutable document/hash/range receipts. "
    "The complete original sources and full tool transcript are retained. "
    "Use document.read with the same document_id to read any chunk again. "
    "A receipt is not source text, a summary, proof of comprehension or a full-source reading claim."
)


def project(observations, *, application_id):
    """Return a copy and explicit protocol marker; never modify durable data."""
    if type(observations) is not list:
        raise ValueError("Exact ordered tool transcript required")
    bindings, chunks = set(), []
    for turn, observation in enumerate(observations):
        if type(observation) is not dict or type(observation.get("actions")) is not list:
            continue
        for index, action in enumerate(observation["actions"]):
            if type(action) is not dict or type(action.get("result")) is not dict:
                continue
            result = action["result"]
            if result.get("status") != "completed" or type(result.get("result")) is not dict:
                continue
            payload = result["result"]
            if action.get("operation") == "policy.read" and payload.get("schema_version") == ROOT_SCHEMA:
                protocol = payload.get("policy_documents", {})
                binding = protocol.get("policy_binding_sha256") if type(protocol) is dict else None
                if (type(protocol) is not dict or protocol.get("protocol") != PROTOCOL
                        or payload.get("application_id") != application_id
                        or type(binding) is not str or not re.fullmatch("[a-f0-9]{64}", binding)):
                    raise ValueError("Exact current policy document protocol required")
                bindings.add(binding)
            elif action.get("operation") == "document.read" and payload.get("schema_version") in (CHUNK_SCHEMA, PAGE_SCHEMA):
                validate_document(payload)
                if (payload.get("application_id") != application_id
                        or payload["policy_binding_sha256"] not in bindings):
                    raise ValueError("Policy chunk transcript scope changed or was not declared")
                chunks.append((turn, index, payload))
    if not bindings:
        return deepcopy(observations), None
    if len(bindings) != 1:
        raise ValueError("One immutable policy binding per transcript required")
    result = deepcopy(observations)
    for turn, index, document in chunks[:-RECENT_CHUNKS]:
        receipt = {"policy_document_receipt_v2": [document["document_id"], document["document_sha256"],
                   document.get("utf8_byte_start"), document.get("utf8_byte_end")]}
        result[turn]["actions"][index]["result"]["result"] = receipt
    marker = {"schema_version": VERSION, "policy_document_protocol": PROTOCOL,
              "receipt_schema_version": RECEIPT_SCHEMA,
              "receipt_columns": ["document_id", "document_sha256", "utf8_byte_start", "utf8_byte_end"],
              "manifest_receipt_range": None, "reread_tool": "document.read",
              "policy_binding_sha256": next(iter(bindings)), "recent_chunks_with_text": RECENT_CHUNKS,
              "full_transcript_sha256": hashlib.sha256(rfc8785.dumps(observations)).hexdigest(),
              "older_policy_document_count": max(0, len(chunks) - RECENT_CHUNKS), "notice": NOTICE}
    return result, marker
