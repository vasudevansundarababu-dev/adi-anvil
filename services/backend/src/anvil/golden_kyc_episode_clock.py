"""Server-minted cross-host clock projection, never caller time authority."""

from typing import Literal

from pydantic import AwareDatetime, model_validator

from anvil.dataset_export_contract import Model, Sha
from anvil.marketing_native_wire_bounds import remaining


class EpisodeCutoff(Model):
    schema_version: Literal['anvil.kyc-episode-cutoff.v1']
    started_at: AwareDatetime
    deadline_at: AwareDatetime
    observed_at: AwareDatetime
    plan_subject_sha256: Sha

    @model_validator(mode='after')
    def original_interval(self):
        interval=(self.deadline_at-self.started_at).total_seconds()
        if not 1<=interval<=600 or not self.started_at<=self.observed_at<self.deadline_at:
            raise ValueError('Exact unexpired server KYC episode interval required')
        return self


def deadline(value,*,request_started,original_cutoff):
    remaining(original_cutoff)
    body=EpisodeCutoff.model_validate(value)
    # Start before the claim connection, not after receiving its response.
    # Subtracting that transport/setup time is conservative across clock domains.
    result=min(original_cutoff,request_started+(body.deadline_at-body.observed_at).total_seconds())
    remaining(result)
    return result
