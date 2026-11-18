"""Reconstruct only complete actually delivered v2 public policy sources."""

import hashlib

from anvil.golden_kyc_policy_chunks import CHUNK_SCHEMA, PAGE_SCHEMA, ROOT_SCHEMA, lookup
from anvil.praxis_generic_contract import digest

FIELDS = ("schema_version", "application_id", "product", "governing_state", "charter_profile",
          "policy_set_sha256", "qualification_id", "materialization_id", "legal_acceptance",
          "state_applicability", "state_applicability_rationale")


def delivered_state_rules(events, *, application_id=None):
    """Missing pages/chunks or mixed bindings never count as delivered law."""
    roots, documents = [], {}
    for event in events:
        record = event.get("record", {})
        value = record.get("result")
        if record.get("status") != "completed" or type(value) is not dict:
            continue
        if (event.get("action") == "policy.read" and value.get("schema_version") == ROOT_SCHEMA
                and (application_id is None or value.get("application_id") == application_id)):
            roots.append(value)
        elif event.get("action") == "document.read" and value.get("schema_version") in (PAGE_SCHEMA, CHUNK_SCHEMA):
            identifier = value.get("document_id")
            if type(identifier) is str:
                if identifier in documents and documents[identifier] != value:
                    return []
                documents[identifier] = value
    for root in reversed(roots):
        try:
            return _complete(root, documents)
        except (ValueError, TypeError, KeyError):
            continue
    return []


def _complete(root, documents):
    index = root["policy_documents"]
    binding = index["policy_binding_sha256"]
    count = index["manifest_page_count"]
    if type(count) is not int or not 1 <= count <= 1000:
        raise ValueError("Bounded complete manifest required")
    pages, entries, identifier = [], [], index["root_manifest_id"]
    for _ in range(count):
        page = lookup(documents, identifier)
        if page["schema_version"] != PAGE_SCHEMA or page["policy_binding_sha256"] != binding:
            raise ValueError("Exact manifest binding required")
        pages.append(page)
        entries.extend(page["entries"])
        identifier = page["next_document_id"]
    if identifier is not None or digest(pages) != index["manifest_sha256"]:
        raise ValueError("Complete ordered manifest required")
    source_headers = [entry for entry in entries if entry.get("kind") == "source"]
    chunk_headers = [entry for entry in entries if entry.get("kind") == "chunk"]
    if len(source_headers) != index["source_count"] or len(chunk_headers) != index["chunk_count"]:
        raise ValueError("Complete source and chunk membership required")
    groups = {"bound_common_rules": [], "bound_state_rules": []}
    total = 0
    for ordinal, source in enumerate(source_headers):
        if source["source_ordinal"] != ordinal or source["group"] not in groups:
            raise ValueError("Exact original source ordering required")
        headers = [entry for entry in chunk_headers if entry["source_ordinal"] == ordinal]
        if len(headers) != source["chunk_count"]:
            raise ValueError("Every original source chunk must be read")
        chunks, end = [], 0
        for number, header in enumerate(headers):
            chunk = lookup(documents, header["document_id"])
            if (chunk["schema_version"] != CHUNK_SCHEMA or chunk["policy_binding_sha256"] != binding
                    or chunk["application_id"] != root["application_id"]
                    or chunk["source_ordinal"] != ordinal or chunk["chunk_ordinal"] != number
                    or chunk["utf8_byte_start"] != end
                    or any(chunk[key] != header[key] for key in header if key != "kind")
                    or chunk["source_sha256"] != source["source_sha256"]):
                raise ValueError("Exact contiguous delivered source chunks required")
            chunks.append(chunk["text"])
            end = chunk["utf8_byte_end"]
        text = "".join(chunks)
        raw = text.encode()
        if end != source["source_byte_count"] or hashlib.sha256(raw).hexdigest() != source["source_sha256"]:
            raise ValueError("Complete original source bytes required")
        groups[source["group"]].append(source["source"] | {"text": text})
        total += len(raw)
    complete = {key: root[key] for key in FIELDS if key in root} | groups
    if (total != index["source_byte_count"] or digest(complete) != binding
            or {key: len(value) for key, value in groups.items()} != root["bound_rule_counts"]):
        raise ValueError("Exact original policy delivery binding required")
    return groups["bound_state_rules"]
