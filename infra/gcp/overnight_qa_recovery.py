"""Actual QA cancel, durable evidence, worker restart and linked Engineer retry."""

import importlib.util
import json
import socket
import ssl
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110"
    root = Path("/var/lib/anvil-overnight-qa")
    fixture = json.loads((root / "synthetic-oidc-test-fixture.json").read_text())
    assert fixture["origin"] == "synthetic_oidc_protocol_qa_only"
    spec = importlib.util.spec_from_file_location(
        "oidc", "/home/vasudevan_sundarababu_adi_labs_a/qa-oidc-protocol.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    web = "https://anvil-qa.127.0.0.1.sslip.io:8443"
    auth = "https://auth-anvil-qa.127.0.0.1.sslip.io:8443"
    prefix = web + f"/api/v1/projects/{fixture['project']}/workspace"
    envs, bench = prefix + "/environments", prefix + "/benchmark"
    verify = ssl.create_default_context(cafile=str(root / "config/qa-root-ca.crt"))
    with httpx.Client(verify=verify, trust_env=False, follow_redirects=False, timeout=30) as client:

        def login(role):
            client.cookies.clear()
            identity = fixture["users"][role]
            response = client.get(web + "/api/v1/auth/login")
            form = module.Form()
            assert response.headers["location"].startswith(auth + "/realms/")
            form.feed(client.get(response.headers["location"]).text)
            assert form.action.startswith(auth + "/realms/anvil-overnight-qa/")
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

        def get(url):
            response = client.get(url)
            assert response.status_code == 200
            return response.json()["data"]

        def post(url):
            response = client.post(
                url,
                headers={
                    "origin": web,
                    "x-csrf-token": client.cookies.get("anvil_csrf"),
                    "idempotency-key": uuid4().hex,
                },
            )
            assert response.status_code == 200, "QA recovery operation HTTP" + str(
                response.status_code
            )
            return response.json()["data"]

        def terminal(identifier, seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                data = get(bench + "/runs/" + identifier)
                if data["run"]["state"] in {"completed", "blocked", "failed"}:
                    return data
                time.sleep(1)
            raise TimeoutError("Bounded recovery wait; no automatic resend")

        login("admin")
        parent = "ed46621a-9f5d-4c57-b36f-96ab4ad16149"
        before = get(bench + "/runs/" + parent)["view_sha256"]
        child = post(envs + "/runs/" + parent + "/retry")["id"]
        (root / "recovery-dispatch-public.json").write_text(
            json.dumps({"parent": parent, "cancel_trial": child, "provider_calls": 0})
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            attempts = get(envs + "/runs/" + child + "/attempts")
            if any(a["state"] == "running" for a in attempts):
                break
            time.sleep(0.2)
        else:
            raise AssertionError("No observed running attempt; cancellation not qualified")
        assert post(envs + "/runs/" + child + "/cancel")["cancel_requested"] is True
        cancelled = terminal(child, 240)
        assert cancelled["run"]["state"] in {"blocked", "failed"}
        retained = get(envs + "/runs/" + child + "/attempts")
        assert retained and all(a["evidence_receipt_id"] for a in retained)
        subprocess.run(["systemctl", "restart", "anvil-qa-run-worker"], check=True)
        assert get(bench + "/runs/" + parent)["view_sha256"] == before
        login("rl-engineer")
        retry = post(envs + "/runs/" + child + "/retry")
        assert retry["parent_run_id"] == child
        result = terminal(retry["id"], 600)
        assert result["run"]["state"] == "completed" and len(result["cells"]) == 12
        assert result["run"]["provider_calls"] == 0 and result["failures"]["cells"] == 0
        assert result["run"]["report_review"]["state"] == "pending_review"
        fresh = get(envs + "/runs/" + retry["id"] + "/attempts")
        assert {a["id"] for a in fresh}.isdisjoint(a["id"] for a in retained)
        assert any(a["parent_attempt_id"] in {r["id"] for r in retained} for a in fresh)
        receipt = {
            "cancelled_run": child,
            "retry_run": retry["id"],
            "retained_attempts": len(retained),
            "fresh_attempts": len(fresh),
            "worker_restart": "passed",
            "parent_result_unchanged": True,
            "engineer_review": "pending_review",
            "provider_calls": 0,
            "test": "actual_https_and_native_worker",
        }
        (root / "recovery-public.json").write_text(json.dumps(receipt))
        print(json.dumps(receipt))


if __name__ == "__main__":
    main()
