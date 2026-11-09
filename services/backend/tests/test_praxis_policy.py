import copy
import hashlib
import json

import pytest

from anvil.praxis_policy import agent_instructions, validate_package


def example():
    source = b"Never export customer data outside the approved destination."
    manifest = {
        "schema_version": "praxis.anvil.project_policy.v1",
        "source_project": {"id": "banking", "version": "1", "name": "Fictional KYC"},
        "project_default_policy_refs": [{"policy_id": "privacy", "version": "1"}],
        "sources": [
            {
                "id": "source",
                "path": "policies/privacy.txt",
                "media_type": "text/plain",
                "size_bytes": len(source),
                "sha256": hashlib.sha256(source).hexdigest(),
            }
        ],
        "policies": [
            {
                "policy_id": "privacy",
                "version": "1",
                "title": "Data destinations",
                "source_id": "source",
                "rules": [
                    {
                        "rule_id": "allowed",
                        "requirement": "Use approved destinations only",
                        "source_location": "paragraph 1",
                        "severity": "high",
                        "visibility": "agent_instruction",
                    },
                    {
                        "rule_id": "hidden",
                        "requirement": "PRIVATE TEST CANARY",
                        "source_location": "paragraph 1",
                        "severity": "high",
                        "visibility": "evaluator_only",
                    },
                ],
            }
        ],
        "task_bindings": [
            {
                "task_id": "kyc",
                "task_version": "1",
                "payload_sha256": "a" * 64,
                "policy_refs": [{"policy_id": "privacy", "version": "1"}],
            }
        ],
    }
    return manifest, {"policies/privacy.txt": source}


def validate(value, files):
    return validate_package(
        json.dumps(value).encode(), files, ("banking", "1"), {("kyc", "1"): "a" * 64}
    )


def test_optional_and_document_only():
    value, files = example()
    value["policies"][0]["rules"] = []
    assert validate(value, files).policies[0].rules == []
    value.update(project_default_policy_refs=[], sources=[], policies=[], task_bindings=[])
    assert validate(value, {}).policies == []


def test_candidate_never_receives_hidden_rule_or_source():
    value, files = example()
    result = agent_instructions(validate(value, files), "kyc", "1")
    assert len(result) == 1
    assert "PRIVATE" not in json.dumps(result)
    assert "source_location" not in result[0]


@pytest.mark.parametrize(
    "path",
    [
        "../a",
        "/a",
        "a/../b",
        "a//b",
        "a/./b",
        "C:/a",
        "https://a/b",
        "a\\b",
        "%2e%2e/a",
        ".hidden",
        "a\x00b",
    ],
)
def test_reject_unsafe_paths(path):
    value, files = example()
    value["sources"][0]["path"] = path
    with pytest.raises(ValueError):
        validate(value, files)


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "size",
        "task",
        "project",
        "unknown",
        "duplicate",
        "source",
        "default",
        "extra_file",
        "missing_file",
    ],
)
def test_reject_untrusted_package(mutation):
    value, files = example()
    if mutation == "hash":
        value["sources"][0]["sha256"] = "b" * 64
    if mutation == "size":
        value["sources"][0]["size_bytes"] += 1
    if mutation == "task":
        value["task_bindings"][0]["payload_sha256"] = "b" * 64
    if mutation == "project":
        value["source_project"]["id"] = "other"
    if mutation == "unknown":
        value["api_key"] = "NEVER ACCEPT"
    if mutation == "duplicate":
        value["policies"].append(copy.deepcopy(value["policies"][0]))
    if mutation == "source":
        value["policies"][0]["source_id"] = "absent"
    if mutation == "default":
        value["task_bindings"][0]["policy_refs"] = []
    if mutation == "extra_file":
        files["unknown"] = b"x"
    if mutation == "missing_file":
        files.clear()
    with pytest.raises(ValueError):
        validate(value, files)


def test_explicit_exclusion_and_duplicate_json():
    value, files = example()
    value["task_bindings"][0].update(
        policy_refs=[], excluded_project_policy_refs=[{"policy_id": "privacy", "version": "1"}]
    )
    assert agent_instructions(validate(value, files), "kyc", "1") == []
    with pytest.raises(ValueError, match="Duplicate JSON"):
        validate_package(b'{"x":1,"x":2}', {}, ("banking", "1"), {})
