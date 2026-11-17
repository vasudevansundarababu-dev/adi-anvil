"""Explicit v5 source program: original opening plan plus twelve report reviews.

No existing v4 definition is silently upgraded. Actual admission must pin this
definition and the matching operator program; parsing grants no run authority.
"""

from copy import deepcopy
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from anvil.dataset_export_contract import Sha
from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_world_activation_definition import ActivationWorldDefinition
from anvil.marketing_world_definition import Window
from anvil.praxis_generic_contract import digest

PROGRAM = "marketing-opening0-and-twelve-reviews-v1"


def operator_program(execution):
    from anvil.praxis_marketing_contract import MarketingExecution

    contract = MarketingExecution.model_validate(execution)
    return {"schema_version": "anvil.marketing-operator-schedule.v2", "program_id": PROGRAM,
            "role_ids": [role["id"] for role in contract.workflow_graph["roles"]],
            "opening_index": 0, "review_indices": list(range(1, 13)), "observation_indices": list(range(13)),
            "weekly_cycle_backedges": 12, "workflow_graph_sha256": contract.workflow_graph_sha256}


class OpeningWindow(Window):
    week: int = Field(strict=True, ge=0, le=0)
    instant: AwareDatetime
    source_paths: list[str] = Field(min_length=1, max_length=500)


class OpeningWorldDefinition(ActivationWorldDefinition):
    schema_version: Literal["anvil.marketing-private-world-definition.v5"]
    operator_program_id: Literal["marketing-opening0-and-twelve-reviews-v1"]
    operator_program_sha256: Sha
    opening: OpeningWindow

    def initial_instant(self):
        return self.opening.instant

    def expected_observation_start(self, program):
        return timestamp(self.service_contract["shared"]["campaign_contract"]["start"] + "T00:00:00Z")

    @model_validator(mode="after")
    def exact_opening(self):
        path = "shared/campaign_contract.json"
        if (self.opening.instant != self.expected_observation_start(None)
                or self.opening.instant >= self.windows[0].instant
                or self.opening.source_paths != [path]
                or path not in self.source_hashes
                or self.opening.window_ref != "anvil-marketing-opening:" + self.case_id + ":" + self.source_hashes[path]
                or self.operator_program_sha256 != digest(operator_program(self.service_contract["execution"]))):
            raise ValueError("Original source-bound opening before twelve report reviews required")
        return self


def with_opening(world):
    """Explicit operator preparation; preserve all source dates and twelve reviews."""
    if type(world) is not dict or world.get("schema_version") != "anvil.marketing-private-world-definition.v4":
        raise ValueError("Explicit complete private v4 predecessor required")
    value = deepcopy(world)
    path = "shared/campaign_contract.json"
    instant = value["service_contract"]["shared"]["campaign_contract"]["start"] + "T00:00:00Z"
    value.update(schema_version="anvil.marketing-private-world-definition.v5", operator_program_id=PROGRAM,
                 operator_program_sha256=digest(operator_program(value["service_contract"]["execution"])),
                 start=instant, opening={"week": 0, "instant": instant, "source_paths": [path],
                                        "window_ref": "anvil-marketing-opening:" + value["case_id"] + ":" + value["source_hashes"][path]})
    return value
