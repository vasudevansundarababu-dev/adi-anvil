"""Deterministic public policy documents; no paths, private references or IO.

The complete bound input determines every document ID. Text is split only on
UTF8 boundaries; paged manifests preserve every source and byte range in order.
This codec proves consistency, never policy applicability or runtime authority.
"""

import hashlib
import json
import re
from copy import deepcopy

import rfc8785

PROTOCOL = "anvil.policy-documents.v2"
ROOT_SCHEMA = "anvil.bound-application-policy.v2"
CHUNK_SCHEMA = "anvil.policy-source-chunk.v2"
PAGE_SCHEMA = "anvil.policy-source-manifest-page.v2"
PREFIX = "policy-doc-v2:"
MAX_DOCUMENT_BYTES = 8192
MAX_SOURCE_BYTES = 1048576
MAX_TOTAL_BYTES = 52428800
_ID = re.compile(r"policy-doc-v2:([a-f0-9]{64}):(manifest:(0|[1-9][0-9]*)|chunk:(0|[1-9][0-9]*):(0|[1-9][0-9]*))\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")


def _canonical(value):
    return rfc8785.dumps(value)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _size(value):
    return max(len(_canonical(value)), len(json.dumps(value).encode()))


def _seal(body):
    return body | {"document_sha256": _sha(_canonical(body))}


def validate_document(document):
    """Validate an exact returned document before using its public receipt."""
    if type(document) is not dict or _size(document) > MAX_DOCUMENT_BYTES:
        raise ValueError("Bounded policy document required")
    identifier = document.get("document_id")
    match = _ID.fullmatch(identifier) if type(identifier) is str else None
    if (not match or document.get("protocol") != PROTOCOL
            or document.get("policy_binding_sha256") != match.group(1)):
        raise ValueError("Exact bound policy document required")
    unsigned = {key: value for key, value in document.items() if key != "document_sha256"}
    if document.get("document_sha256") != _sha(_canonical(unsigned)):
        raise ValueError("Policy document bytes changed")
    if document.get("schema_version") == CHUNK_SCHEMA:
        text = document.get("text")
        start, end = document.get("utf8_byte_start"), document.get("utf8_byte_end")
        source_size = document.get("source_byte_count")
        source_sha = document.get("source_sha256")
        if (type(text) is not str or type(start) is not int or type(end) is not int
                or type(source_size) is not int or not 0 <= start < end <= source_size
                or end - start != len(text.encode())
                or document.get("chunk_sha256") != _sha(text.encode())
                or type(source_sha) is not str or not _SHA.fullmatch(source_sha)
                or document["document_id"] != (PREFIX + match.group(1) + ":chunk:"
                    + str(document.get("source_ordinal")) + ":" + str(document.get("chunk_ordinal")))):
            raise ValueError("Exact UTF8 policy chunk required")
    elif document.get("schema_version") == PAGE_SCHEMA:
        if not match.group(2).startswith("manifest:") or type(document.get("entries")) is not list:
            raise ValueError("Exact policy manifest page required")
    else:
        raise ValueError("Versioned policy document required")
    return document


def lookup(documents, document_id):
    """Resolve only the freshly bound in-memory document map; never a filename."""
    if type(document_id) is not str or not _ID.fullmatch(document_id):
        raise ValueError("Bound policy document ID required")
    if type(documents) is not dict or document_id not in documents:
        raise ValueError("Policy document is outside the current binding")
    document = documents[document_id]
    validate_document(document)
    if document["document_id"] != document_id:
        raise ValueError("Policy document identity changed")
    return deepcopy(document)


def build(public):
    """Return a compact public index and separate complete scoped document map."""
    if type(public) is not dict or public.get("schema_version") != ROOT_SCHEMA:
        raise ValueError("Explicit version-two policy delivery required")
    binding = _sha(_canonical(public))
    documents, entries = {}, []
    count, total, chunks = 0, 0, 0
    counts = {}
    for group in ("bound_common_rules", "bound_state_rules"):
        sources = public.get(group)
        if type(sources) is not list:
            raise ValueError("Complete ordered policy source lists required")
        counts[group] = len(sources)
        for source in sources:
            if type(source) is not dict or type(source.get("text")) is not str:
                raise ValueError("Complete public policy text required")
            text = source["text"]
            raw = text.encode()
            source_sha = _sha(raw)
            total += len(raw)
            if (not 0 < len(raw) <= MAX_SOURCE_BYTES or total > MAX_TOTAL_BYTES
                    or count >= 200 or source.get("public_text_sha256") != source_sha):
                raise ValueError("Bounded exact original policy text required")
            metadata = deepcopy({key: value for key, value in source.items() if key != "text"})
            header = {"kind": "source", "source_ordinal": count, "group": group,
                      "source_byte_count": len(raw), "source_sha256": source_sha, "source": metadata}
            source_chunks = []
            position, byte_start, ordinal = 0, 0, 0
            while position < len(text):
                identifier = f"{PREFIX}{binding}:chunk:{count}:{ordinal}"

                def candidate(end):
                    part = text[position:end]
                    body = {"schema_version": CHUNK_SCHEMA, "protocol": PROTOCOL,
                            "document_id": identifier, "policy_binding_sha256": binding,
                            "application_id": public.get("application_id"),
                            "source_ordinal": count, "chunk_ordinal": ordinal,
                            "source_sha256": source_sha, "source_byte_count": len(raw),
                            "utf8_byte_start": byte_start, "utf8_byte_end": byte_start + len(part.encode()),
                            "chunk_sha256": _sha(part.encode()), "text": part}
                    return _seal(body)

                low, high, best = position + 1, min(len(text), position + MAX_DOCUMENT_BYTES), None
                while low <= high:
                    middle = (low + high) // 2
                    document = candidate(middle)
                    if _size(document) <= MAX_DOCUMENT_BYTES:
                        best = (middle, document)
                        low = middle + 1
                    else:
                        high = middle - 1
                if best is None:
                    raise ValueError("Policy chunk metadata exceeds the document bound")
                position, document = best
                validate_document(document)
                documents[identifier] = document
                source_chunks.append({"kind": "chunk", **{key: document[key] for key in (
                    "document_id", "document_sha256", "source_ordinal", "chunk_ordinal",
                    "utf8_byte_start", "utf8_byte_end", "chunk_sha256")}})
                byte_start = document["utf8_byte_end"]
                ordinal += 1
            header["chunk_count"] = ordinal
            entries.extend([header, *source_chunks])
            count += 1
            chunks += ordinal
    if not count:
        raise ValueError("At least one complete public policy source required")

    pages, current = [], []

    def page(index, items):
        return _seal({"schema_version": PAGE_SCHEMA, "protocol": PROTOCOL,
                      "document_id": f"{PREFIX}{binding}:manifest:{index}",
                      "policy_binding_sha256": binding, "application_id": public.get("application_id"),
                      "entries": items, "next_document_id": f"{PREFIX}{binding}:manifest:{index + 1}"})

    for entry in entries:
        if _size(page(len(pages), [*current, entry])) > MAX_DOCUMENT_BYTES:
            if not current:
                raise ValueError("Policy source metadata exceeds the document bound")
            pages.append(current)
            current = []
        current.append(entry)
        if _size(page(len(pages), current)) > MAX_DOCUMENT_BYTES:
            raise ValueError("Policy source metadata exceeds the document bound")
    if current:
        pages.append(current)
    page_documents = []
    for index, items in enumerate(pages):
        body = page(index, items)
        if index == len(pages) - 1:
            body = _seal({**{key: value for key, value in body.items() if key != "document_sha256"},
                          "next_document_id": None})
        validate_document(body)
        documents[body["document_id"]] = body
        page_documents.append(body)
    root = deepcopy({key: value for key, value in public.items()
                     if key not in {"bound_common_rules", "bound_state_rules"}})
    root["bound_rule_counts"] = counts
    root["policy_documents"] = {"protocol": PROTOCOL, "policy_binding_sha256": binding,
        "root_manifest_id": f"{PREFIX}{binding}:manifest:0",
        "manifest_sha256": _sha(_canonical(page_documents)), "manifest_page_count": len(pages),
        "source_count": count, "chunk_count": chunks, "source_byte_count": total,
        "maximum_document_bytes": MAX_DOCUMENT_BYTES, "complete_sources_available": True}
    if _size(root) > MAX_DOCUMENT_BYTES:
        raise ValueError("Policy root metadata exceeds the document bound")
    return root, documents
