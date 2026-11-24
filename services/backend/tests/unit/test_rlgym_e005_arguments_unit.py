"""E-005 §2.3 step 4: versions whose arguments differ for a tool a task names, or whose data lacks a document type the
tasks rely on, are greyed out (Studio's operation_contracts and document_kinds)."""

from anvil.rlgym.suites import environment


def test_cited_document_kinds():
    actors = [
        {"sections": {"S2": {"inputContract": "Read the government ID and proof of address."}}}
    ]
    assert environment.cited_kinds(
        actors, {"government_id", "proof_of_address", "passport", "screening_result"}
    ) == {"government_id", "proof_of_address"}


def test_signatures_are_read_from_the_record(monkeypatch):
    monkeypatch.setitem(
        environment._RECORDS,
        "env@9",
        {
            "operation_contracts": [
                {
                    "operation_id": "recommend",
                    "signature_sha256": "s1",
                    "inputs": [{"name": "decision"}],
                }
            ]
        },
    )
    assert environment.signatures({"id": "env@9"})["recommend"]["signature_sha256"] == "s1"
