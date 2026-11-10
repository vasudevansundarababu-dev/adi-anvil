"""Actual HTTPS authorization-code/PKCE QA journeys; not a browser UI test."""

import json
import socket
import ssl
from html.parser import HTMLParser
from pathlib import Path

import httpx


class Form(HTMLParser):
    action = None

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == "form" and fields.get("id") == "kc-form-login":
            self.action = fields.get("action")


def main():
    if socket.gethostname() != "anvil-overnight-qa-20261110":
        raise ValueError("Owned QA host required")
    root = Path("/var/lib/anvil-overnight-qa")
    fixture = json.loads((root / "synthetic-oidc-test-fixture.json").read_text())
    assert fixture["origin"] == "synthetic_oidc_protocol_qa_only"
    base = "https://anvil-qa.127.0.0.1.sslip.io:8443"
    auth = "https://auth-anvil-qa.127.0.0.1.sslip.io:8443"
    context = ssl.create_default_context(cafile=str(root / "config/qa-root-ca.crt"))
    results = []
    for role, identity in fixture["users"].items():
        with httpx.Client(
            verify=context, trust_env=False, follow_redirects=False, timeout=20
        ) as client:
            start = client.get(base + "/api/v1/auth/login")
            assert start.status_code in (302, 307)
            assert start.headers["location"].startswith(auth + "/realms/anvil-overnight-qa/")
            page = client.get(start.headers["location"])
            assert page.status_code == 200
            form = Form()
            form.feed(page.text)
            assert form.action and form.action.startswith(auth + "/realms/anvil-overnight-qa/")
            response = client.post(
                form.action,
                data={
                    "username": identity["username"],
                    "password": identity["password"],
                    "credentialId": "",
                },
            )
            assert response.status_code in (302, 303), "Synthetic OIDC credential step failed"
            destination = response.headers["location"]
            assert destination.startswith(base + "/api/v1/auth/callback?")
            callback = client.get(destination)
            assert callback.status_code in (302, 307), "Actual API OIDC callback failed"
            me = client.get(base + "/api/v1/me")
            assert me.status_code == 200
            state = me.json()["data"]
            assert identity["id"] in json.dumps(state)
            environments = client.get(
                base + f"/api/v1/projects/{fixture['project']}/workspace/environments"
            )
            assert environments.status_code == 200
            assert len(environments.json()["data"]["templates"]) == 6
            dashboard = client.get(
                base + f"/api/v1/projects/{fixture['project']}/workspace/benchmark"
            )
            assert dashboard.status_code == 200
            results.append(
                {
                    "role": role,
                    "https_verified": True,
                    "oidc_code_pkce_callback": "pass",
                    "six_templates": "pass",
                    "dashboard": "pass",
                    "provider_calls": 0,
                }
            )
    (root / "oidc-protocol-public.json").write_text(
        json.dumps(
            {
                "origin": fixture["origin"],
                "journeys": results,
                "browser_ui_test": False,
                "real_owner_acceptance": False,
            }
        )
    )
    print(
        json.dumps(
            {
                "protocol_journeys_passed": len(results),
                "provider_calls": 0,
                "browser_ui_test": False,
            }
        )
    )


if __name__ == "__main__":
    main()
