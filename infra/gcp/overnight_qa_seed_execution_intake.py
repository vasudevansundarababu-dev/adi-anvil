"""Stage exact draft Tasks in the existing structured-decision broker path.

Package compilation is deterministic ZIP generation, never an image build,
human approval, rights clearance, activation or provider call.
"""

import hashlib
import importlib.util
import json
import socket
import ssl
import subprocess
import zipfile
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110"
    root = Path("/var/lib/anvil-overnight-qa")
    source = root / "seed-handoff"
    subprocess.run(
        ["sha256sum", "-c", "MANIFEST.sha256"], cwd=source, check=True, stdout=subprocess.DEVNULL
    )
    assert "**Status: READY" in (source / "STATUS.md").read_text()
    fixture = json.loads((root / "synthetic-oidc-test-fixture.json").read_text())
    assert fixture["origin"] == "synthetic_oidc_protocol_qa_only"
    spec = importlib.util.spec_from_file_location(
        "oidc", "/home/vasudevan_sundarababu_adi_labs_a/qa-oidc-protocol.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    web = "https://anvil-qa.127.0.0.1.sslip.io:8443"
    auth = "https://auth-anvil-qa.127.0.0.1.sslip.io:8443"
    verify = ssl.create_default_context(cafile=str(root / "config/qa-root-ca.crt"))
    results = []
    with httpx.Client(verify=verify, trust_env=False, follow_redirects=False, timeout=30) as client:
        response = client.get(web + "/api/v1/auth/login")
        assert response.headers["location"].startswith(auth + "/realms/")
        form = module.Form()
        form.feed(client.get(response.headers["location"]).text)
        assert form.action.startswith(auth + "/realms/anvil-overnight-qa/")
        identity = fixture["users"]["admin"]
        response = client.post(
            form.action,
            data={
                "username": identity["username"],
                "password": identity["password"],
                "credentialId": "",
            },
        )
        assert response.headers["location"].startswith(web + "/api/v1/auth/callback?")
        assert client.get(response.headers["location"]).status_code in (302, 307)
        endpoint = web + f"/api/v1/projects/{fixture['project']}"

        def post(url, body=None):
            response = client.post(
                url,
                json=body,
                headers={
                    "origin": web,
                    "x-csrf-token": client.cookies.get("anvil_csrf"),
                    "idempotency-key": uuid4().hex,
                },
            )
            assert response.status_code == 200, "Draft execution intake HTTP" + str(
                response.status_code
            )
            return response.json()["data"]

        models = []
        for provider, model_id in (
            ("openai", "gpt-6.1-sol"),
            ("openai", "gpt-6-luna"),
            ("anthropic", "claude-fable-5-2"),
            ("anthropic", "claude-opus-5-5"),
            ("gemini", "gemini-4-argon"),
            ("gemini", "gemini-3.8-flash"),
        ):
            response = client.get(endpoint + "/workspace/models")
            assert response.status_code == 200
            current = response.json()["data"]["items"]
            item = next((m for m in current if m["name"] == "Overnight QA " + model_id), None)
            if item is None:
                item = post(
                    endpoint + "/workspace/models",
                    {
                        "name": "Overnight QA " + model_id,
                        "provider": provider,
                        "model_id": model_id,
                        "max_output_tokens": 2048,
                        "processing_terms_reviewed": False,
                    },
                )
            assert item["model_id"] == model_id and item["provider"] == provider
            assert item["credential_present"] is False and item["status"] == "planning_only"
            models.append(
                {
                    "id": item["id"],
                    "provider": provider,
                    "model_id": model_id,
                    "state": "planning_only",
                    "credential_bound": False,
                    "processing_terms_reviewed": False,
                }
            )
        (root / "model-planning-public.json").write_text(
            json.dumps(
                {
                    "models": models,
                    "provider_calls": 0,
                    "authority": "owner_exact_model_selection_only",
                    "availability_verified": False,
                }
            )
        )

        for folder in (
            "phone-launch",
            "locale-compliance",
            "kyb-review",
            "aml-alerts",
            "kyc-onboarding",
        ):
            with zipfile.ZipFile(source / (folder + ".anvil.zip")) as archive:
                names = [
                    n for n in archive.namelist() if n.startswith("tasks/") and n.endswith(".json")
                ]
                assert len(names) == 2
                for name in names:
                    envelope = archive.read(name)
                    value = json.loads(envelope)
                    payload = value["payload_json"].encode()
                    task = json.loads(payload)
                    assert hashlib.sha256(payload).hexdigest() == value["payload_sha256"]
                    assert task["provenance"]["review"]["status"] == "draft"
                    assert value["source"]["reviewer_id"] is None
                    item = post(endpoint + "/praxis-sources", {"payload": envelope.decode()})
                    assert item["source_sha256"] == value["payload_sha256"]
                    package = post(endpoint + "/praxis-sources/" + item["id"] + "/build")
                    assert package["approval"] is None
                    assert package["manifest"]["binding"] == "structured-decision-v1"
                    repeated = post(endpoint + "/praxis-sources", {"payload": envelope.decode()})
                    assert repeated["id"] == item["id"]
                    results.append(
                        {
                            "task_id": task["task_id"],
                            "source_id": item["id"],
                            "source_sha256": item["source_sha256"],
                            "package_id": package["id"],
                            "package_sha256": package["package_sha256"],
                            "binding": "structured-decision-v1",
                            "source_review": "draft",
                            "package_approval": None,
                        }
                    )
                    (root / "seed-execution-intake-public.json").write_text(
                        json.dumps(
                            {
                                "tasks": results,
                                "source_commit": "bef6f49ebf1ad6c40f4fec0fea597cdc88c64743",
                                "human_approvals_created": 0,
                                "provider_calls": 0,
                                "image_builds": 0,
                            }
                        )
                    )
    assert len(results) == 10
    print(
        json.dumps(
            {
                "draft_sources": len(results),
                "deterministic_packages": len(results),
                "provider_calls": 0,
                "human_approvals": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
