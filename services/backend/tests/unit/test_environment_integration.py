"""Fail-closed collection and cloud wire contracts, always offline transports."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import pytest

from anvil.db import digest
from anvil.environment_cloud import Authority, CloudBlocked
from anvil.environment_cloud_build import BuildOperator, BuildProfile
from anvil.environment_cloud_worker import Metadata, perform
from anvil.environment_collect import harbor_collection


def test_metadata_manifest_is_generation_hash_and_identity_bound_and_mock_cannot_qualify():
    job = uuid4()
    manifest = {
        "schema_version": "anvil.gcp-environment-job.v1",
        "project_id": str(uuid4()),
        "initiated_by": str(uuid4()),
        "build_job_id": str(job),
        "environment_id": str(uuid4()),
        "environment_manifest_sha256": "1" * 64,
        "profile_sha256": "2" * 64,
        "execution_source_sha256": "3" * 64,
        "image_digest": "us-west1-docker.pkg.dev/fictional-project/anvil-test/environment@sha256:"
        + "4" * 64,
    }
    raw = json.dumps(manifest).encode()
    sha = hashlib.sha256(raw).hexdigest()
    fields = {
        "instance/attributes/anvil-manifest-sha256": sha,
        "instance/attributes/anvil-manifest": "gs://fictional-manifests/environments/"
        + sha
        + ".json",
        "instance/attributes/anvil-manifest-generation": "123",
        "instance/service-accounts/default/token": json.dumps(
            {"access_token": "offline-test-token", "token_type": "Bearer"}
        ),
        "project/project-id": "fictional-project",
        "instance/id": "123",
        "instance/name": "anvil-env-" + job.hex,
        "instance/zone": "projects/123/zones/us-west1-a",
    }
    calls = []

    def send(request):
        calls.append(request)
        if request.url.host == "169.254.169.254":
            assert request.headers["Metadata-Flavor"] == "Google"
            return httpx.Response(
                200,
                text=fields[request.url.path.removeprefix("/computeMetadata/v1/")],
                headers={"Metadata-Flavor": "Google"},
            )
        assert request.url.host == "storage.googleapis.com"
        assert request.url.params["generation"] == "123"
        return httpx.Response(200, content=raw)

    with httpx.Client(transport=httpx.MockTransport(send)) as client:
        parsed, evidence = Metadata(client).manifest()
    assert parsed.initiated_by == UUID(manifest["initiated_by"])
    assert evidence["origin"] == "mock_metadata_contract"
    assert "offline-test-token" not in json.dumps(evidence)
    with pytest.raises(ValueError, match="Mock metadata"):
        perform(parsed, evidence)
    fields["instance/attributes/anvil-manifest-generation"] = "latest"
    with httpx.Client(transport=httpx.MockTransport(send)) as client:
        with pytest.raises(ValueError, match="Immutable"):
            Metadata(client).manifest()


class Journal:
    def __init__(self):
        self.rows = {}
        self.unknown = []

    def begin(self, job, phase, request):
        key = (job, phase)
        if key in self.rows:
            old = self.rows[key]
            if old["request"] != request:
                raise CloudBlocked("changed request")
            return {"new": False, "ack": old.get("ack")}
        self.rows[key] = {"request": request}
        return {"new": True}

    def ack(self, job, phase, value):
        self.rows[(job, phase)]["ack"] = value

    def uncertain(self, job, phase):
        self.unknown.append((job, phase))


def profile():
    return BuildProfile(
        project="fictional-project",
        region="us-west1",
        zone="us-west1-a",
        network="anvil-test",
        subnet="anvil-test",
        machine_type="e2-standard-4",
        boot_image_project="fictional-project",
        boot_image="qualified-worker-v1",
        boot_image_id="111",
        service_account="worker@fictional-project.iam.gserviceaccount.com",
        disk_gib=30,
        max_lifetime_seconds=3600,
        manifest_bucket="fictional-manifests",
        registry="us-west1-docker.pkg.dev/fictional-project/anvil-test",
        build_service_account="projects/fictional-project/serviceAccounts/build@fictional-project.iam.gserviceaccount.com",
        builder_image="gcr.io/cloud-builders/docker@sha256:" + "1" * 64,
    )


def operator(send, journal=None):
    p = profile()
    raw = b"explicit synthetic source archive wire fixture"
    sha = hashlib.sha256(raw).hexdigest()
    a = Authority(
        digest(p.model_dump()),
        uuid4(),
        datetime.now(timezone.utc) + timedelta(minutes=5),
        1,
        True,
        source_sha256=sha,
    )
    return (
        BuildOperator(
            p,
            a,
            lambda: "synthetic-offline-token",
            httpx.Client(transport=httpx.MockTransport(send)),
            journal or Journal(),
        ),
        raw,
        sha,
    )


def test_cloud_build_pins_source_generation_identity_and_only_submits_once():
    calls = []

    def send(request):
        calls.append(request)
        if request.url.host == "storage.googleapis.com":
            assert request.url.params["ifGenerationMatch"] == "0"
            return httpx.Response(
                200,
                json={
                    "bucket": "fictional-manifests",
                    "name": request.url.params["name"],
                    "generation": "123",
                },
            )
        body = json.loads(request.content)
        assert body["source"]["storageSource"]["generation"] == "123"
        assert body["steps"][0]["args"][1:3] == ["--network=none", "--pull=false"]
        assert body["options"]["logging"] == "NONE" and "secretEnv" not in str(body)
        return httpx.Response(
            200,
            json={
                "name": "projects/fictional-project/locations/us-west1/operations/owned-operation"
            },
        )

    client, raw, sha = operator(send)
    source = client.upload_source(raw, sha)
    first = client.submit(source)
    assert client.submit(source) == first
    assert len(calls) == 2
    with pytest.raises(CloudBlocked):
        client.upload_source(raw, "0" * 64)


def test_ambiguous_build_dispatch_is_never_retried():
    count = []

    def send(request):
        count.append(request)
        raise httpx.ReadTimeout("synthetic ambiguous reply")

    client, raw, sha = operator(send)
    source = {
        "bucket": "fictional-manifests",
        "object": "environment-source/" + sha + ".tar.gz",
        "generation": "123",
        "sha256": sha,
    }
    with pytest.raises(httpx.ReadTimeout):
        client.submit(source)
    with pytest.raises(CloudBlocked, match="Uncertain"):
        client.submit(source)
    assert len(count) == 1 and len(client.journal.unknown) == 1


@pytest.mark.parametrize("status", ["failed", "empty", "skipped", "not_run"])
def test_native_trial_success_cannot_hide_missing_or_failed_required_collection(status):
    result = harbor_collection(
        [{"name": "output", "status": status, "byte_size": 4, "sha256": "a" * 64}],
        required=["output"],
    )
    assert not result["complete"]
    assert not harbor_collection([], required=["output"])["complete"]
    assert not harbor_collection(
        [{"name": "output", "status": "collected", "byte_size": 0, "sha256": "a" * 64}],
        required=["output"],
    )["complete"]
