"""Bounded GCP worker wire adapter, separate from the ordinary API/runtime.

No credential discovery, IAM/network creation or automatic activation. This module
is not called by local Build. A tested operator profile and explicit provisioning
authority must be supplied to the dedicated executor; draft configuration is inert.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

import httpx
from pydantic import Field, StrictInt, model_validator

from anvil.schemas import Strict


class Profile(Strict):
    project: str = Field(pattern=r"^[a-z][a-z0-9-]{4,61}[a-z0-9]$")
    region: str = Field(pattern=r"^[a-z]+-[a-z]+[0-9]$")
    zone: str = Field(pattern=r"^[a-z]+-[a-z]+[0-9]-[a-z]$")
    network: str = Field(pattern=r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$")
    subnet: str = Field(pattern=r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$")
    machine_type: str = Field(pattern=r"^e2-standard-(2|4|8)$")
    boot_image_project: str = Field(pattern=r"^[a-z][a-z0-9-]{4,61}[a-z0-9]$")
    boot_image: str = Field(pattern=r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$")
    boot_image_id: str = Field(pattern=r"^[1-9][0-9]{0,22}$")
    service_account: str = Field(
        pattern=r"^[a-z][a-z0-9-]+@[a-z][a-z0-9-]+\.iam\.gserviceaccount\.com$"
    )
    disk_gib: StrictInt = Field(ge=20, le=60)
    max_lifetime_seconds: StrictInt = Field(ge=300, le=86400)
    manifest_bucket: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{1,220}[a-z0-9]$")
    validation_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def location(self):
        if self.zone.rsplit("-", 1)[0] != self.region:
            raise ValueError("Zone must be in the configured region")
        if not self.service_account.endswith("@" + self.project + ".iam.gserviceaccount.com"):
            raise ValueError("Worker identity must belong to the explicit project")
        return self


@dataclass(frozen=True)
class Authority:
    profile_sha256: str
    job_id: UUID
    expires_at: datetime
    max_workers: int
    provisioning_enabled: bool = False
    source_sha256: str | None = None
    manifest_sha256: str | None = None


class CloudBlocked(RuntimeError):
    pass


class Worker:
    def __init__(
        self, profile: Profile, authority: Authority, token: Callable[[], str], client: httpx.Client
    ):
        from anvil.db import digest

        if (
            not authority.provisioning_enabled
            or authority.max_workers != 1
            or authority.profile_sha256 != digest(profile.model_dump())
            or authority.expires_at.tzinfo is None
            or authority.expires_at <= datetime.now(timezone.utc)
        ):
            raise CloudBlocked(
                "Exact tested profile and unexpired one-worker provisioning authority required"
            )
        self.profile, self.authority, self.token, self.client = profile, authority, token, client
        self.name = "anvil-env-" + authority.job_id.hex
        self.base = f"https://compute.googleapis.com/compute/v1/projects/{profile.project}/zones/{profile.zone}"

    def _request(self, method, suffix, *, body=None, request_id=None, image=False):
        # No caller-provided origin/path, and no credential enters a stored receipt.
        response = self.client.request(
            method,
            (
                f"https://compute.googleapis.com/compute/v1/projects/{self.profile.boot_image_project}/global"
                if image
                else self.base
            )
            + suffix,
            params={"requestId": str(request_id)} if request_id else None,
            json=body,
            headers={"Authorization": "Bearer " + self.token()},
            timeout=30,
        )
        if response.status_code >= 400:
            raise CloudBlocked(
                f"GCP operation rejected with HTTP {response.status_code}; no automatic retry"
            )
        value = response.json()
        if not isinstance(value, dict):
            raise CloudBlocked("Invalid GCP response shape")
        return value

    def create(self, *, manifest_object: str, manifest_generation: str, manifest_sha256: str):
        import re

        if self.authority.expires_at <= datetime.now(timezone.utc):
            raise CloudBlocked("Provisioning authority expired; no create request sent")
        if self.authority.manifest_sha256 != manifest_sha256:
            raise CloudBlocked("Exact authorized manifest digest required; no create request sent")
        if (
            not re.fullmatch(r"environments/[a-f0-9]{64}\.json", manifest_object)
            or not re.fullmatch(r"[1-9][0-9]{0,22}", manifest_generation)
            or not re.fullmatch(r"[a-f0-9]{64}", manifest_sha256)
        ):
            raise CloudBlocked("Exact immutable manifest object/generation/hash required")
        if manifest_object != f"environments/{manifest_sha256}.json":
            raise CloudBlocked("Manifest object and content hash differ")
        p = self.profile
        image = self._request("GET", "/images/" + p.boot_image, image=True)
        if str(image.get("id")) != p.boot_image_id or image.get("status") != "READY":
            raise CloudBlocked("Configured boot image identity changed or is not Ready")
        body = {
            "name": self.name,
            "labels": {
                "adi-owner": self.authority.job_id.hex,
                "adi-purpose": "environment-validation",
            },
            "machineType": f"zones/{p.zone}/machineTypes/{p.machine_type}",
            "disks": [
                {
                    "boot": True,
                    "autoDelete": True,
                    "initializeParams": {
                        "diskSizeGb": str(p.disk_gib),
                        "sourceImage": f"projects/{p.boot_image_project}/global/images/{p.boot_image}",
                    },
                }
            ],
            "networkInterfaces": [
                {
                    "network": f"projects/{p.project}/global/networks/{p.network}",
                    "subnetwork": f"projects/{p.project}/regions/{p.region}/subnetworks/{p.subnet}",
                    "accessConfigs": [],
                }
            ],
            "serviceAccounts": [
                {
                    "email": p.service_account,
                    "scopes": ["https://www.googleapis.com/auth/cloud-platform"],
                }
            ],
            "shieldedInstanceConfig": {
                "enableSecureBoot": True,
                "enableVtpm": True,
                "enableIntegrityMonitoring": True,
            },
            "scheduling": {
                "automaticRestart": False,
                "onHostMaintenance": "TERMINATE",
                "maxRunDuration": {"seconds": str(p.max_lifetime_seconds)},
                "instanceTerminationAction": "DELETE",
            },
            "metadata": {
                "items": [
                    {"key": "enable-oslogin", "value": "TRUE"},
                    {"key": "block-project-ssh-keys", "value": "TRUE"},
                    {
                        "key": "anvil-manifest",
                        "value": f"gs://{p.manifest_bucket}/{manifest_object}",
                    },
                    {"key": "anvil-manifest-generation", "value": manifest_generation},
                    {"key": "anvil-manifest-sha256", "value": manifest_sha256},
                ]
            },
        }
        # Boot image must already contain a separately qualified Anvil worker.
        # No arbitrary uploaded startup script, deprecated startup agent or apt install.
        return self._request("POST", "/instances", body=body, request_id=self.authority.job_id)

    def poll(self, operation_name):
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", operation_name):
            raise CloudBlocked("Invalid operation identity")
        value = self._request("GET", "/operations/" + operation_name)
        if value.get("error"):
            raise CloudBlocked("GCP operation returned an error; retained for reconciliation")
        return {
            "name": value.get("name"),
            "status": value.get("status"),
            "targetId": value.get("targetId"),
            "targetLink": value.get("targetLink"),
        }

    def delete_owned(self, request_id: UUID):
        row = self._request("GET", "/instances/" + self.name)
        if (
            row.get("name") != self.name
            or row.get("labels", {}).get("adi-owner") != self.authority.job_id.hex
        ):
            raise CloudBlocked("Resource ownership mismatch; nothing deleted")
        return self._request("DELETE", "/instances/" + self.name, request_id=request_id)
