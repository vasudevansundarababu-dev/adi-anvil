"""Bounded actor-visible structured inputs and explicit deterministic sampling.

This contract neither cleans quarantined files nor grants dataset/runtime/rights
qualification. A selected input version must be consumed by candidate and grader.
"""

import hashlib
import math
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, TypeAdapter, field_validator, model_validator

from anvil.db import digest
from anvil.golden_kyc_data import VERSION
from anvil.schemas import Strict

MAX_BYTES = 10 * 1048576
PROJECT_QUOTA_BYTES = 50 * 1048576
Identifier = Annotated[
    str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
]
Text = Annotated[str, Field(max_length=20000)]
State = Literal["CA", "NY", "TX", "FL", "IL"]
Product = Literal["individual", "adult_joint", "teen_joint", "custodial"]
FORBIDDEN = {
    "private_reference",
    "expected_outputs",
    "reviewer_only",
    "scenario_controls",
    "controller_token",
    "role_tokens",
}


def actor_json(value, depth=0):
    if depth > 8:
        raise ValueError("Actor record nesting exceeds8 levels")
    if isinstance(value, dict):
        if len(value) > 200 or set(value) & FORBIDDEN:
            raise ValueError("Actor inputs cannot contain hidden references or runtime controls")
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 200:
                raise ValueError("Bounded string field names required")
            actor_json(child, depth + 1)
    elif isinstance(value, list):
        if len(value) > 10000:
            raise ValueError("Bounded actor arrays required")
        for child in value:
            actor_json(child, depth + 1)
    elif type(value) not in (str, int, float, bool, type(None)):
        raise ValueError("Only JSON data is supported")
    if type(value) is float and not math.isfinite(value):
        raise ValueError("Finite JSON numbers required")
    if isinstance(value, str) and (len(value) > 20000 or "\x00" in value):
        raise ValueError("Bounded UTF8 text required")


class Party(Strict):
    id: Identifier
    name: str = Field(min_length=1, max_length=200)
    birth_date: date | None
    role: Literal["owner", "teen_owner", "adult_owner", "custodian", "beneficiary"]
    address: str = Field(min_length=1, max_length=1000)
    residence_state: State
    contact: str = Field(max_length=320)
    identity_route: str = Field(min_length=1, max_length=100)


class Document(Strict):
    id: Identifier
    revision: int = Field(ge=1, le=10000, strict=True)
    party_id: Identifier
    kind: str = Field(min_length=1, max_length=100)
    fields: dict = Field(max_length=100)
    text: Text
    quality: str = Field(default="unspecified", min_length=1, max_length=100)

    @field_validator("fields")
    @classmethod
    def data_only(cls, value):
        actor_json(value)
        return value


class Charter(Strict):
    profile: str = Field(min_length=1, max_length=200)
    reviewed: Literal[False]


class Application(Strict):
    id: Identifier
    data_origin: str = Field(min_length=1, max_length=200)
    revision: int = Field(ge=1, le=10000, strict=True)
    product: Product
    requested_product: str = Field(min_length=1, max_length=100)
    assessment_date: date
    governing_state: State
    branch_state: State
    product_version: Literal[VERSION]
    policy_bundle: Literal[VERSION]
    charter_applicability: Charter
    purpose: str = Field(max_length=2000)
    expected_monthly_activity: str = Field(max_length=2000)
    parties: list[Party] = Field(min_length=1, max_length=10)
    documents: list[Document] = Field(max_length=100)
    calendar_version: Literal["golden-weekdays-2026-v1"]

    @model_validator(mode="after")
    def source_links(self):
        parties = [party.id for party in self.parties]
        documents = [doc.id for doc in self.documents]
        if len(parties) != len(set(parties)) or len(documents) != len(set(documents)):
            raise ValueError("Unique party and document IDs required")
        if any(doc.party_id not in parties for doc in self.documents):
            raise ValueError("Every document must reference a declared application party")
        return self


class KycInput(Strict):
    schema_version: Literal["anvil.kyc-actor-input.v1"]
    applications: list[Application] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def shared_states(self):
        if len({app.id for app in self.applications}) != len(self.applications):
            raise ValueError("Unique application IDs required")
        return self


class PublicRecord(Strict):
    released_at: AwareDatetime
    public: dict

    @field_validator("public")
    @classmethod
    def public_only(cls, value):
        actor_json(value)
        return value


class Campaign(Strict):
    id: Literal["GT2-R01", "GT2-R02"]
    locale: Literal["en-US"]
    start: AwareDatetime
    collections: dict[str, list[PublicRecord]] = Field(max_length=30)

    @model_validator(mode="after")
    def known_collections(self):
        from anvil.marketing_task2_tools import READS

        if set(self.collections) - (set(READS.values()) | {"forecasts"}):
            raise ValueError("Only published candidate-visible campaign collections are supported")
        if sum(len(rows) for rows in self.collections.values()) > 10000:
            raise ValueError("At most10000 public records per campaign")
        return self


class CampaignInput(Strict):
    schema_version: Literal["anvil.campaign-actor-input.v1"]
    cases: list[Campaign] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def us_pair(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Unique supported US campaign case IDs required")
        return self


INPUT = TypeAdapter(Annotated[KycInput | CampaignInput, Field(discriminator="schema_version")])


class FrozenSelection(Strict):
    id: UUID
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Sampling(Strict):
    mode: Literal["all", "explicit_ids", "deterministic_random", "stratified_state"] = "all"
    count: int | None = Field(default=None, ge=1, le=10000, strict=True)
    seed: str | None = Field(default=None, min_length=1, max_length=120)
    case_ids: list[Identifier] | None = Field(default=None, min_length=1, max_length=10000)

    @model_validator(mode="after")
    def explicit(self):
        if self.mode == "all" and any(
            value is not None for value in (self.count, self.seed, self.case_ids)
        ):
            raise ValueError("All means the whole dataset without implicit sampling")
        if self.mode == "explicit_ids" and (
            not self.case_ids or self.count is not None or self.seed is not None
        ):
            raise ValueError("Explicit selection needs only unique case IDs")
        if self.case_ids and len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("Duplicate case selection")
        if self.mode in {"deterministic_random", "stratified_state"} and (
            self.count is None or self.seed is None or self.case_ids is not None
        ):
            raise ValueError("Sampling requires an explicit count and seed")
        return self


def select(members, dataset_sha256, sampling):
    by_id = {member["id"]: member for member in members}
    if not members or len(by_id) != len(members):
        raise ValueError("Exact unique eligible population required")
    if sampling.mode == "all":
        chosen = sorted(by_id)
    elif sampling.mode == "explicit_ids":
        if set(sampling.case_ids) - set(by_id):
            raise ValueError("Selected cases are outside the bound input version")
        chosen = sorted(sampling.case_ids)
    else:
        if sampling.count > len(members):
            raise ValueError("Sample count exceeds the eligible population")

        def rank(identifier):
            return hashlib.sha256(
                (sampling.seed + "\0" + dataset_sha256 + "\0" + identifier).encode()
            ).hexdigest(), identifier

        if sampling.mode == "deterministic_random":
            chosen = sorted(sorted(by_id, key=rank)[: sampling.count])
        else:
            groups = {}
            for member in members:
                if member.get("governing_state") not in {"CA", "NY", "TX", "FL", "IL"}:
                    raise ValueError("State stratification applies only to KYC application cases")
                groups.setdefault(member["governing_state"], []).append(member["id"])
            if sampling.count < len(groups):
                raise ValueError("State-stratified samples require at least one case per state")
            quotas = {state: 1 for state in groups}
            remaining = sampling.count - len(groups)
            capacity = sum(len(ids) - 1 for ids in groups.values())
            if capacity:
                for state, ids in groups.items():
                    quotas[state] += remaining * (len(ids) - 1) // capacity
                residual = sampling.count - sum(quotas.values())
                ordering = sorted(
                    groups,
                    key=lambda state: (-(remaining * (len(groups[state]) - 1) % capacity), state),
                )
                for state in ordering[:residual]:
                    quotas[state] += 1
            chosen = sorted(
                identifier
                for state, ids in groups.items()
                for identifier in sorted(ids, key=rank)[: quotas[state]]
            )
    selection = {
        "schema_version": "anvil.input-sample.v1",
        "dataset_sha256": dataset_sha256,
        "sampling": sampling.model_dump(),
        "eligible_count": len(members),
        "selected_count": len(chosen),
        "members": [by_id[identifier] for identifier in chosen],
        "complete_population": len(chosen) == len(members),
    }
    return selection | {"sha256": digest(selection)}
