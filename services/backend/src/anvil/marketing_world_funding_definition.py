"""Explicit private v3 successor with independently pinned parent accounting."""

from copy import deepcopy
from typing import Literal

from pydantic import model_validator

from anvil.dataset_export_contract import Sha
from anvil.marketing_world_finance import FILES, normalize
from anvil.marketing_world_service_definition import ServiceWorldDefinition
from anvil.praxis_generic_contract import canonical, digest


class FundingWorldDefinition(ServiceWorldDefinition):
    schema_version: Literal["anvil.marketing-private-world-definition.v3"]
    finance_source_documents: dict[str, str]
    finance_book: dict
    finance_book_sha256: Sha

    @model_validator(mode="after")
    def exact_finance(self):
        paths = {f"cases/{self.case_id}/{name}" for name in FILES}
        if set(self.finance_source_documents) != paths:
            raise ValueError("Exact original parent-finance source files required")
        expected = normalize(self.case_id, {path: raw.encode("utf-8") for path, raw in self.finance_source_documents.items()},
                             self.source_hashes)
        if canonical(expected) != canonical(self.finance_book) or digest(expected) != self.finance_book_sha256:
            raise ValueError("Private finance book differs from original pinned source bytes")
        return self


def with_finance(world, files):
    """Prepare source only; no seed, admission, activation or qualification."""
    if type(world) is not dict or world.get("schema_version") != "anvil.marketing-private-world-definition.v2":
        raise ValueError("Explicit original service-world v2 required")
    value = deepcopy(world)
    paths = [f"cases/{value['case_id']}/{name}" for name in FILES]
    book = normalize(value["case_id"], files, value["source_hashes"])
    value.update(schema_version="anvil.marketing-private-world-definition.v3",
                 finance_source_documents={path: files[path].decode("utf-8") for path in paths},
                 finance_book=book, finance_book_sha256=digest(book))
    return value
