"""Bound generation and project credentials in a pre-provisioned GCP secret.

Local immutable indexes contain version locators only, never keys. VM workload identity
authenticates requests; no service-account file or SDK credential is accepted.
"""

import base64
import json
import os
import re
import stat
from pathlib import Path
from uuid import UUID, uuid4

import httpx

from anvil.config import private_file_owner


def resource():
    from anvil import pilot_environment

    pilot = pilot_environment.current()
    if pilot:
        if os.environ.get("ANVIL_WORKER_BROKER_ROLE") != "api":
            raise ValueError("Only the API may resolve pilot provider credentials")
        number = os.environ.get("ANVIL_PILOT_GCP_PROJECT_NUMBER", "")
        value = os.environ.get("ANVIL_PILOT_SECRET_RESOURCE", "")
        prefix = pilot_environment.TARGETS[pilot][1]
        if (
            not re.fullmatch(r"[1-9][0-9]{0,19}", number)
            or value != f"projects/{number}/secrets/{prefix}-model-credentials"
        ):
            raise ValueError("Exact isolated permanent-pilot credential resource required")
        if os.environ.get("ANVIL_QA_SECRET_RESOURCE") or os.environ.get(
            "ANVIL_GENERATION_SECRET_RESOURCE"
        ):
            raise ValueError("Legacy/temporary credential resources cannot be inherited")
        if any(
            os.environ.get(k)
            for k in (
                "GOOGLE_APPLICATION_CREDENTIALS",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "GOOGLE_API_KEY",
                "GEMINI_API_KEY",
                "OPENAI_API_KEY_FILE",
                "ANTHROPIC_API_KEY_FILE",
                "GOOGLE_API_KEY_FILE",
                "GEMINI_API_KEY_FILE",
            )
        ):
            raise ValueError("Ambient provider/service-account keys are forbidden")
        return value
    if os.environ.get("ANVIL_CREDENTIAL_STORE_PROFILE", "legacy") == "qa":
        value = os.environ.get("ANVIL_QA_SECRET_RESOURCE", "")
        if not re.fullmatch(r"projects/[0-9]+/secrets/anvil-qa-model-credentials", value):
            raise ValueError("Separate QA credential secret is not configured")
        return value
    if os.environ.get("ANVIL_CREDENTIAL_STORE_PROFILE", "legacy") != "legacy":
        raise ValueError("Unsupported credential store profile")
    value = os.environ.get("ANVIL_GENERATION_SECRET_RESOURCE", "")
    if not re.fullmatch(r"projects/[0-9]+/secrets/anvil-import-generation", value):
        raise ValueError("Managed generation secret is not configured")
    return value


def available():
    try:
        resource()
        return True
    except ValueError:
        return False


def validate_binding(binding):
    if (
        set(binding) == {"scope", "settings_id", "provider"}
        and binding.get("scope") == "installation_import_generation"
        and isinstance(binding.get("settings_id"), str)
        and binding["settings_id"]
        and binding.get("provider") in {"openai", "anthropic", "gemini"}
    ):
        return
    if set(binding) != {"project_id", "credential_id", "version_id", "provider"}:
        raise ValueError("Unsupported evaluation credential binding")
    for key in ("project_id", "credential_id", "version_id"):
        if str(UUID(binding[key])) != binding[key]:
            raise ValueError("Invalid evaluation credential binding")
    if binding["provider"] not in {"openai", "anthropic", "gemini", "langsmith", "huggingface"}:
        raise ValueError("Unsupported evaluation credential provider")


def request(method, path, body=None):
    from anvil import pilot_environment

    pilot = pilot_environment.current()
    if pilot:
        selected = resource()
        if not (
            (method == "POST" and path == selected + ":addVersion")
            or (
                method == "GET"
                and re.fullmatch(re.escape(selected) + r"/versions/[0-9]+:access", path)
            )
        ):
            raise ValueError("Pilot secret operation outside exact resource")
    from anvil.golden_kyc_dispatch_scope import current

    if current() is not None:
        from anvil.golden_kyc_deadline_http import secret_request

        return secret_request(method,path,body)
    with httpx.Client(trust_env=False, timeout=15, follow_redirects=False) as client:
        token = client.get(
            ("http://169.254.169.254" if pilot else "http://metadata.google.internal")
            + "/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
        )
        token.raise_for_status()
        response = client.request(
            method,
            "https://secretmanager.googleapis.com/v1/" + path,
            headers={"Authorization": "Bearer " + token.json()["access_token"]},
            json=body,
        )
        response.raise_for_status()
        if len(response.content) > 65536:
            raise ValueError("Managed secret response exceeds bound")
        return response.json()


def index():
    path = Path(os.environ.get("ANVIL_CLOUD_SECRET_INDEX", "/app/.data/secret-index"))
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if not private_file_owner(info.st_uid) or info.st_mode & 0o077:
        os.close(fd)
        raise ValueError("Unsafe managed secret index")
    return fd


def save(value, binding):
    validate_binding(binding)
    selected_resource = resource()
    if (
        os.environ.get("ANVIL_CREDENTIAL_STORE_PROFILE", "legacy") in {"qa", "qa-v1", "staging-v1"}
        and "scope" in binding
    ):
        raise ValueError("QA credential store requires a project binding")
    identifier = str(uuid4())
    data = json.dumps({"id": identifier, "binding": binding, "secret": value}).encode()
    if len(data) > 32768:
        raise ValueError("Credential exceeds bound")
    fd = index()
    try:
        version = request(
            "POST",
            selected_resource + ":addVersion",
            {"payload": {"data": base64.b64encode(data).decode()}},
        )["name"]
        if not re.fullmatch(re.escape(selected_resource) + r"/versions/[0-9]+", version):
            raise ValueError("Unexpected managed secret version")
        out = os.open(
            identifier, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd
        )
        with os.fdopen(out, "w") as stream:
            json.dump({"version": version}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)
    return identifier


def load(identifier, binding):
    validate_binding(binding)
    selected_resource = resource()
    if (
        os.environ.get("ANVIL_CREDENTIAL_STORE_PROFILE", "legacy") in {"qa", "qa-v1", "staging-v1"}
        and "scope" in binding
    ):
        raise ValueError("QA credential store requires a project binding")
    name = str(UUID(str(identifier)))
    fd = index()
    try:
        item = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        with os.fdopen(item) as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or not private_file_owner(info.st_uid)
                or info.st_mode & 0o077
                or info.st_size > 4096
            ):
                raise ValueError("Unsafe managed secret locator")
            version = json.load(stream)["version"]
    finally:
        os.close(fd)
    if not re.fullmatch(re.escape(selected_resource) + r"/versions/[0-9]+", version):
        raise ValueError("Unexpected managed secret locator")
    response = request("GET", version + ":access")
    if response.get("name") != version:
        raise ValueError("Managed secret version mismatch")
    value = json.loads(base64.b64decode(response["payload"]["data"], validate=True))
    if (
        value.get("id") != name
        or value.get("binding") != binding
        or not isinstance(value.get("secret"), str)
    ):
        raise ValueError("Managed credential binding mismatch")
    return value["secret"]
