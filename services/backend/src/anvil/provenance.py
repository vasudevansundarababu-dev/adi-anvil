"""Immutable author declarations; never an independent rights or privacy approval."""

from typing import Literal

from fastapi import HTTPException
from pydantic import Field, model_validator

from anvil.db import Jsonb, audit, digest, one
from anvil.schemas import Strict


class Declaration(Strict):
    classification: Literal[
        "bodhium_restricted",
        "adi_praxis_sme",
        "adi_synthetic",
        "public_permitted",
        "third_party_licensed",
    ]
    source_owner: str = Field(min_length=3, max_length=200)
    basis: str = Field(min_length=10, max_length=1000)
    generator_version: str | None = Field(default=None, min_length=1, max_length=100)
    seed: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def synthetic_metadata(self):
        if any(not v.strip() for v in (self.source_owner, self.basis)):
            raise ValueError("Owner and declaration basis cannot be blank")
        if self.classification == "adi_synthetic" and (
            not self.generator_version
            or not self.generator_version.strip()
            or not self.seed
            or not self.seed.strip()
        ):
            raise ValueError("Synthetic sources require generator version and seed")
        if self.classification != "adi_synthetic" and (self.generator_version or self.seed):
            raise ValueError(
                "Synthetic generator metadata cannot relabel partner or licensed ownership"
            )
        return self


def read(c, artifact):
    r = one(c, "SELECT * FROM anvil.source_provenance WHERE artifact_id=%s", (artifact,))
    if not r:
        return {
            "classification": "unclassified",
            "source_owner": None,
            "status": "missing_declaration",
        }
    return r["declaration"] | {
        "declaration_sha256": digest(r["declaration"]),
        "declared_by": str(r["declared_by"]),
        "declared_at": r["created_at"].isoformat(),
        "status": "author_declared_not_independently_reviewed",
    }


def declare(c, project, user, artifact, body):
    if body is None:
        return
    content = body.model_dump(mode="json")
    old = one(
        c, "SELECT declaration FROM anvil.source_provenance WHERE artifact_id=%s", (artifact,)
    )
    if old:
        if old["declaration"] != content:
            raise HTTPException(
                409,
                "Source provenance/owner is immutable; upload a new source rather than relabel it",
            )
        return
    if one(c, "SELECT 1 FROM anvil.task_imports WHERE source_artifact_id=%s", (artifact,)):
        raise HTTPException(
            409,
            "This source was imported without a declaration; re-upload rather than retroactively relabel it",
        )
    c.execute(
        "INSERT INTO anvil.source_provenance(project_id,artifact_id,declaration,declared_by) VALUES(%s,%s,%s,%s)",
        (project, artifact, Jsonb(content), user),
    )
    audit(
        c,
        project,
        user,
        "source.provenance_declared",
        artifact,
        {"classification": body.classification},
    )


def publication_blocker(info):
    if info["classification"] == "unclassified":
        return "Source provenance is unclassified; upload a source with an explicit immutable declaration"
    if info["classification"] != "adi_synthetic":
        return "Restricted, SME, public and licensed source publication requires independently reviewed rights/privacy controls, unavailable in this increment"
    return None
