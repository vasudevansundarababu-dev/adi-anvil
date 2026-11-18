"""Synthetic public text only; no model, network, policy approvals or SQL."""
import hashlib
import json
from copy import deepcopy

import pytest
import rfc8785

from anvil import golden_kyc_policy_chunks as codec
from anvil.kyc_policy_observation_projection import RECEIPT_SCHEMA, VERSION, project


def public(texts):
    sources = [{"id": f"synthetic-{i}", "version": "test-only",
                "public_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "content_sha256": "a" * 64, "artifact_sha256": "b" * 64,
                "hash_scheme": "synthetic", "text": text} for i, text in enumerate(texts)]
    return {"schema_version": codec.ROOT_SCHEMA, "application_id": "synthetic-application",
            "bound_common_rules": sources[:1], "bound_state_rules": sources[1:]}


def observation(operation, payload):
    return {"actions": [{"operation": operation,
                         "result": {"status": "completed", "result": payload}}], "closed": False}


@pytest.mark.parametrize("texts", [["a" * 13000, "b" * 71000, "c" * 69000],
                                  [('"\\\n😀é' * 9000), "state" * 3000]])
def test_complete_sources_deterministic_bounded_and_utf8_safe(texts):
    original = public(texts)
    root, documents = codec.build(original)
    assert (root, documents) == codec.build(original)
    for document in [root, *documents.values()]:
        assert len(rfc8785.dumps(document)) <= 8192
        assert len(json.dumps(document).encode()) <= 8192
    pages, current = [], root["policy_documents"]["root_manifest_id"]
    while current:
        page = codec.lookup(documents, current)
        pages.append(page)
        current = page["next_document_id"]
    assert hashlib.sha256(rfc8785.dumps(pages)).hexdigest() == root["policy_documents"]["manifest_sha256"]
    entries = [entry for page in pages for entry in page["entries"]]
    for ordinal, text in enumerate(texts):
        header = next(e for e in entries if e["kind"] == "source" and e["source_ordinal"] == ordinal)
        refs = [e for e in entries if e["kind"] == "chunk" and e["source_ordinal"] == ordinal]
        assert header["source"]["id"] == f"synthetic-{ordinal}"
        assert header["chunk_count"] == len(refs)
        rebuilt, previous = b"", 0
        for ref in refs:
            chunk = codec.lookup(documents, ref["document_id"])
            assert chunk["utf8_byte_start"] == previous
            assert chunk["document_sha256"] == ref["document_sha256"]
            rebuilt += chunk["text"].encode()
            previous = chunk["utf8_byte_end"]
        assert rebuilt == text.encode()
        assert hashlib.sha256(rebuilt).hexdigest() == header["source_sha256"]
    changed = deepcopy(original)
    changed["application_id"] = "foreign-application"
    assert not (set(documents) & set(codec.build(changed)[1]))
    assert original == public(texts)


def test_lookup_exact_scoped_copy_and_tamper_fail_closed():
    _, documents = codec.build(public(["synthetic" * 1000]))
    identifier = next(iter(documents))
    copy = codec.lookup(documents, identifier)
    copy["text"] = "changed"
    assert codec.lookup(documents, identifier) != copy
    for foreign in ("../../secret", identifier + "/", "policy-doc-v2:" + "f" * 64 + ":chunk:0:0", None):
        with pytest.raises(ValueError):
            codec.lookup(documents, foreign)
    documents[identifier]["text"] = "tampered"
    with pytest.raises(ValueError):
        codec.lookup(documents, identifier)


def test_original_size_and_metadata_bounds_are_explicit():
    with pytest.raises(ValueError):
        codec.build(public(["x" * (codec.MAX_SOURCE_BYTES + 1)]))
    body = public(["source"])
    body["bound_common_rules"][0]["id"] = "x" * 9000
    with pytest.raises(ValueError):
        codec.build(body)


def test_projection_receipts_rereads_scope_and_ordinary_observations():
    root, documents = codec.build(public(["synthetic" * 3000]))
    chunks = [d for d in documents.values() if d["schema_version"] == codec.CHUNK_SCHEMA]
    events = [observation("policy.read", root), observation("application.read", {"keep": "all"})]
    events += [observation("document.read", chunk) for chunk in chunks]
    frozen = deepcopy(events)
    visible, marker = project(events, application_id="synthetic-application")
    assert events == frozen and marker["schema_version"] == VERSION
    assert marker["full_transcript_sha256"] == hashlib.sha256(rfc8785.dumps(events)).hexdigest()
    assert visible[1] == events[1] and visible[-1] == events[-1]
    receipt = visible[2]["actions"][0]["result"]["result"]
    assert marker["receipt_schema_version"] == RECEIPT_SCHEMA and "text" not in receipt
    assert receipt["policy_document_receipt_v2"][0] == chunks[0]["document_id"]
    reread = events + [observation("document.read", codec.lookup(documents, receipt["policy_document_receipt_v2"][0]))]
    assert project(reread, application_id="synthetic-application")[0][-1] == reread[-1]
    with pytest.raises(ValueError):
        project(events, application_id="foreign")
    with pytest.raises(ValueError):
        project(events[2:], application_id="synthetic-application")
    legacy = [observation("document.read", {"text": "ordinary" * 10000})]
    assert project(legacy, application_id="synthetic-application") == (legacy, None)


def test_every_actor_prompt_for_complete_153kb_source_stays_bounded(monkeypatch):
    from anvil import golden_kyc_paid_session as session

    root, documents = codec.build(public(["a" * 13000, "b" * 71000, "c" * 69000]))
    binding = {"group_id": "group", "resolved_task_id": "task", "application_id": "synthetic-application",
               "runtime_sha256": "a" * 64, "import_id": "import"}
    native = {key: binding[key] for key in ("resolved_task_id", "application_id", "runtime_sha256", "import_id")}
    plan = {"id": "plan", "project_id": "project", "created_by": "synthetic-user",
            "config": {"workspace_execution_group": "group", "golden_native_binding": native, "max_calls": 100}}
    monkeypatch.setattr(session, "one", lambda *a, **kw: binding)
    monkeypatch.setattr(session, "task_context", lambda *a, **kw: {"synthetic": True})

    class Connection:
        def __init__(self):
            self.rows = []

        def execute(self, *args):
            return self

        def fetchall(self):
            return self.rows

    connection = Connection()
    # Actual delivery order: metadata root, linked manifests, then all chunks.
    events = [observation("policy.read", root)]
    events += [observation("document.read", d) for d in documents.values() if d["schema_version"] == codec.PAGE_SCHEMA]
    events += [observation("document.read", d) for d in documents.values() if d["schema_version"] == codec.CHUNK_SCHEMA]
    for event in events:
        connection.rows.append({"observation": event, "observation_sha256": session.digest(event)})
        frozen = deepcopy(connection.rows)
        prompt = session.actor_prompt(connection, plan, len(connection.rows))
        assert len(prompt.encode()) <= 32768
        assert VERSION in prompt and codec.PROTOCOL in prompt
        value = json.loads(prompt.split("\n", 1)[1])
        contracts = value["tool_contracts"]
        from anvil.golden_kyc_tool_contract import tools
        assert [contracts["defaults"] | item for item in contracts["tools"]] == tools()
        assert contracts["contracts_sha256"] == session.digest(tools())
        assert connection.rows == frozen
    connection.rows.append({"observation": observation("application.read", {"ordinary": "z" * 33000})})
    connection.rows[-1]["observation_sha256"] = session.digest(connection.rows[-1]["observation"])
    with pytest.raises(RuntimeError, match="golden_actor_input_bound"):
        session.actor_prompt(connection, plan, len(connection.rows))
