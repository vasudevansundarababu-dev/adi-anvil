"""Dedicated GCP host worker: exact metadata manifest → existing SQL/native runtime.

Not imported or launched by ordinary API/worker. Workload identity reads only the
generation-bound manifest; actor containers never inherit its token or SQL key.
The qualified boot profile must supply the scoped worker DSN and pinned runtimes.
"""

import hashlib
import json
import re
from urllib.parse import quote
from uuid import UUID

import httpx
from pydantic import Field

from anvil import environment_runtime as runtime
from anvil import environment_validation as checks
from anvil.db import Jsonb, digest, one, transaction, uid
from anvil.environment_cloud_build import BuildProfile
from anvil.schemas import Strict


class Manifest(Strict):
    schema_version: str = Field(pattern=r"^anvil\.gcp-environment-job\.v1$")
    project_id: UUID
    initiated_by: UUID
    build_job_id: UUID
    environment_id: UUID
    environment_manifest_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    profile_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    execution_source_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    image_digest: str = Field(
        pattern=r"^[a-z]+-[a-z]+[0-9]-docker\.pkg\.dev/[a-z0-9-]+/[a-z0-9-]+/environment@sha256:[a-f0-9]{64}$"
    )


class Metadata:
    def __init__(self, client):
        self.client = client

    def read(self, path):
        if not re.fullmatch("[A-Za-z0-9_/-]+", path):
            raise ValueError("Invalid metadata field")
        response = self.client.get(
            "http://169.254.169.254/computeMetadata/v1/" + path,
            headers={"Metadata-Flavor": "Google"},
            timeout=5,
            follow_redirects=False,
        )
        if (
            response.status_code != 200
            or response.headers.get("Metadata-Flavor") != "Google"
            or len(response.content) > 65536
        ):
            raise ValueError("GCP metadata unavailable or invalid")
        return response.text.strip()

    def manifest(self):
        sha = self.read("instance/attributes/anvil-manifest-sha256")
        uri = self.read("instance/attributes/anvil-manifest")
        generation = self.read("instance/attributes/anvil-manifest-generation")
        match = re.fullmatch(
            r"gs://([a-z0-9][a-z0-9.-]{1,220}[a-z0-9])/(environments/[a-f0-9]{64}\.json)", uri
        )
        if (
            not match
            or match[2] != "environments/" + sha + ".json"
            or not re.fullmatch("[1-9][0-9]{0,22}", generation)
        ):
            raise ValueError("Immutable metadata manifest identity required")
        token = json.loads(self.read("instance/service-accounts/default/token"))
        if (
            not isinstance(token.get("access_token"), str)
            or not token["access_token"]
            or token.get("token_type") != "Bearer"
        ):
            raise ValueError("Workload identity token unavailable")
        response = self.client.get(
            "https://storage.googleapis.com/storage/v1/b/"
            + match[1]
            + "/o/"
            + quote(match[2], safe=""),
            params={"alt": "media", "generation": generation},
            headers={"Authorization": "Bearer " + token["access_token"]},
            timeout=30,
            follow_redirects=False,
        )
        if (
            response.status_code != 200
            or len(response.content) > 65536
            or hashlib.sha256(response.content).hexdigest() != sha
        ):
            raise ValueError("Manifest download hash/status/bound failed")
        return Manifest.model_validate_json(response.content), {
            "manifest_sha256": sha,
            "manifest_generation": generation,
            "manifest_bucket": match[1],
            "gcp_project": self.read("project/project-id"),
            "instance_id": self.read("instance/id"),
            "instance_name": self.read("instance/name"),
            "zone": self.read("instance/zone"),
            "origin": "mock_metadata_contract"
            if isinstance(self.client._transport, httpx.MockTransport)
            else "gcp_metadata",
        }


def perform(manifest: Manifest, metadata):
    from anvil.environment_execution import source_hash

    # A mock metadata response can test parsing but never qualify a cloud worker.
    if metadata.get("origin") != "gcp_metadata":
        raise ValueError("Mock metadata cannot qualify GCP execution")
    if source_hash() != manifest.execution_source_sha256:
        raise ValueError("Cloud worker source differs from frozen manifest")
    with transaction(str(manifest.project_id), str(manifest.initiated_by), worker=True) as c:
        c.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))", (str(manifest.build_job_id),))
        # Scope lookup by Project, then authenticate the original job initiator
        # against current membership before component reads or mutations.
        job = one(
            c,
            "SELECT * FROM anvil.environment_build_jobs WHERE id=%s FOR UPDATE",
            (manifest.build_job_id,),
        )
        if (
            not job
            or str(job["created_by"]) != str(manifest.initiated_by)
            or str(job["environment_id"]) != str(manifest.environment_id)
            or job["profile_sha256"] != manifest.profile_sha256
            or digest(job["profile"]) != manifest.profile_sha256
        ):
            raise ValueError("Cloud job/profile scope mismatch")
        profile = BuildProfile.model_validate(job["profile"])
        expected = "anvil-env-" + manifest.build_job_id.hex
        if (
            metadata["gcp_project"] != profile.project
            or metadata["instance_name"] != expected
            or not metadata["zone"].endswith("/zones/" + profile.zone)
            or metadata["manifest_bucket"] != profile.manifest_bucket
        ):
            raise ValueError("GCP instance identity differs from exact operator profile")
        if not manifest.image_digest.startswith(profile.registry + "/environment@sha256:"):
            raise ValueError("Worker image is outside exact private registry")
        version = runtime.get(c, "environment_versions", manifest.environment_id)
        if version["manifest_sha256"] != manifest.environment_manifest_sha256:
            raise ValueError("Environment manifest changed")
        old = one(
            c,
            "SELECT * FROM anvil.environment_build_steps WHERE job_id=%s AND phase='worker-validation'",
            (manifest.build_job_id,),
        )
        if old:
            return old
        if job["state"] in ("cancelled", "completed") or job["cancel_requested"]:
            raise ValueError("Cloud job is cancelled or terminal")
        intent = one(
            c,
            "SELECT id FROM anvil.environment_build_steps WHERE job_id=%s AND phase='worker-validation-intent'",
            (manifest.build_job_id,),
        )
        if intent:
            raise ValueError(
                "Prior worker validation dispatch needs reconciliation; no automatic replay"
            )
        receipt = checks.validate(
            c, manifest.project_id, job["created_by"], manifest.environment_id
        )
        if not receipt["content"]["passed"]:
            raise ValueError("Actual GCP-host component validation failed")
        # Actual native actor/collector validation uses this version's first
        # public collection and the exact cached Harbor profile, not a model.
        import os
        import tempfile
        from pathlib import Path

        from anvil.environment_harbor import execute
        from anvil.environment_seeds import CATALOG

        instance = runtime.create_instance(
            c, manifest.project_id, job["created_by"], manifest.environment_id
        )
        intent_content = {
            "instance_id": str(instance["id"]),
            "manifest_sha256": metadata["manifest_sha256"],
            "execution_source_sha256": manifest.execution_source_sha256,
        }
        c.execute(
            "INSERT INTO anvil.environment_build_steps(id,project_id,job_id,phase,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (
                uid(),
                manifest.project_id,
                manifest.build_job_id,
                "worker-validation-intent",
                Jsonb(intent_content),
                digest(intent_content),
                job["created_by"],
            ),
        )
        c.commit()
        c.execute(
            "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
            (str(manifest.project_id), str(job["created_by"])),
        )

        def action():
            result = runtime.execute(
                c,
                job["created_by"],
                instance["id"],
                "list_records",
                {"collection": CATALOG[version["manifest"]["template_id"]]["collections"][0]},
                0,
            )
            evidence = runtime.export_evidence(c, job["created_by"], instance["id"])
            c.commit()
            c.execute(
                "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                (str(manifest.project_id), str(job["created_by"])),
            )
            return {"actual_tool_result": result}, evidence

        root = Path(tempfile.mkdtemp(prefix="anvil-cloud-native-"))
        native = execute(
            root / "attempt",
            {
                "origin": "synthetic_gcp_component_validation",
                "environment_manifest_sha256": version["manifest_sha256"],
            },
            action,
            host=os.environ["ANVIL_HARBOR_DOCKER_HOST"],
            python=os.environ["ANVIL_ENVIRONMENT_HARBOR_PYTHON"],
        )
        runtime.close(c, job["created_by"], instance["id"])
        content = {
            "schema_version": "anvil.gcp-component-validation.v1",
            "environment_manifest_sha256": version["manifest_sha256"],
            "profile_sha256": manifest.profile_sha256,
            "execution_source_sha256": manifest.execution_source_sha256,
            "image_digest": manifest.image_digest,
            "component_receipt_id": str(receipt["id"]),
            "component_receipt_sha256": receipt["content_sha256"],
            "native_actor_collection": {k: v for k, v in native.items() if k != "trusted_receipt"},
            "metadata": metadata,
            "provider_calls": 0,
            "model_performance": False,
            "authentic_task_qualification": False,
        }
        row = one(
            c,
            "INSERT INTO anvil.environment_build_steps(id,project_id,job_id,phase,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uid(),
                manifest.project_id,
                manifest.build_job_id,
                "worker-validation",
                Jsonb(content),
                digest(content),
                job["created_by"],
            ),
        )
        c.execute(
            "UPDATE anvil.environment_build_jobs SET state='completed',phase='worker-validation',revision=revision+1 WHERE id=%s",
            (manifest.build_job_id,),
        )
        return row


def main():
    import os

    if os.environ.get("ANVIL_ENVIRONMENT_CLOUD_WORKER_ENABLED") != "true":
        raise RuntimeError("Dedicated cloud worker is disabled")
    with httpx.Client(trust_env=False, follow_redirects=False) as client:
        manifest, metadata = Metadata(client).manifest()
        result = perform(manifest, metadata)
        print(
            json.dumps(
                {
                    "receipt_id": str(result["id"]),
                    "receipt_sha256": result["content_sha256"],
                    "provider_calls": 0,
                }
            )
        )


if __name__ == "__main__":
    main()
