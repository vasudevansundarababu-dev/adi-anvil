"""Wire-source numeric hashing differs from unchanged local metadata hashing."""

from test_marketing_paid_session import fixture

from anvil.db import digest as metadata_digest
from anvil.marketing_paid_contract import phase
from anvil.marketing_paid_session import task_context
from anvil.marketing_task2_workflow_store import Journal
from anvil.praxis_generic_contract import digest as wire_digest


def test_numeric_published_source_is_verified_with_its_rfc8785_producer(monkeypatch):
    data = fixture(monkeypatch)
    row = data["resolved"]
    row["actor"]["numeric_probe"] = {"whole": 1.0, "small": 1e-7, "zero": -0.0}
    execution = row["spec"]["execution"]
    execution["output_schema"]["properties"]["numeric_probe"] = {"type": "number", "maximum": 1.0}
    row["actor_sha256"] = wire_digest(row["actor"])
    row["spec_sha256"] = wire_digest(row["spec"])
    row["binding"].update(
        actor_sha256=row["actor_sha256"],
        template_sha256=row["spec_sha256"],
        execution_sha256=wire_digest(execution),
    )
    row["binding"]["case_context"]["evaluator_bindings_sha256"] = wire_digest(
        execution["evaluators"]
    )
    row["binding"]["case_context_sha256"] = wire_digest(row["binding"]["case_context"])
    row["binding_sha256"] = wire_digest(row["binding"])
    imported = data["imported"]
    imported["content"]["tasks"][0]["source"]["template"]["sha256"] = row["spec_sha256"]
    imported["content_sha256"] = metadata_digest(imported["content"])
    assert row["actor_sha256"] != metadata_digest(row["actor"])
    result = task_context(None, "project", "resolved", imported["id"])
    assert result["native_binding"]["execution_sha256"] == wire_digest(execution)
    assert result["run_authority"] == "not_granted"
    node = next(n for n in execution["workflow_graph"]["nodes"] if n["id"] == "intent_step")
    inputs = {name: {} for name in node["inputRefs"]}
    context = phase(execution, node["id"], inputs, 1, 1)
    journal = Journal(None, "project", "user", "episode", 0, execution, None)
    assert context["execution_sha256"] == journal.execution_sha == wire_digest(execution)
    assert context["inputs_sha256"] == metadata_digest(inputs)
