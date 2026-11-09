from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

from anvil.db import digest
from anvil.environment_cloud import Authority, CloudBlocked, Profile, Worker


def profile():
    return Profile(
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
        validation_receipt_sha256="1" * 64,
    )


def test_cloud_is_inert_without_exact_explicit_authority():
    p = profile()
    with pytest.raises(CloudBlocked):
        Worker(
            p,
            Authority(
                digest(p.model_dump()), uuid4(), datetime.now(timezone.utc) + timedelta(hours=1), 1
            ),
            lambda: "never-used",
            httpx.Client(
                transport=httpx.MockTransport(lambda r: pytest.fail("No request permitted"))
            ),
        )


def test_compute_wire_contract_private_worker_idempotency_and_owned_cleanup():
    p, job = profile(), uuid4()
    calls = []

    def respond(request):
        import json

        calls.append(request)
        if "/global/images/" in request.url.path:
            return httpx.Response(200, json={"id": "111", "status": "READY"})
        if request.method == "POST":
            value = json.loads(request.content)
            assert value["networkInterfaces"][0]["accessConfigs"] == []
            assert value["disks"][0]["autoDelete"] is True
            assert value["scheduling"]["maxRunDuration"]["seconds"] == "3600"
            assert "startup-script" not in str(value)
            assert request.url.params["requestId"] == str(job)
            return httpx.Response(200, json={"name": "operation-test", "status": "PENDING"})
        if "/operations/" in request.url.path:
            return httpx.Response(
                200, json={"name": "operation-test", "status": "DONE", "targetId": "123"}
            )
        if request.method == "GET":
            return httpx.Response(
                200, json={"name": "anvil-env-" + job.hex, "labels": {"adi-owner": job.hex}}
            )
        return httpx.Response(200, json={"name": "delete-test", "status": "PENDING"})

    worker = Worker(
        p,
        Authority(
            digest(p.model_dump()), job, datetime.now(timezone.utc) + timedelta(hours=1), 1, True
        ),
        lambda: "synthetic-token",
        httpx.Client(transport=httpx.MockTransport(respond)),
    )
    assert (
        worker.create(
            manifest_object="environments/" + "a" * 64 + ".json",
            manifest_generation="123",
            manifest_sha256="a" * 64,
        )["status"]
        == "PENDING"
    )
    assert worker.poll("operation-test")["status"] == "DONE"
    assert worker.delete_owned(uuid4())["name"] == "delete-test"
    assert len(calls) == 5


def test_cleanup_refuses_other_owners_and_never_retries_ambiguous_dispatch():
    p, job = profile(), uuid4()
    count = []

    def respond(request):
        count.append(request.method)
        return httpx.Response(
            200, json={"name": "anvil-env-" + job.hex, "labels": {"adi-owner": "different-job"}}
        )

    worker = Worker(
        p,
        Authority(
            digest(p.model_dump()), job, datetime.now(timezone.utc) + timedelta(hours=1), 1, True
        ),
        lambda: "synthetic-token",
        httpx.Client(transport=httpx.MockTransport(respond)),
    )
    with pytest.raises(CloudBlocked, match="ownership"):
        worker.delete_owned(uuid4())
    assert count == ["GET"]
