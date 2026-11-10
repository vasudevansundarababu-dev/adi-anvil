"""Owner-authorized encrypted intake -> authenticated QA credential API.

Key values exist only inside the store/API clients. No values, request bodies,
session data or provider replies are logged. This grants no run/source approval.
"""

import json
import os
import ssl
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

import httpx

INTAKE = Path("/private/tmp/anvil-qa-key-intake-bcc8e8a790c24cdfbd77c8645552607a")
OPERATOR = Path("/private/tmp/anvil-overnight-qa-20261110-operator")
WEB = "https://anvil-qa.127.0.0.1.sslip.io:8443"
AUTH = "https://auth-anvil-qa.127.0.0.1.sslip.io:8443"


class Form(HTMLParser):
    action = None

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == "form" and fields.get("id") == "kc-form-login":
            self.action = fields.get("action")


def main():
    assert os.environ.get("ANVIL_ROOT") == str(INTAKE)
    assert os.environ.get("ANVIL_ENV") == "local"
    from anvil.workspace_secrets import load

    status = json.loads((INTAKE / "status.json").read_text())
    assert set(status["credentials"]) == {"openai", "anthropic", "gemini"}
    fixture = json.loads((OPERATOR / "browser-synthetic-fixture.json").read_text())
    assert fixture["origin"] == "synthetic_oidc_protocol_qa_only"
    assert fixture["project"] == "b3337332-aff7-4041-93f8-6adf9ca276d3"
    verify = ssl.create_default_context(cafile=str(OPERATOR / "qa-root-ca.crt"))
    result = []
    with httpx.Client(verify=verify, trust_env=False, follow_redirects=False, timeout=30) as client:
        response = client.get(WEB + "/api/v1/auth/login")
        assert response.headers["location"].startswith(AUTH + "/realms/")
        form = Form()
        form.feed(client.get(response.headers["location"]).text)
        assert form.action.startswith(AUTH + "/realms/anvil-overnight-qa/")
        identity = fixture["users"]["admin"]
        response = client.post(form.action, data={"username": identity["username"], "password": identity["password"], "credentialId": ""})
        assert response.headers["location"].startswith(WEB + "/api/v1/auth/callback?")
        assert client.get(response.headers["location"]).status_code in (302, 307)
        endpoint = WEB + f"/api/v1/projects/{fixture['project']}/workspace/credentials"
        response = client.get(endpoint)
        assert response.status_code == 200 and response.json()["data"]["entry_available"]
        existing = response.json()["data"]["items"]
        for provider in ("openai", "anthropic", "gemini"):
            name = "Owner supplied overnight QA " + provider
            item = next((v for v in existing if v["name"] == name), None)
            if item is None:
                staged = status["credentials"][provider]
                value = load(staged["reference"], staged["binding"])
                response = client.post(endpoint, json={"name": name, "provider": provider, "secret": value}, headers={"origin": WEB, "x-csrf-token": client.cookies.get("anvil_csrf"), "idempotency-key": uuid4().hex})
                del value
                assert response.status_code == 200, "Credential API did not complete"
                item = response.json()["data"]
            assert item["provider"] == provider and item["revoked_at"] is None
            result.append({"provider": provider, "credential_id": item["id"], "version_id": item["current_version_id"]})
    receipt = {"project": fixture["project"], "credentials": result, "provider_calls_dispatched": 0, "source_approvals_created": 0, "run_authorizations_created": 0, "actor_origin": fixture["origin"]}
    (OPERATOR / "credential-bindings-public.json").write_text(json.dumps(receipt))
    print(json.dumps(receipt))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("QA credential binding did not complete; no secret details logged") from None
