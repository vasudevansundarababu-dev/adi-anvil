"""Source-bound Cloud Storage/Cloud Build adapter for the dedicated operator.

No credential discovery or API route. Caller must supply an exact, unexpired
authority and a journal that commits intent before a mutating request. The API
does not have a Build request ID, so uncertain submission is never retried.
"""

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import quote

from pydantic import Field, model_validator

from anvil.db import digest
from anvil.environment_cloud import Authority, CloudBlocked, Profile


class BuildProfile(Profile):
    validation_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    registry: str = Field(
        pattern=r"^[a-z]+-[a-z]+[0-9]-docker\.pkg\.dev/[a-z][a-z0-9-]+/[a-z][a-z0-9-]+$"
    )
    build_service_account: str = Field(
        pattern=r"^projects/[a-z][a-z0-9-]+/serviceAccounts/[a-z][a-z0-9-]+@[a-z][a-z0-9-]+\.iam\.gserviceaccount\.com$"
    )
    builder_image: str = Field(pattern=r"^gcr\.io/cloud-builders/docker@sha256:[a-f0-9]{64}$")
    build_timeout_seconds: int = Field(default=1200, ge=60, le=2400, strict=True)

    @model_validator(mode="after")
    def scoped_build(self):
        if (
            not self.registry.startswith(self.region + "-docker.pkg.dev/" + self.project + "/")
            or not self.build_service_account.startswith("projects/" + self.project + "/")
            or not self.build_service_account.endswith(
                "@" + self.project + ".iam.gserviceaccount.com"
            )
        ):
            raise ValueError(
                "Build identity and registry must belong to the explicit project/region"
            )
        return self


class BuildOperator:
    def __init__(self, profile: BuildProfile, authority: Authority, token, client, journal):
        if (
            not authority.provisioning_enabled
            or authority.profile_sha256 != digest(profile.model_dump())
            or authority.max_workers != 1
            or authority.expires_at.tzinfo is None
            or authority.expires_at <= datetime.now(timezone.utc)
        ):
            raise CloudBlocked("Exact unexpired cloud build authority required")
        self.profile, self.authority, self.token, self.client, self.journal = (
            profile,
            authority,
            token,
            client,
            journal,
        )
        self.base = f"https://cloudbuild.googleapis.com/v1/projects/{profile.project}/locations/{profile.region}"
        if not re.fullmatch("[a-f0-9]{64}", authority.source_sha256 or ""):
            raise CloudBlocked("Exact authorized source digest required")

    def call(self, method, url, **kwargs):
        response = self.client.request(
            method,
            url,
            headers={
                "Authorization": "Bearer " + self.token(),
                **({"Content-Type": "application/octet-stream"} if "content" in kwargs else {}),
            },
            timeout=30,
            **kwargs,
        )
        if response.status_code >= 400:
            raise CloudBlocked(f"Cloud operation HTTP {response.status_code}; no automatic retry")
        value = response.json()
        if not isinstance(value, dict):
            raise CloudBlocked("Invalid cloud response")
        return value

    def once(self, phase, request, send):
        if self.authority.expires_at <= datetime.now(timezone.utc):
            raise CloudBlocked("Cloud authority expired")
        # Journal.begin is durable before send. Existing unacknowledged intent
        # represents an ambiguous external write and must not re-enter send.
        state = self.journal.begin(str(self.authority.job_id), phase, digest(request))
        if state.get("ack") is not None:
            return state["ack"]
        if not state.get("new"):
            raise CloudBlocked(
                "Uncertain external dispatch; reconcile the owned operation before continuing"
            )
        try:
            value = send()
        except Exception:
            self.journal.uncertain(str(self.authority.job_id), phase)
            raise
        self.journal.ack(str(self.authority.job_id), phase, value)
        return value

    def upload_source(self, raw: bytes, expected_sha256: str):
        if (
            not isinstance(raw, bytes)
            or not 0 < len(raw) <= 32 * 1024 * 1024
            or hashlib.sha256(raw).hexdigest() != expected_sha256
            or expected_sha256 != self.authority.source_sha256
        ):
            raise CloudBlocked("Bounded exact source archive required")
        name = "environment-source/" + expected_sha256 + ".tar.gz"
        value = self.once(
            "source-upload",
            {"name": name, "sha256": expected_sha256, "size": len(raw)},
            lambda: self.call(
                "POST",
                f"https://storage.googleapis.com/upload/storage/v1/b/{self.profile.manifest_bucket}/o",
                params={"uploadType": "media", "name": name, "ifGenerationMatch": "0"},
                content=raw,
            ),
        )
        if (
            value.get("name") != name
            or value.get("bucket") != self.profile.manifest_bucket
            or not re.fullmatch("[1-9][0-9]{0,22}", str(value.get("generation", "")))
        ):
            raise CloudBlocked("Uploaded source identity is invalid")
        return {
            "bucket": self.profile.manifest_bucket,
            "object": name,
            "generation": str(value["generation"]),
            "sha256": expected_sha256,
        }

    def submit(self, source):
        if (
            source.get("bucket") != self.profile.manifest_bucket
            or source.get("object") != "environment-source/" + source.get("sha256", "") + ".tar.gz"
            or not re.fullmatch("[a-f0-9]{64}", source.get("sha256", ""))
            or not re.fullmatch("[1-9][0-9]{0,22}", str(source.get("generation", "")))
        ):
            raise CloudBlocked("Exact content-addressed source/generation required")
        image = self.profile.registry + "/environment:" + source["sha256"]
        body = {
            "source": {"storageSource": {k: source[k] for k in ("bucket", "object", "generation")}},
            "steps": [
                {
                    "name": self.profile.builder_image,
                    "args": ["build", "--network=none", "--pull=false", "-t", image, "."],
                }
            ],
            "images": [image],
            "timeout": str(self.profile.build_timeout_seconds) + "s",
            "serviceAccount": self.profile.build_service_account,
            "options": {"logging": "NONE"},
            "tags": ["anvil-env-" + self.authority.job_id.hex],
        }
        result = self.once(
            "image-build",
            body,
            lambda: self.call(
                "POST", self.base + "/builds", params={"projectId": self.profile.project}, json=body
            ),
        )
        name = result.get("name", "")
        if not re.fullmatch(
            "projects/"
            + re.escape(self.profile.project)
            + "/locations/"
            + re.escape(self.profile.region)
            + "/operations/[A-Za-z0-9_-]+",
            name,
        ):
            raise CloudBlocked("Invalid build operation identity")
        return {"operation": name, "image": image, "source": source}

    def get_build(self, build_id, expected_source):
        if not re.fullmatch("[a-f0-9-]{20,80}", build_id):
            raise CloudBlocked("Invalid build identity")
        row = self.call("GET", self.base + "/builds/" + quote(build_id, safe=""))
        if row.get("tags") != ["anvil-env-" + self.authority.job_id.hex] or row.get(
            "source", {}
        ).get("storageSource") != {
            k: expected_source[k] for k in ("bucket", "object", "generation")
        }:
            raise CloudBlocked("Build ownership/source mismatch")
        status = row.get("status")
        image = None
        if status == "SUCCESS":
            images = row.get("results", {}).get("images", [])
            if len(images) != 1 or not re.fullmatch(
                "sha256:[a-f0-9]{64}", images[0].get("digest", "")
            ):
                raise CloudBlocked("Successful build has no exact image digest")
            expected = self.profile.registry + "/environment:" + expected_source["sha256"]
            if images[0].get("name") != expected:
                raise CloudBlocked("Published image name changed")
            image = self.profile.registry + "/environment@" + images[0]["digest"]
        return {
            "build_id": build_id,
            "status": status,
            "image_digest": image,
            "source": expected_source,
        }

    def cancel(self, build_id, expected_source):
        owned = self.get_build(build_id, expected_source)
        if owned["status"] not in ("QUEUED", "WORKING"):
            return owned
        return self.once(
            "cancel-build",
            {"build_id": build_id},
            lambda: self.call(
                "POST", self.base + "/builds/" + quote(build_id, safe="") + ":cancel", json={}
            ),
        )


class SQLJournal:
    """Append-only intent/ack fence; separate transactions precede external effects."""

    def __init__(self, project, user, profile_sha256):
        if not re.fullmatch("[a-f0-9]{64}", profile_sha256):
            raise CloudBlocked("Pinned operator profile digest required")
        self.project, self.user, self.profile_sha256 = project, user, profile_sha256

    def begin(self, job, phase, request_sha256):
        from anvil.db import Jsonb, one, transaction, uid

        with transaction(self.project, self.user, worker=True) as c:
            row = one(
                c, "SELECT * FROM anvil.environment_build_jobs WHERE id=%s FOR UPDATE", (job,)
            )
            if not row:
                raise CloudBlocked("Owned build job not found")
            if (
                row["profile_sha256"] != self.profile_sha256
                or digest(row["profile"]) != self.profile_sha256
            ):
                raise CloudBlocked("Build job profile differs from explicit authority")
            intent = one(
                c,
                "SELECT content FROM anvil.environment_build_steps WHERE job_id=%s AND phase=%s",
                (job, phase + "-intent"),
            )
            ack = one(
                c,
                "SELECT content FROM anvil.environment_build_steps WHERE job_id=%s AND phase=%s",
                (job, phase + "-ack"),
            )
            if intent and intent["content"]["request_sha256"] != request_sha256:
                raise CloudBlocked("Dispatch content changed")
            if intent:
                return {"new": False, "ack": ack["content"]["response"] if ack else None}
            content = {
                "request_sha256": request_sha256,
                "state": "intent_committed_before_dispatch",
            }
            c.execute(
                "INSERT INTO anvil.environment_build_steps(id,project_id,job_id,phase,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    uid(),
                    self.project,
                    job,
                    phase + "-intent",
                    Jsonb(content),
                    digest(content),
                    self.user,
                ),
            )
            c.execute("UPDATE anvil.environment_build_jobs SET state='running',phase=%s,revision=revision+1 WHERE id=%s",(phase,job))
            return {"new": True}

    def ack(self, job, phase, response):
        from anvil.db import Jsonb, transaction, uid

        # Retain only public bounded operation identifiers, never credentials/body logs.
        safe = {
            k: v
            for k, v in response.items()
            if k in ("name", "bucket", "generation", "id", "status", "done")
        }
        if any(
            type(v) not in (str, int, bool)
            or (isinstance(v, str) and (len(v) > 500 or not re.fullmatch("[A-Za-z0-9_./-]+", v)))
            for v in safe.values()
        ):
            raise CloudBlocked("Invalid public operation identifiers; no response body retained")
        with transaction(self.project, self.user, worker=True) as c:
            content = {"response": safe}
            c.execute(
                "INSERT INTO anvil.environment_build_steps(id,project_id,job_id,phase,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    uid(),
                    self.project,
                    job,
                    phase + "-ack",
                    Jsonb(content),
                    digest(content),
                    self.user,
                ),
            )

    def uncertain(self, job, phase):
        from anvil.db import transaction

        with transaction(self.project, self.user, worker=True) as c:
            c.execute(
                "UPDATE anvil.environment_build_jobs SET state='reconciliation_required',revision=revision+1 WHERE id=%s",
                (job,),
            )
