"""Explicit private world v2; v1 definitions and public task schemas unchanged."""

from typing import Literal

from pydantic import model_validator

from anvil.dataset_export_contract import Sha
from anvil.marketing_world_definition import WorldDefinition
from anvil.marketing_world_service_sources import normalize, public_sources
from anvil.praxis_generic_contract import canonical, digest


class ServiceWorldDefinition(WorldDefinition):
    schema_version: Literal["anvil.marketing-private-world-definition.v2"]
    service_contract: dict
    service_contract_sha256: Sha

    @model_validator(mode="after")
    def exact_services(self):
        value = self.service_contract
        documents = value.get("source_documents")
        execution = value.get("execution")
        if (type(documents) is not dict or type(execution) is not dict
                or digest(execution) != self.execution_sha256
                or len(documents) > 50
                or any(type(path) is not str or type(raw) is not str for path, raw in documents.items())):
            raise ValueError("Exact private service source bytes and execution required")
        expected = normalize(self.case_id, {path: raw.encode("utf-8") for path, raw in documents.items()},
                             self.source_hashes, execution)
        if canonical(value) != canonical(expected) or digest(value) != self.service_contract_sha256:
            raise ValueError("Private service rules differ from their actual pinned source bytes")
        for collection, path, public in public_sources(value):
            rows = [r for r in self.records[collection] if r.public.get("id") == public["id"]]
            if (len(rows) != 1 or rows[0].outcome_binding is not None
                    or rows[0].source_path != path or rows[0].source_sha256 != self.source_hashes[path]
                    or canonical(rows[0].public) != canonical(public)):
                raise ValueError("Required released service evidence differs from approved baseline source")
        return self
