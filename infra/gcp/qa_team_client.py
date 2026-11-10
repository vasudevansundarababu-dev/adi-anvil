"""Ephemeral authenticated QA client; never persists sessions or prints passwords."""

import json
import ssl
from contextlib import contextmanager
from uuid import uuid4

import httpx
from overnight_qa_bind_staged_credentials import AUTH, OPERATOR, WEB, Form


@contextmanager
def client(role="admin"):
    fixture = json.loads((OPERATOR / "browser-synthetic-fixture.json").read_text())
    assert fixture["origin"] == "synthetic_oidc_protocol_qa_only"
    assert role in {"admin", "rl-engineer"}
    verify = ssl.create_default_context(cafile=str(OPERATOR / "qa-root-ca.crt"))
    with httpx.Client(verify=verify, trust_env=False, follow_redirects=False, timeout=30) as http:
        response = http.get(WEB + "/api/v1/auth/login")
        assert response.headers["location"].startswith(AUTH + "/realms/")
        form = Form()
        form.feed(http.get(response.headers["location"]).text)
        assert form.action.startswith(AUTH + "/realms/anvil-overnight-qa/")
        identity = fixture["users"][role]
        response = http.post(form.action, data={"username": identity["username"], "password": identity["password"], "credentialId": ""})
        assert response.headers["location"].startswith(WEB + "/api/v1/auth/callback?")
        assert http.get(response.headers["location"]).status_code in (302, 307)

        class API:
            def request(self, method, path, *, body=None, raw=None):
                headers = {"origin": WEB, "x-csrf-token": http.cookies.get("anvil_csrf"), "idempotency-key": uuid4().hex}
                if raw is not None:
                    headers["content-type"] = "application/zip"
                response = http.request(method, WEB + path, json=body if raw is None else None, content=raw, headers=headers)
                if response.status_code != 200:
                    raise RuntimeError("QA API " + method + " " + path.split("?")[0] + " HTTP " + str(response.status_code))
                return response.json()["data"]

            def download(self, path):
                response = http.get(WEB + path)
                assert response.status_code == 200
                return response.content

        yield API()
