import json
import threading
from urllib.parse import urlencode

import httpx
import pytest

from anvil.qa_credential_intake import Intake, server


def form(intake, **changes):
    return urlencode(
        {
            "csrf": intake.nonce,
            "openai": "synthetic-openai-secret",
            "anthropic": "",
            "gemini": "",
            **changes,
        }
    ).encode()


def test_staging_never_echoes_key_or_grants_execution(tmp_path):
    writes = []

    def save(value, binding):
        writes.append((value, binding))
        return "opaque-test-reference"

    intake = Intake(tmp_path, save)
    old = intake.nonce
    assert intake.accept(form(intake)) == ["openai"]
    status = (tmp_path / "status.json").read_text()
    assert "synthetic-openai-secret" not in status
    assert "synthetic-openai-secret" not in intake.page().decode()
    assert writes[0][1]["scope"] == "qa_key_intake_unassigned"
    assert json.loads(status)["activated"] is False
    assert json.loads(status)["project_bound"] is False
    assert json.loads(status)["provider_calls"] == 0
    assert old != intake.nonce
    assert (tmp_path / "status.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "change",
    [{"csrf": "wrong"}, {"openai": ""}, {"openai": "embedded space"}, {"openai": "x" * 8193}],
)
def test_invalid_submissions_do_not_write(tmp_path, change):
    writes = []
    intake = Intake(tmp_path, lambda *args: writes.append(args))
    with pytest.raises(ValueError):
        intake.accept(form(intake, **change))
    assert not writes and not (tmp_path / "status.json").exists()


def test_http_requires_exact_origin_host_nonce_and_never_serves_status(tmp_path):
    intake = Intake(tmp_path, lambda *args: "opaque-test-reference")
    service = server(intake)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{service.server_port}"
    try:
        with httpx.Client(trust_env=False) as client:
            page = client.get(url)
            assert page.status_code == 200
            assert page.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
            assert client.get(url + "/status.json").status_code == 404
            assert client.get(url, headers={"Host": "untrusted.invalid"}).status_code == 404
            assert (
                client.post(
                    url + "/save",
                    content=form(intake),
                    headers={
                        "Origin": "https://untrusted.invalid",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                ).status_code
                == 403
            )
            saved = client.post(
                url + "/save",
                content=form(intake),
                headers={"Origin": url, "Content-Type": "application/x-www-form-urlencoded"},
            )
            assert saved.status_code == 200 and "Encrypted keys saved for: openai" in saved.text
            assert "synthetic-openai-secret" not in saved.text
    finally:
        service.shutdown()
        service.server_close()
        thread.join(3)
