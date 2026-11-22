"""The model gateway for live models (built behind the owner's approval; nothing here runs without one).

One `complete()` call per model turn, for five providers: anthropic (Messages), openai (Chat Completions), google
(Gemini API generateContent), vertex (Claude via rawPredict and Gemini via generateContent, with Application Default
Credentials) and huggingface (a hosted Inference Endpoint, its revision checked against the pinned one first).

Rules:
- **Keys:** read only through the allowlist: a named environment variable, or `.secrets/<name>` named by
  `<NAME>_FILE` (owner-only file, no symlink), never both. A key never leaves this module: it is not logged, stored,
  returned or passed to a runner, a container or a model.
- **Gates:** a real request needs `ANVIL_LIVE_PROVIDERS_ENABLED=true` and an approval checked by the caller
  (`approvals.require`). Without the flag the gateway refuses before reading a key. Tests pass a fake transport.
- **No retries:** SDK-style retries are off. A request that was sent but not answered (timeout after sending, dropped
  connection) is `ambiguous`: counted at its maximum cost and never retried automatically. A refused connection was
  never sent and is an ordinary error.
- **Network:** no proxy from the environment, no redirects followed, a bounded timeout.
"""

import json
import os
import stat
from dataclasses import dataclass, field
from decimal import Decimal

import httpx
from pydantic import SecretStr

from anvil.config import ROOT, private_file_owner
from anvil.rlgym.common import GymError

KEY_NAMES = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "huggingface": "HF_TOKEN",
    "vertex": None,  # Application Default Credentials (gcloud or GOOGLE_APPLICATION_CREDENTIALS)
}
PROVIDERS = tuple(KEY_NAMES)
ANTHROPIC_VERSION = "2023-06-01"
VERTEX_ANTHROPIC_VERSION = "vertex-2023-10-16"


def live_enabled():
    return os.environ.get("ANVIL_LIVE_PROVIDERS_ENABLED", "false") == "true"


class Ambiguous(GymError):
    """Sent, not answered: never retried automatically."""

    def __init__(self, message):
        super().__init__("LIVE_AMBIGUOUS", message)


@dataclass(frozen=True)
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    model_returned: str | None = None
    request_id: str | None = None
    finish_reason: str | None = None
    raw_usage: dict = field(default_factory=dict)

    def cost(self, price_in, price_out):
        """USD from the approval's verified prices (per million tokens)."""
        return (
            Decimal(self.tokens_in) * Decimal(str(price_in))
            + Decimal(self.tokens_out) * Decimal(str(price_out))
        ) / Decimal(1_000_000)


# --- keys -------------------------------------------------------------------------------------------------------


def key_source(name):
    """(present, problem) for an allowlisted secret, without reading its value."""
    value, file = os.environ.get(name), os.environ.get(name + "_FILE")
    if value and file:
        return False, "conflicting_secret_sources"
    if value:
        return True, None
    if not file:
        return False, "secret_missing"
    try:
        allowed = ROOT / ".secrets" / name.lower()
        candidate = ROOT / file
        if candidate.is_symlink() or candidate.resolve() != allowed.resolve():
            return False, "secret_path_not_allowlisted"
        if not candidate.is_file():
            return False, "secret_missing"
        info = candidate.stat()
        if stat.S_IMODE(info.st_mode) & 0o077 or not private_file_owner(info.st_uid):
            return False, "secret_file_permissions"
        return (info.st_size > 0), (None if info.st_size else "secret_empty")
    except OSError:
        return False, "secret_unreadable"


def read_key(provider):
    name = KEY_NAMES[provider]
    if name is None:
        raise GymError(
            "VALIDATION_FAILED", f"{provider} uses Application Default Credentials, not a key"
        )
    ok, problem = key_source(name)
    if not ok:
        raise GymError("KEY_MISSING", f"{name}: {problem}", {"provider": provider, "secret": name})
    value = os.environ.get(name)
    if value is None:
        value = (ROOT / os.environ[name + "_FILE"]).read_text().strip()
    return SecretStr(value)


def vertex_token():
    """An access token from Application Default Credentials (never stored)."""
    import google.auth
    import google.auth.transport.requests

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return SecretStr(creds.token)


def vertex_location():
    project, region = os.environ.get("ANVIL_VERTEX_PROJECT"), os.environ.get("ANVIL_VERTEX_REGION")
    if not (project and region):
        raise GymError(
            "VALIDATION_FAILED", "Set ANVIL_VERTEX_PROJECT and ANVIL_VERTEX_REGION for Vertex"
        )
    return project, region


# --- the gateway ------------------------------------------------------------------------------------------------


class Gateway:
    """`transport` is for tests (httpx.MockTransport) and is the only way to call without the live flag.
    `credentials` (tests) maps provider → SecretStr so no real key is read."""

    def __init__(self, transport=None, credentials=None, vertex=None):
        self.transport = transport
        self.credentials = credentials or {}
        self.vertex = vertex  # tests: (project, region)
        if transport is None and not live_enabled():
            raise GymError(
                "LIVE_DISABLED",
                "Live provider calls are disabled (ANVIL_LIVE_PROVIDERS_ENABLED is not true); no key was read",
            )
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise GymError("VALIDATION_FAILED", "Only a fake transport may replace the network")

    def _key(self, provider):
        if provider in self.credentials:
            return self.credentials[provider]
        return vertex_token() if provider == "vertex" else read_key(provider)

    def _client(self, timeout):
        return httpx.Client(
            transport=self.transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(timeout, connect=min(10, timeout)),
        )

    def _post(self, client, url, headers, body):
        try:
            r = client.post(url, headers=headers, json=body)
        except httpx.ConnectError as exc:
            raise GymError(
                "LIVE_UNAVAILABLE", f"Provider not reachable: {type(exc).__name__}"
            ) from None
        except (httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ReadError) as exc:
            raise Ambiguous(f"Sent, no answer ({type(exc).__name__}); not retried") from None
        if r.status_code >= 400:
            detail = r.text[:300]
            raise GymError("LIVE_REFUSED", f"Provider answered {r.status_code}", {"detail": detail})
        return r.json()

    def complete(
        self,
        provider,
        model_id,
        messages,
        *,
        max_output_tokens=1024,
        temperature=None,
        timeout_s=60,
        serving=None,
        hf_revision=None,
    ):
        """messages: [{"role": "system"|"user"|"assistant", "content": str}]."""
        if provider not in PROVIDERS:
            raise GymError("VALIDATION_FAILED", f"Unknown live provider {provider}")
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        key = self._key(provider)
        with self._client(timeout_s) as client:
            if provider == "anthropic":
                return _anthropic(
                    self._post(
                        client,
                        "https://api.anthropic.com/v1/messages",
                        {
                            "x-api-key": key.get_secret_value(),
                            "anthropic-version": ANTHROPIC_VERSION,
                        },
                        _anthropic_body(model_id, system, turns, max_output_tokens, temperature),
                    )
                )
            if provider == "openai":
                body = {
                    "model": model_id,
                    "messages": ([{"role": "system", "content": system}] if system else []) + turns,
                    "max_completion_tokens": max_output_tokens,
                    "store": False,
                }
                if temperature is not None:
                    body["temperature"] = temperature
                return _openai(
                    self._post(
                        client,
                        "https://api.openai.com/v1/chat/completions",
                        {"Authorization": f"Bearer {key.get_secret_value()}"},
                        body,
                    )
                )
            if provider == "google":
                return _gemini(
                    self._post(
                        client,
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent",
                        {"x-goog-api-key": key.get_secret_value()},
                        _gemini_body(system, turns, max_output_tokens, temperature),
                    )
                )
            if provider == "vertex":
                project, region = self.vertex or vertex_location()
                base = f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/publishers"
                auth = {"Authorization": f"Bearer {key.get_secret_value()}"}
                if model_id.startswith("claude"):
                    body = _anthropic_body(model_id, system, turns, max_output_tokens, temperature)
                    body.pop("model")
                    body["anthropic_version"] = VERTEX_ANTHROPIC_VERSION
                    return _anthropic(
                        self._post(
                            client, f"{base}/anthropic/models/{model_id}:rawPredict", auth, body
                        )
                    )
                return _gemini(
                    self._post(
                        client,
                        f"{base}/google/models/{model_id}:generateContent",
                        auth,
                        _gemini_body(system, turns, max_output_tokens, temperature),
                    )
                )
            # huggingface: a hosted Inference Endpoint serving the pinned revision
            endpoint = ((serving or {}).get("endpoint_url") or "").rstrip("/")
            if not endpoint.startswith("https://"):
                raise GymError(
                    "VALIDATION_FAILED", "A Hugging Face Inference Endpoint URL (https) is required"
                )
            auth = {"Authorization": f"Bearer {key.get_secret_value()}"}
            try:
                info = client.get(f"{endpoint}/info", headers=auth)
            except httpx.HTTPError as exc:
                raise GymError(
                    "LIVE_UNAVAILABLE", f"Endpoint not reachable: {type(exc).__name__}"
                ) from None
            served = (info.json() if info.status_code == 200 else {}).get("model_sha")
            if not hf_revision or served != hf_revision:
                raise GymError(
                    "HASH_MISMATCH",
                    "The endpoint does not serve the pinned revision",
                    {"pinned": hf_revision, "served": served},
                )
            body = {
                "model": "tgi",
                "messages": ([{"role": "system", "content": system}] if system else []) + turns,
                "max_tokens": max_output_tokens,
            }
            if temperature is not None:
                body["temperature"] = temperature
            return _openai(self._post(client, f"{endpoint}/v1/chat/completions", auth, body))


CHECK_URLS = {
    "anthropic": (
        "https://api.anthropic.com/v1/models",
        lambda k: {"x-api-key": k, "anthropic-version": ANTHROPIC_VERSION},
    ),
    "openai": ("https://api.openai.com/v1/models", lambda k: {"Authorization": f"Bearer {k}"}),
    "google": (
        "https://generativelanguage.googleapis.com/v1beta/models",
        lambda k: {"x-goog-api-key": k},
    ),
    "huggingface": (
        "https://huggingface.co/api/whoami-v2",
        lambda k: {"Authorization": f"Bearer {k}"},
    ),
}


def check_key(gw, provider):
    """A key test that costs nothing: list models (or who-am-I). Vertex: the ADC token is obtained. → (valid, note)."""
    key = gw._key(provider)
    if provider == "vertex":
        return True, "Application Default Credentials returned a token"
    url, headers = CHECK_URLS[provider]
    with gw._client(20) as client:
        try:
            r = client.get(url, headers=headers(key.get_secret_value()))
        except httpx.HTTPError as exc:
            raise GymError(
                "LIVE_UNAVAILABLE", f"Provider not reachable: {type(exc).__name__}"
            ) from None
    if r.status_code == 200:
        return True, "The provider accepted the key"
    if r.status_code in (401, 403):
        return False, f"The provider refused the key ({r.status_code})"
    raise GymError("LIVE_UNAVAILABLE", f"Provider answered {r.status_code}")


def _anthropic_body(model_id, system, turns, max_output_tokens, temperature):
    body = {"model": model_id, "max_tokens": max_output_tokens, "messages": turns}
    if system:
        body["system"] = system
    if temperature is not None:
        body["temperature"] = temperature
    return body


def _anthropic(data):
    usage = data.get("usage") or {}
    return Completion(
        text="".join(
            b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text"
        ),
        tokens_in=int(usage.get("input_tokens") or 0),
        tokens_out=int(usage.get("output_tokens") or 0),
        model_returned=data.get("model"),
        request_id=data.get("id"),
        finish_reason=data.get("stop_reason"),
        raw_usage=usage,
    )


def _openai(data):
    usage = data.get("usage") or {}
    choice = (data.get("choices") or [{}])[0]
    return Completion(
        text=((choice.get("message") or {}).get("content")) or "",
        tokens_in=int(usage.get("prompt_tokens") or 0),
        tokens_out=int(usage.get("completion_tokens") or 0),
        model_returned=data.get("model"),
        request_id=data.get("id"),
        finish_reason=choice.get("finish_reason"),
        raw_usage=usage,
    )


def _gemini_body(system, turns, max_output_tokens, temperature):
    body = {
        "contents": [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in turns
        ],
        "generationConfig": {"maxOutputTokens": max_output_tokens},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if temperature is not None:
        body["generationConfig"]["temperature"] = temperature
    return body


def _gemini(data):
    usage = data.get("usageMetadata") or {}
    cand = (data.get("candidates") or [{}])[0]
    return Completion(
        text="".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts") or []),
        tokens_in=int(usage.get("promptTokenCount") or 0),
        tokens_out=int(usage.get("candidatesTokenCount") or 0)
        + int(usage.get("thoughtsTokenCount") or 0),
        model_returned=data.get("modelVersion"),
        request_id=data.get("responseId"),
        finish_reason=cand.get("finishReason"),
        raw_usage=usage,
    )


def parse_json(text):
    """The first JSON object in a model's answer (the agent and judge protocols answer in JSON)."""
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(text, start)
            if isinstance(value, dict):
                return value
        except ValueError:
            pass
        start = text.find("{", start + 1)
    return None
