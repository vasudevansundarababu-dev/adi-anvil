"""Public installation trust policy, separate from source bundles and product secrets."""

import base64
import os
import stat
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool

from anvil.benchmark_bundle import TrustedSigner, _json


class SignerPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
    public_key_base64: str = Field(min_length=44, max_length=44)
    not_before: AwareDatetime
    not_after: AwareDatetime
    revoked: StrictBool


class TrustPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["anvil.benchmark.trust.v1"]
    keys: list[SignerPolicy] = Field(max_length=100)


def load_trust_policy() -> dict[str, TrustedSigner]:
    location = os.environ.get("ANVIL_BENCHMARK_TRUST_POLICY")
    if location is None:
        return {}  # No configured roots means every unknown signature stays quarantined.
    path = Path(location)
    if not path.is_absolute():
        raise RuntimeError("Trust policy requires an absolute installation path")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_mode & 0o022
                or info.st_size > 65536
                or info.st_uid not in {0, os.geteuid()}
                or info.st_nlink != 1
            ):
                raise ValueError("Unsafe public trust policy")
            policy = TrustPolicy.model_validate(_json(stream.read(65537)))
        result = {}
        for key in policy.keys:
            if key.key_id in result:
                raise ValueError("Duplicate signer")
            public = base64.b64decode(key.public_key_base64, validate=True)
            if base64.b64encode(public).decode() != key.public_key_base64:
                raise ValueError("Noncanonical public key")
            result[key.key_id] = TrustedSigner(
                key.key_id, public, key.not_before, key.not_after, key.revoked
            )
        return result
    except (OSError, ValueError) as exc:
        raise RuntimeError("Invalid installation benchmark trust policy") from exc
