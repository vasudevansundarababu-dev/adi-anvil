"""Explicit v6: source-complete opening world, expanded only inside the API."""

from copy import deepcopy
from typing import Literal

from pydantic import model_validator

from anvil.marketing_task2_persistence import freeze
from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_world_definition import PublicFixture
from anvil.marketing_world_opening_definition import OpeningWorldDefinition
from anvil.marketing_world_population import compile_population, encode_sources
from anvil.praxis_generic_contract import canonical, digest

VIRTUAL = {"products", "capabilities", "campaigns", "questions", "observation-windows"}


def branch_declarations(case, services, pins):
    """Private source inventory only, never a candidate answer/issued decision."""
    rows = []
    for branch in ("positive", "null", "negative"):
        source = services["conditional_campaign_approval_sources"][branch]
        path = f"reviewer_only/us-pair/{case}/reuse-test-{branch}/conditional_campaign_approval.json"
        rows.append({"source_path": path, "source_sha256": pins[path], "outcome_binding": branch,
                     "released_at": source["issued_at_if_selected"],
                     "public": {"id": "anvil-private-source:" + digest({"path": path, "sha256": pins[path]}),
                                "source_kind": "conditional_campaign_source_declaration"}})
    return rows


class PopulationWorldDefinition(OpeningWorldDefinition):
    schema_version: Literal["anvil.marketing-private-world-definition.v6"]
    population_source_documents: dict[str, list[str]]

    def population(self):
        return compile_population(self.case_id, self.population_source_documents, self.source_hashes, self.service_contract)

    @model_validator(mode="after")
    def exact_population(self):
        if any(self.records[name] for name in VIRTUAL):
            raise ValueError("Virtual populations must derive from complete original bytes, not operator rows")
        expected = [PublicFixture.model_validate(row).model_dump(mode="json")
                    for row in branch_declarations(self.case_id, self.service_contract, self.source_hashes)]
        if canonical([row.model_dump(mode="json") for row in self.records["work"]]) != canonical(expected):
            raise ValueError("Original private source declarations required; no manufactured branch markers")
        rows = self.population()
        if sum(map(len, self.records.values())) + len(rows) > 20000:
            raise ValueError("Complete actual public population exceeds original row bound")
        existing = {(collection, row.public["id"]) for collection, records in self.records.items() for row in records}
        for collection, row in rows:
            if ((collection, row.public["id"]) in existing or row.released_at > self.windows[-1].instant
                    or not set(row.public) <= set(self.public_columns[collection])):
                raise ValueError("Exact source projection, distinct identity and final release bound required")
        return self

    def controller(self, repeat_index):
        controller = super().controller(repeat_index)
        for collection, row in self.population():
            controller._initial[collection].append({"actor_visible": True, "released_at": row.released_at.isoformat(),
                                                    "outcome_binding": None, "public": row.model_dump(mode="json")["public"]})
        # Original persisted-controller byte ceiling is unchanged. Future rows
        # remain private until their source release time; no branch is activated.
        freeze(controller)
        return controller


def with_population(world, files):
    if type(world) is not dict or world.get("schema_version") != "anvil.marketing-private-world-definition.v5":
        raise ValueError("Explicit original-opening private v5 predecessor required")
    value = deepcopy(world)
    documents = encode_sources(value["case_id"], files, value["source_hashes"])
    rows = compile_population(value["case_id"], documents, value["source_hashes"], value["service_contract"])
    if any(value["records"][name] for name in VIRTUAL):
        raise ValueError("Do not overwrite an existing operator population")
    for collection, row in rows:
        value["public_columns"][collection] = sorted(set(value["public_columns"][collection]) | set(row.public))
    value["records"]["work"] = branch_declarations(value["case_id"], value["service_contract"], value["source_hashes"])
    value["public_columns"]["work"] = ["id", "source_kind"]
    value.update(schema_version="anvil.marketing-private-world-definition.v6", population_source_documents=documents)
    # The original opening source clock is retained, never the first feedback.
    if timestamp(value["start"]) != timestamp(value["opening"]["instant"]):
        raise ValueError("Original opening clock changed")
    return value
