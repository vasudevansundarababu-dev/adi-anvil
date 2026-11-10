"""Authenticated draft-only task intake using checksum-verified handoff bytes."""

import hashlib
import importlib.util
import json
import socket
import ssl
import subprocess
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    if socket.gethostname() != "anvil-overnight-qa-20261110":
        raise ValueError("Owned QA host required")
    root = Path("/var/lib/anvil-overnight-qa")
    source = root / "seed-handoff"
    subprocess.run(
        ["sha256sum", "-c", "MANIFEST.sha256"], cwd=source, check=True, stdout=subprocess.DEVNULL
    )
    assert "**Status: READY" in (source / "STATUS.md").read_text()
    fixture = json.loads((root / "synthetic-oidc-test-fixture.json").read_text())
    assert fixture["origin"] == "synthetic_oidc_protocol_qa_only"
    spec = importlib.util.spec_from_file_location(
        "qa_oidc", "/home/vasudevan_sundarababu_adi_labs_a/qa-oidc-protocol.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = "https://anvil-qa.127.0.0.1.sslip.io:8443"
    auth = "https://auth-anvil-qa.127.0.0.1.sslip.io:8443"
    verify = ssl.create_default_context(cafile=str(root / "config/qa-root-ca.crt"))
    results = []
    with httpx.Client(verify=verify, trust_env=False, follow_redirects=False, timeout=30) as client:
        response = client.get(base + "/api/v1/auth/login")
        assert response.headers["location"].startswith(auth + "/realms/")
        form = module.Form()
        form.feed(client.get(response.headers["location"]).text)
        assert form.action.startswith(auth + "/realms/anvil-overnight-qa/")
        identity = fixture["users"]["rl-engineer"]
        response = client.post(
            form.action,
            data={
                "username": identity["username"],
                "password": identity["password"],
                "credentialId": "",
            },
        )
        assert response.status_code in (302, 303)
        assert response.headers["location"].startswith(base + "/api/v1/auth/callback?")
        assert client.get(response.headers["location"]).status_code in (302, 307)
        endpoint = base + f"/api/v1/projects/{fixture['project']}/workspace/benchmark"
        for folder in (
            "phone-launch",
            "locale-compliance",
            "kyb-review",
            "aml-alerts",
            "kyc-onboarding",
        ):
            raw = (source / (folder + ".anvil.zip")).read_bytes()
            headers = {
                "origin": base,
                "content-type": "application/zip",
                "x-csrf-token": client.cookies.get("anvil_csrf"),
                "idempotency-key": uuid4().hex,
            }
            imported = client.post(endpoint + "/import", content=raw, headers=headers)
            assert imported.status_code == 200, (
                f"Draft group import failed: {folder}, HTTP{imported.status_code}"
            )
            repeated = client.post(endpoint + "/import", content=raw, headers=headers)
            assert repeated.status_code == 200
            group = imported.json()["data"]
            assert group["id"] == repeated.json()["data"]["id"]
            results.append(
                {
                    "folder": folder,
                    "id": group["id"],
                    "archive_sha256": hashlib.sha256(raw).hexdigest(),
                    "idempotency": "pass",
                    "review_status": "draft",
                    "policy_sidecars": "retained_proposed_not_installed",
                }
            )
        current = client.get(endpoint).json()["data"]
        assert len(current["groups"]) == 5
    (root / "seed-import-public.json").write_text(
        json.dumps(
            {
                "source_commit": "bef6f49ebf1ad6c40f4fec0fea597cdc88c64743",
                "groups": results,
                "tasks": 10,
                "actor": "synthetic_qa_rl_engineer",
                "human_approvals_created": 0,
                "provider_calls": 0,
            }
        )
    )
    print(
        "Five draft groups / ten Tasks imported through authenticated HTTPS; no approvals or model calls"
    )


if __name__ == "__main__":
    main()
