"""Private normalized world sources, not qualification or activation.

Only the private operator/source producer supplies this body. An actual current
independent rights/source/runtime receipt is still required by API admission.
Candidate prompts, answers, model identity and performance never choose branch.
"""

import hashlib
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import Sha
from anvil.marketing_paid_world import CampaignContext
from anvil.marketing_task2_runtime import Task2Controller
from anvil.marketing_task2_tools import READS
from anvil.praxis_generic_contract import digest
from anvil.schemas import Strict

COLLECTIONS = frozenset(READS.values()) | {"forecasts", "work"}
Branch = Literal["positive", "null", "negative"]


class PublicFixture(Strict):
    source_path: str = Field(min_length=1, max_length=500)
    source_sha256: Sha
    released_at: AwareDatetime
    outcome_binding: Branch | None = None
    public: dict


class Window(Strict):
    week: int = Field(strict=True, ge=1, le=12)
    instant: AwareDatetime
    window_ref: str = Field(min_length=1, max_length=2000)
    source_paths: list[str] = Field(min_length=1, max_length=500)


class WorldDefinition(Strict):
    schema_version: Literal["anvil.marketing-private-world-definition.v1"]
    case_id: Literal["GT2-R01", "GT2-R02"]
    case_snapshot_sha256: Sha
    execution_sha256: Sha
    fixture_manifest_sha256: Sha
    source_manifest_sha256: Sha
    rights_receipt_sha256: Sha
    campaign_context: CampaignContext
    start: AwareDatetime
    # Private operator-generated blinding seed; never a public plan/model ID.
    branch_seed: Sha
    branch_cycle: list[Branch] = Field(min_length=3, max_length=3)
    source_hashes: dict[str, Sha] = Field(min_length=1, max_length=2000)
    public_columns: dict[str, list[str]]
    records: dict[str, list[PublicFixture]]
    windows: list[Window] = Field(min_length=12, max_length=12)

    def initial_instant(self):
        return self.windows[0].instant

    @model_validator(mode="after")
    def exact(self):
        if (
            self.case_id != self.campaign_context.case_id
            or set(self.records) != COLLECTIONS
            or set(self.public_columns) != COLLECTIONS
            or set(self.branch_cycle) != {"positive", "null", "negative"}
            or [window.week for window in self.windows] != list(range(1, 13))
            or self.start != self.initial_instant()
            or any(a.instant >= b.instant for a, b in zip(self.windows, self.windows[1:]))
        ):
            raise ValueError("Exact case, collection, branch and twelve-window source required")
        for path in self.source_hashes:
            if (
                "\\" in path
                or path.startswith("/")
                or any(part in {"", ".", ".."} for part in path.split("/"))
            ):
                raise ValueError("Canonical relative source manifest paths required")
        for window in self.windows:
            if (
                len(set(window.source_paths)) != len(window.source_paths)
                or not set(window.source_paths) <= self.source_hashes.keys()
            ):
                raise ValueError("Actual distinct window sources must exist in pinned manifest")
        count, branches = 0, set()
        for collection, rows in self.records.items():
            columns = self.public_columns[collection]
            if (
                len(columns) > 100
                or len(set(columns)) != len(columns)
                or any(type(name) is not str or not 1 <= len(name) <= 200 for name in columns)
            ):
                raise ValueError(
                    "Bounded explicit per-collection public column projection required"
                )
            ids = set()
            for row in rows:
                count += 1
                identifier = row.public.get("id")
                if (
                    count > 20000
                    or row.source_sha256 != self.source_hashes.get(row.source_path)
                    or not set(row.public) <= set(columns)
                    or type(identifier) is not str
                    or not 1 <= len(identifier) <= 200
                    or (identifier, row.outcome_binding) in ids
                    or (identifier, None) in ids
                    or (row.outcome_binding is None and any(key[0] == identifier for key in ids))
                    or row.released_at > self.windows[-1].instant
                ):
                    raise ValueError("Exact pinned projected source record required")
                ids.add((identifier, row.outcome_binding))
                if row.outcome_binding is not None:
                    branches.add(row.outcome_binding)
                bounded_json(row.public, 49152, max_nodes=10000)
        if branches != set(self.branch_cycle):
            raise ValueError("All three private branch source populations are required")
        bounded_json(self.model_dump(mode="json"), 16777216, max_nodes=200000)
        return self

    def branch(self, repeat_index):
        if type(repeat_index) is not int or not 0 <= repeat_index < 1000:
            raise ValueError("Explicit frozen case repetition index required")
        seed = digest(
            {
                "case_id": self.case_id,
                "snapshot_sha256": self.case_snapshot_sha256,
                "seed": self.branch_seed,
            }
        )
        offset = int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big")
        return self.branch_cycle[(offset + repeat_index) % len(self.branch_cycle)]

    def controller(self, repeat_index):
        """Private API only; the object contains future evidence and credentials."""
        records = {
            name: [
                {
                    "actor_visible": True,
                    "released_at": row.released_at.isoformat(),
                    "outcome_binding": row.outcome_binding,
                    "public": row.model_dump(mode="json")["public"],
                }
                for row in rows
                # Selecting a fixed paired branch is not activating it. Actual
                # approval/request/finance custody must release alternatives
                # later through the private world producer, never by time alone.
                if row.outcome_binding is None
            ]
            for name, rows in self.records.items()
        }
        return Task2Controller(
            self.case_id,
            records=records,
            start=self.start.isoformat(),
            outcome=self.branch(repeat_index),
            budget_minor=self.campaign_context.business_budget_minor,
        )


def definition(value):
    """Bound untrusted operator bytes before model validation/hash expansion."""
    bounded_json(value, 16777216, max_nodes=200000)
    if type(value) is dict and value.get("schema_version") == "anvil.marketing-private-world-definition.v6":
        from anvil.marketing_world_population_definition import PopulationWorldDefinition

        return PopulationWorldDefinition.model_validate(value)
    if type(value) is dict and value.get("schema_version") == "anvil.marketing-private-world-definition.v5":
        from anvil.marketing_world_opening_definition import OpeningWorldDefinition

        return OpeningWorldDefinition.model_validate(value)
    if type(value) is dict and value.get("schema_version") == "anvil.marketing-private-world-definition.v4":
        from anvil.marketing_world_activation_definition import ActivationWorldDefinition

        return ActivationWorldDefinition.model_validate(value)
    if type(value) is dict and value.get("schema_version") == "anvil.marketing-private-world-definition.v3":
        from anvil.marketing_world_funding_definition import FundingWorldDefinition

        return FundingWorldDefinition.model_validate(value)
    if type(value) is dict and value.get("schema_version") == "anvil.marketing-private-world-definition.v2":
        from anvil.marketing_world_service_definition import ServiceWorldDefinition

        return ServiceWorldDefinition.model_validate(value)
    return WorldDefinition.model_validate(value)
