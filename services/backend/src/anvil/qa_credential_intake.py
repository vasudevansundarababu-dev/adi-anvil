"""Temporary loopback-only encrypted QA credential staging; no execution authority.

No keys are returned, printed, sent to providers, or assigned to an Anvil identity.
The existing encrypted store is reused in a fresh private root. A later explicit
authenticated import must bind staged credentials to the actual QA Project.
"""

import hmac
import json
import os
import secrets
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4

PROVIDERS = ("openai", "anthropic", "gemini")


class Intake:
    def __init__(self, root, save, *, lifetime=1200):
        self.root, self.save = Path(root), save
        self.nonce = secrets.token_urlsafe(32)
        self.identifier = str(uuid4())
        self.expires = time.monotonic() + lifetime
        self.saved = {}

    def accept(self, raw):
        if time.monotonic() >= self.expires or not isinstance(raw, bytes) or len(raw) > 32768:
            raise ValueError("Expired or invalid intake")
        body = parse_qs(
            raw.decode("ascii"), keep_blank_values=True, strict_parsing=True, max_num_fields=4
        )
        if set(body) != {"csrf", *PROVIDERS} or any(len(v) != 1 for v in body.values()):
            raise ValueError("Invalid fields")
        if not hmac.compare_digest(body["csrf"][0], self.nonce):
            raise ValueError("Invalid form token")
        values = {p: body[p][0].strip() for p in PROVIDERS if body[p][0].strip()}
        if not values or any(
            not 8 <= len(v) <= 8192 or not v.isascii() or any(not 33 <= ord(c) <= 126 for c in v)
            for v in values.values()
        ):
            raise ValueError("Invalid credential format")
        pending = {}
        for provider, value in values.items():
            binding = {
                "scope": "qa_key_intake_unassigned",
                "provider": provider,
                "intake_id": self.identifier,
            }
            pending[provider] = {"reference": self.save(value, binding), "binding": binding}
        self.saved.update(pending)
        status = {
            "schema_version": "anvil.qa-key-intake.v1",
            "intake_id": self.identifier,
            "credentials": self.saved,
            "provider_calls": 0,
            "activated": False,
            "project_bound": False,
        }
        path = self.root / "status.json"
        tmp = self.root / (".status-" + uuid4().hex)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(status, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        self.nonce = secrets.token_urlsafe(32)
        return sorted(self.saved)

    def page(self, message=""):
        fields = "".join(
            f'<label>{p.title()} API key<input type="password" name="{p}" autocomplete="off" spellcheck="false" maxlength="8192"></label>'
            for p in PROVIDERS
        )
        return f'''<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Anvil QA key staging</title>
<style nonce="{self.nonce}">body{{font:17px system-ui;max-width:600px;margin:50px auto;padding:20px;color:#17324b}}label{{display:block;margin:22px 0}}input{{display:block;width:95%;padding:12px;margin-top:8px}}button{{padding:12px;background:#146e80;color:white;border:0;border-radius:6px}}</style>
<h1>Anvil QA credentials</h1><p>Private local entry. Keys are encrypted on this computer. They are not printed, tested with providers or activated.</p><p>{message}</p>
<p id="save-status" role="status" aria-live="polite"></p>
<form method="post" action="/save"><input type="hidden" name="csrf" value="{self.nonce}">{fields}<button>Save encrypted QA keys</button></form>
<script nonce="{self.nonce}">
document.querySelector('form').addEventListener('submit', async (event) => {{
 event.preventDefault();
 const form = event.currentTarget, status = document.getElementById('save-status');
 const button = form.querySelector('button'); button.disabled = true;
 status.textContent = 'Saving encrypted keys locally…';
 try {{
  const response = await fetch('/save', {{method:'POST', credentials:'same-origin',
   headers:{{'Content-Type':'application/x-www-form-urlencoded'}},
   body:new URLSearchParams(new FormData(form)).toString()}});
  const result = await response.text();
  const parsed = new DOMParser().parseFromString(result, 'text/html');
  const notice = parsed.querySelector('h1 + p + p');
  status.textContent = notice ? notice.textContent : 'Unexpected response. Save was not confirmed.';
  const token = parsed.querySelector('input[name="csrf"]');
  if (token) form.elements.csrf.value = token.value;
  if (response.ok) form.querySelectorAll('input[type="password"]').forEach(input => input.value = '');
  button.disabled = false;
 }} catch (error) {{
  status.textContent = 'The local save request failed. Keys were not confirmed saved. Please retry or report this message.';
  button.disabled = false;
 }}
}});
</script>
<p>Leave a field blank to keep its staged key. Saving does not authorize spending, create an account or approve a Run.</p></html>'''.encode()


def server(intake):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *args):
            pass

        def reply(self, status, message):
            data = intake.page(message)
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                f"default-src 'none'; style-src 'nonce-{intake.nonce}'; script-src 'nonce-{intake.nonce}'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(data)

        def valid_host(self):
            return self.headers.get_all("Host") == [f"127.0.0.1:{self.server.server_port}"]

        def do_GET(self):
            if not self.valid_host() or self.path != "/":
                self.send_error(404)
                return
            if time.monotonic() >= intake.expires:
                self.reply(410, "This entry window has expired. No keys were activated.")
                return
            self.reply(200, "Staged providers: " + (", ".join(sorted(intake.saved)) or "none yet"))

        def do_POST(self):
            self.connection.settimeout(5)
            if (
                not self.valid_host()
                or self.path != "/save"
                or self.headers.get("Origin") != f"http://127.0.0.1:{self.server.server_port}"
            ):
                self.reply(403, "Only the local form may submit keys.")
                return
            lengths = self.headers.get_all("Content-Length", [])
            if (
                self.headers.get("Transfer-Encoding")
                or len(lengths) != 1
                or not lengths[0].isascii()
                or not lengths[0].isdecimal()
                or not 0 < int(lengths[0]) <= 32768
                or self.headers.get("Content-Type") != "application/x-www-form-urlencoded"
            ):
                self.reply(400, "Invalid form request. No activation occurred.")
                return
            try:
                raw = self.rfile.read(int(lengths[0]))
                if len(raw) != int(lengths[0]):
                    raise ValueError("Incomplete request")
                saved = intake.accept(raw)
            except Exception:
                self.reply(
                    400, "Keys were not saved completely. Please retry. No activation occurred."
                )
                return
            self.reply(
                200, "Encrypted keys saved for: " + ", ".join(saved) + ". No provider calls made."
            )

    result = HTTPServer(("127.0.0.1", 0), Handler)
    result.timeout = 1
    return result


def main():
    from anvil.config import CLOUD, ROOT
    from anvil.workspace_secrets import save

    if (
        CLOUD
        or not ROOT.name.startswith("anvil-qa-key-intake-")
        or ROOT.is_symlink()
        or ROOT.stat().st_uid != os.getuid()
        or ROOT.stat().st_mode & 0o077
    ):
        raise RuntimeError("Fresh owner-only local intake root required")
    intake = Intake(ROOT, save)
    service = server(intake)
    metadata = {
        "url": f"http://127.0.0.1:{service.server_port}/",
        "root": str(ROOT),
        "provider_calls": 0,
        "activated": False,
    }
    (ROOT / "public.json").write_text(json.dumps(metadata))
    print(json.dumps(metadata), flush=True)
    try:
        while time.monotonic() < intake.expires:
            service.handle_request()
    finally:
        service.server_close()


if __name__ == "__main__":
    main()
